"""Promptit ja säännöt -sivut (Asetusten alla): luettelo, yksittäinen prompti, muokkauslomake gatewaylle, escapetus
ja 404. Hub ei kirjoita mitään: lomake on gatewayn (paluu=hub), ja kiinteällä tekstillä ei ole lomaketta."""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui import dokumentit
from ilmari_ui.app import Settings, create_app
from test_dokumentit import julkaise as julkaise_dokumentit
from test_kehotteet import AIKA, KADET, KIINTEA, MUOKATTU, RIVI, kirjoita, luettelo
from test_toiminta import RP, julkaise, lomakkeet, tuotanto


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def dom(r) -> BeautifulSoup:
    return BeautifulSoup(r.text, "html.parser")


# --- Esimerkkitila -----------------------------------------------------------------------------------------------

def test_luettelo_esimerkkitilassa():
    r = asiakas().get("/hub/kehotteet?demo=1")
    sivu = dom(r)
    assert r.status_code == 200 and "refresh" not in r.headers
    assert sivu.find("a", class_="back")["href"] == "/hub/asetukset?demo=1"
    assert [h.get_text(" ", strip=True) for h in sivu.select("h2.label")] == ["Ilmari", "Ilmarin kädet", "Sinun ohjeesi",
                                                                             "Säännöt"]
    rivit = {a["href"]: a.find_parent("li") for a in sivu.select("ul.rows a")}
    assert list(rivit) == [
        "/hub/kehotteet/jarjestelma?demo=1", "/hub/kehotteet/vuoro?demo=1", "/hub/kehotteet/tyokalut?demo=1",
        "/hub/kehotteet/tyon_alku?demo=1", "/hub/asetukset?demo=1#ohjeet", "/hub/asetukset?demo=1#tavoitteet",
        "/hub/dokumentit/saannot?demo=1", "/hub/dokumentit/agents?demo=1"]
    tagit = {href: [t.get_text() for t in li.select(".tag")] for href, li in rivit.items()}
    assert tagit["/hub/kehotteet/jarjestelma?demo=1"] == ["muokattu"] and tagit["/hub/kehotteet/vuoro?demo=1"] == ["muokattava"]
    assert tagit["/hub/kehotteet/tyokalut?demo=1"] == [] and tagit["/hub/kehotteet/tyon_alku?demo=1"] == []
    assert "Ilmarin perusohje: mukana jokaisessa keskustelussa" in rivit["/hub/kehotteet/jarjestelma?demo=1"].get_text()
    assert rivit["/hub/asetukset?demo=1#ohjeet"].find("small").get_text() == "3\u00a0kpl"
    assert rivit["/hub/asetukset?demo=1#tavoitteet"].find("small").get_text() == "3\u00a0kpl"
    assert rivit["/hub/dokumentit/saannot?demo=1"].a.get_text() == "Esimerkkisäännöt: kuka päättää mistä"
    assert "<form" not in r.text and "<textarea" not in r.text               # luettelossa ei ole lomakkeita
    assert not any(sana in r.text for sana in ("gateway", "dsh", "ADR"))     # ei jargonia


def test_muokattava_prompti_esimerkkitilassa():
    r = asiakas().get("/hub/kehotteet/jarjestelma?demo=1")
    sivu = dom(r)
    assert r.status_code == 200 and sivu.title.get_text() == "Systemprompti · Ilmari"
    assert sivu.find("a", class_="back")["href"] == "/hub/kehotteet?demo=1"
    h1 = sivu.find("h1", id="h-kehote")
    assert h1.find(string=True, recursive=False).strip() == "Systemprompti"
    assert h1.find("span", class_="aside").get_text() == "muokattu 19.11.\u00a0klo\u00a015.40"
    kentta = sivu.find("textarea", attrs={"name": "teksti"})
    assert kentta["maxlength"] == "6000" and kentta.has_attr("required") and int(kentta["rows"]) >= 10
    assert kentta.get_text().startswith("Olet Ilmari (esimerkki). Tee työt itse loppuun.\n\nRaportoi lyhyesti: mitä tein")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert [b.get_text() for b in sivu.find_all("button")] == ["Tallenna", "Palauta alkuperäinen"]
    assert sivu.find("form") is None                                        # esimerkkitilassa napit eivät tee mitään
    alkuperainen = sivu.find("details", class_="fold")
    assert alkuperainen.summary.get_text() == "Alkuperäinen teksti"
    assert alkuperainen.find("div", class_="pre").get_text() == "Olet Ilmari (esimerkki). Tee työt itse loppuun.\n\nRaportoi lyhyesti."
    assert "Alkuperäinen: src/aiops/ceo_masterprompt.md" in sivu.get_text()
    assert sivu.find("code").get_text() == "src/aiops/ceo_masterprompt.md"      # tiedostopolku on dataa, ei käyttöliittymän tekstiä


def test_muokkaamaton_ja_kiintea_prompti():
    c = asiakas()
    vuoro = dom(c.get("/hub/kehotteet/vuoro?demo=1"))
    assert [b.get_text() for b in vuoro.find_all("button")] == ["Tallenna"]   # ei palautusta, kun ei ole muokattu
    assert vuoro.find("details") is None and vuoro.find("h1").find("span", class_="aside") is None
    r = c.get("/hub/kehotteet/tyokalut?demo=1")
    kiintea = dom(r)
    assert r.status_code == 200 and kiintea.find("textarea") is None and kiintea.find("button") is None
    assert kiintea.find("div", class_="pre").get_text().startswith("aja\nTee työ käsillä (esimerkki).")
    assert "Kiinteä teksti koodissa: src/aiops/ceo.py ja src/aiops/rekisteri/kyvyt/. Muutosta voi pyytää Työt-sivulla." in kiintea.get_text()


def test_tuntematon_ja_kelvoton_tunniste_404():
    c = asiakas()
    for polku in ("/hub/kehotteet/eiole?demo=1", "/hub/kehotteet/ISO?demo=1", "/hub/kehotteet/jarjestelma",
                  "/hub/kehotteet/a.b?demo=1"):
        r = c.get(polku)
        assert r.status_code == 404 and "<textarea" not in r.text, polku


def test_ilman_esimerkkitilaa_lahdetta_ei_ole():
    r = asiakas().get("/hub/kehotteet")
    assert r.status_code == 200 and "Promptit eivät ole saatavilla tässä ympäristössä." in r.text
    assert dom(r).select("h2.label") == [] and "Hahmon promptit" not in r.text


def test_asetuksissa_linkki_ja_aktiivinen_valikko():
    c = asiakas()
    muut = dom(c.get("/hub/asetukset?demo=1")).find("section", attrs={"aria-labelledby": "h-muut"})
    assert [(a.get_text(), a["href"]) for a in muut.find_all("a")][:2] == [
        ("Promptit ja säännöt", "/hub/kehotteet?demo=1"), ("Dokumentit", "/hub/dokumentit?demo=1")]
    for polku in ("/hub/kehotteet?demo=1", "/hub/kehotteet/vuoro?demo=1"):
        nykyinen = dom(c.get(polku)).select('nav a[aria-current="page"]')
        assert [a.get_text() for a in nykyinen] == ["Asetukset"]


# --- Tuotantotila: gatewayn julkaisu ja lomakkeet ----------------------------------------------------------------

def test_tuotannossa_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    hak = kirjoita(julkaise(tmp_path / "toiminta"), luettelo(MUOKATTU, KIINTEA, KADET))
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    assert r.status_code == 200 and "Refresh" not in r.headers and "form-action 'self'" in r.headers["content-security-policy"]
    assert lomakkeet(r) == {"/ilmari/kehote/jarjestelma": {"paluu": "hub", "teksti": "Olet Ilmari. Vastaa lyhyesti."},
                            "/ilmari/kehote/jarjestelma/oletus": {"paluu": "hub"}}
    assert dom(r).find("a", class_="back")["href"] == "/hub/kehotteet"
    kiintea = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/tyokalut")
    assert kiintea.status_code == 200 and lomakkeet(kiintea) == {} and "<textarea" not in kiintea.text
    lista = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet")
    assert lista.status_code == 200 and lomakkeet(lista) == {}
    assert [h.get_text(" ", strip=True) for h in dom(lista).select("h2.label")] == ["Ilmari", "Ilmarin kädet", "Sinun ohjeesi"]


def test_tuotannossa_saannot_asennetuista_dokumenteista(tmp_path, monkeypatch):
    """Säännöt-ryhmä näkyy vain, kun dokumentit on asennettu ja niissä on säännöt tai avustajien ohjeet."""
    hak = kirjoita(julkaise(tmp_path / "toiminta"), luettelo())
    dok = [{"tunniste": "tilanne", "polku": "docs/TILANNE.md", "ryhma": "perus", "otsikko": "Tilanne", "tila": "",
            "paiva": "", "teksti": "# Tilanne\n"},
           {"tunniste": "agents", "polku": "AGENTS.md", "ryhma": "perus", "otsikko": "Ohjeet tekoälyavustajille",
            "tila": "", "paiva": "", "teksti": "# Ohjeet tekoälyavustajille\n\nVastaa suomeksi.\n"}]
    julkaise_dokumentit(tmp_path / "dokumentit", dok)
    monkeypatch.setattr(dokumentit, "OLETUS", tmp_path / "dokumentit")
    oikea = dokumentit.lue_dokumentit      # testijulkaisun omistaja on testin käyttäjä, ei root (omistaja: test_dokumentit)
    monkeypatch.setattr(dokumentit, "lue_dokumentit", lambda root, omistaja=0: oikea(root, omistaja=None))
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet")
    sivu = dom(r)
    assert [h.get_text(" ", strip=True) for h in sivu.select("h2.label")][-1] == "Säännöt"
    saannot = sivu.find("section", attrs={"aria-labelledby": "h-saannot"})
    assert [(a.get_text(), a["href"]) for a in saannot.find_all("a")] == [
        ("Ohjeet tekoälyavustajille", "/hub/dokumentit/agents")]


def test_tuotannossa_julkaisematon_ja_rikkinainen_luettelo(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "toiminta"), polku="/kehotteet")
    assert r.status_code == 200 and "Prompteja ei ole vielä tallennettu." in r.text and dom(r).select("h2.label") == []
    assert tuotanto(tmp_path, monkeypatch, tmp_path / "toiminta", polku="/kehotteet/jarjestelma").status_code == 404
    hak = kirjoita(julkaise(tmp_path / "rikki"), luettelo(RIVI | {"vieras": 1}))
    r = tuotanto(tmp_path / "x", monkeypatch, hak, polku="/kehotteet")
    assert r.status_code == 200 and "kentät eivät vastaa muotoa" in r.text and "Systemprompti" not in r.text


def test_teksti_koodataan_myos_tuotannossa(tmp_path, monkeypatch):
    paha = RIVI | {"teksti": "</textarea><script>alert(1)</script>", "otsikko": "<b>Otsikko</b>", "kuvaus": "<i>x</i>"}
    hak = kirjoita(julkaise(tmp_path / "toiminta"), luettelo(paha, KIINTEA | {"teksti": "<img src=x onerror=alert(1)>"}))
    for polku in ("/kehotteet", "/kehotteet/jarjestelma", "/kehotteet/tyokalut"):
        r = tuotanto(tmp_path, monkeypatch, hak, polku=polku)
        assert r.status_code == 200
        assert "<script>" not in r.text and "<img" not in r.text and "<b>Otsikko" not in r.text and "<i>x" not in r.text
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    assert lomakkeet(r)["/ilmari/kehote/jarjestelma"]["teksti"] == "</textarea><script>alert(1)</script>"


def test_esimerkkitiedosto_on_samaa_muotoa_kuin_gatewayn(tmp_path):
    """Esimerkkiaineiston kentät ovat täsmälleen ne, jotka lukija vaatii (ei erkaannu oikeasta muodosta)."""
    data = json.loads((Path(__file__).resolve().parents[1] / "src" / "ilmari_ui" / "demo" / "toiminta" /
                       "kehotteet.json").read_text(encoding="utf-8"))
    assert set(data) == {"versio", "aika", "kehotteet"} and data["aika"] != AIKA
    assert all(list(r) == ["tunniste", "ryhma", "otsikko", "kuvaus", "lahde", "teksti", "oletus", "muokattu",
                           "muokattava", "enint"] for r in data["kehotteet"])
