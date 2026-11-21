"""Promptit ja säännöt -sivut (Asetusten alla): luettelo, yksittäinen prompti, muokkauslomake gatewaylle, escapetus
ja 404. Hub ei kirjoita mitään: lomake on gatewayn (paluu=hub), ja kiinteällä tekstillä ei ole lomaketta.

Käsikirjan versiot ja lukko (aiops ADR-0033 pala 6): aiemmat versiot palautusnapein, voimassa olevan tekstin
kirjoittaja ja lukko luettelossa. Vanha muoto ilman versioita näyttää sivut ennallaan."""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui import dokumentit
from ilmari_ui.app import Settings, create_app
from test_dokumentit import julkaise as julkaise_dokumentit
from test_kehotteet import AIKA, KADET, KIINTEA, MUOKATTU, RIVI, V1, V2, V3, kirjoita, luettelo, uusi
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
    assert "Ravintopolun ja Hahmon omat promptit ovat niiden omissa asetuksissa." in r.text
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
    assert kentta["maxlength"] == "12000" and kentta.has_attr("required") and int(kentta["rows"]) >= 10
    assert kentta.get_text().startswith("Olet Ilmari (esimerkki). Tee työt itse loppuun.\n\nRaportoi lyhyesti: mitä tein")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert [b.get_text() for b in sivu.find_all("button")] == ["Tallenna", "Palauta alkuperäinen", "Palauta", "Palauta",
                                                               "Palauta"]
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
    assert dom(r).select("h2.label") == [] and "omissa asetuksissa" not in r.text


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
    assert list(data) == ["versio", "aika", "lukittu", "kehotteet"] and data["aika"] != AIKA
    assert all(list(r) == ["tunniste", "ryhma", "otsikko", "kuvaus", "lahde", "teksti", "oletus", "muokattu",
                           "muokattava", "enint", "versiot"] for r in data["kehotteet"])
    assert all(list(v) == ["n", "aika", "kuka", "miksi", "teksti"] for r in data["kehotteet"] for v in r["versiot"])


# --- Käsikirjan versiot ja lukko (aiops ADR-0033 pala 6) ---------------------------------------------------------

def kaikki_lomakkeet(r) -> list[tuple[str, dict[str, str]]]:
    """[(polku, {kenttä: arvo})] sivun järjestyksessä: samaan osoitteeseen voi olla monta lomaketta (versiot)."""
    tulos = []
    for f in dom(r).find_all("form"):
        assert f["method"] == "post" and f["action"].startswith(f"https://{RP}/ilmari/")
        tulos.append((f["action"][len(f"https://{RP}"):],
                      {k["name"]: (k.get("value") or k.get_text()) for k in f.find_all(["input", "textarea", "select"])}))
    return tulos


def versiorivit(sivu: BeautifulSoup) -> list[str]:
    osio = sivu.find("section", attrs={"aria-labelledby": "h-versiot"})
    return [" ".join(li.find("div", class_="toimirivi").get_text(" ").split()) for li in osio.select("ol.versiot > li")]


def test_versiot_esimerkkitilassa():
    sivu = dom(asiakas().get("/hub/kehotteet/jarjestelma?demo=1"))
    assert " ".join(sivu.find(id="voimassa").get_text().split()).startswith("Voimassa: versio 4 · Ilmari · ")
    osio = sivu.find("section", attrs={"aria-labelledby": "h-versiot"})
    assert osio.find("h2").get_text() == "Aiemmat versiot"
    rivit = versiorivit(sivu)
    assert [r.split(" · ")[:2] for r in rivit] == [["Versio 4", "Ilmari"], ["Versio 3", "Elias"], ["Versio 2", "Ilmari"],
                                                  ["Versio 1", "alkuperäinen"]]
    assert rivit[0].endswith(" voimassa") and not any("voimassa" in r for r in rivit[1:])
    assert [r.endswith("Palauta") for r in rivit] == [False, True, True, True]   # voimassa olevaa ei palauteta
    kohdat = osio.select("ol.versiot > li")
    assert kohdat[0].find("p").get_text() == "Miksi: Raportit venyivät; lisäsin, mitä raporttiin kuuluu."
    assert kohdat[3].find("p") is None                                       # tyhjä perustelu: ei riviä
    teksti = kohdat[0].find("details", class_="fold")
    assert teksti.summary.get_text() == "Teksti (179 merkkiä)" and not teksti.find("div", class_="pre").find_all(True)
    assert osio.find("form") is None and [i["value"] for i in osio.find_all("input")] == ["3", "2", "1"]
    vuoro = dom(asiakas().get("/hub/kehotteet/vuoro?demo=1"))           # ei versioita: alkuperäinen voimassa, ei osiota
    assert vuoro.find(id="voimassa").get_text() == "Voimassa: alkuperäinen teksti"
    assert vuoro.find("section", attrs={"aria-labelledby": "h-versiot"}) is None
    kiintea = dom(asiakas().get("/hub/kehotteet/tyokalut?demo=1"))
    assert kiintea.find(id="voimassa") is None and kiintea.find("section", attrs={"aria-labelledby": "h-versiot"}) is None


def test_lukko_esimerkkitilassa():
    r = asiakas().get("/hub/kehotteet?demo=1")
    lukko = dom(r).find(id="lukko").parent
    assert lukko.find(id="lukko").get_text() == "Ilmari saa muokata käsikirjaansa ja vuoron ohjettaan."
    assert [b.get_text() for b in lukko.find_all("button")] == ["Lukitse"] and "<form" not in r.text


def test_tuotannossa_versioiden_palautus_ja_lukko_gatewaylle(tmp_path, monkeypatch):
    hak = kirjoita(julkaise(tmp_path / "toiminta"),
                   uusi(MUOKATTU | {"versiot": [V2, V1]}, KIINTEA, KADET, lukittu=False))
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    assert r.status_code == 200 and "Refresh" not in r.headers
    assert kaikki_lomakkeet(r) == [
        ("/ilmari/kehote/jarjestelma", {"paluu": "hub", "teksti": "Olet Ilmari. Vastaa lyhyesti."}),
        ("/ilmari/kehote/jarjestelma/oletus", {"paluu": "hub"}),
        ("/ilmari/kehote/jarjestelma/versio", {"paluu": "hub", "n": "1"})]
    sivu = dom(r)
    assert " ".join(sivu.find(id="voimassa").get_text().split()).startswith("Voimassa: versio 2 · Ilmari · ")
    assert [x.split(" · ")[:2] for x in versiorivit(sivu)] == [["Versio 2", "Ilmari"], ["Versio 1", "alkuperäinen"]]
    lista = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet")
    assert kaikki_lomakkeet(lista) == [("/ilmari/kehote/lukko", {"paluu": "hub", "lukittu": "1"})]
    assert dom(lista).find(id="lukko").get_text() == "Ilmari saa muokata käsikirjaansa ja vuoron ohjettaan."
    assert [b.get_text() for b in dom(lista).find_all("button")] == ["Lukitse"]
    kiintea = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/tyokalut")
    assert kaikki_lomakkeet(kiintea) == [] and "Aiemmat versiot" not in kiintea.text


def test_tuotannossa_lukittu_ja_sama_teksti(tmp_path, monkeypatch):
    """Lukittu: Avaa lähettää 0. Alkuperäinen voimassa (versio 3): sitä eikä samaa versiota 1 tarjota palautettavaksi."""
    hak = kirjoita(julkaise(tmp_path / "toiminta"), uusi(RIVI | {"versiot": [V3, V2, V1]}, KIINTEA, lukittu=True))
    lista = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet")
    assert kaikki_lomakkeet(lista) == [("/ilmari/kehote/lukko", {"paluu": "hub", "lukittu": "0"})]
    assert dom(lista).find(id="lukko").get_text() == "Lukittu: vain sinä muokkaat."
    assert [b.get_text() for b in dom(lista).find_all("button")] == ["Avaa"]
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    assert [f for f in kaikki_lomakkeet(r) if f[0].endswith("/versio")] == [
        ("/ilmari/kehote/jarjestelma/versio", {"paluu": "hub", "n": "2"})]
    rivit = versiorivit(dom(r))
    assert rivit[0].startswith("Versio 3 · Elias") and rivit[0].endswith(" voimassa")
    assert rivit[1].startswith("Versio 2 · Ilmari") and rivit[1].endswith("Palauta")
    assert rivit[2].startswith("Versio 1 · alkuperäinen") and rivit[2].endswith(" sama kuin voimassa")
    assert " ".join(dom(r).find(id="voimassa").get_text().split()).startswith("Voimassa: versio 3 · Elias · ")


def test_tuotannossa_vanha_muoto_ilman_versioita_ja_lukkoa(tmp_path, monkeypatch):
    hak = kirjoita(julkaise(tmp_path / "toiminta"), luettelo(MUOKATTU, KIINTEA, KADET))
    for polku in ("/kehotteet", "/kehotteet/jarjestelma"):
        r = tuotanto(tmp_path, monkeypatch, hak, polku=polku)
        sivu = dom(r)
        assert r.status_code == 200 and sivu.find(id="lukko") is None and sivu.find(id="voimassa") is None
        assert "Aiemmat versiot" not in r.text and not [f for f in kaikki_lomakkeet(r) if "lukko" in f[0] or "versio" in f[0]]


def test_tuotannossa_rikkinaiset_versiot_eivat_piilota_tekstia(tmp_path, monkeypatch):
    """Kielletty suunta: kelvoton versio (bidi-merkki perustelussa) ei näy, mutta teksti ja muokkaus toimivat."""
    paha = V2 | {"miksi": "suunta" + chr(0x202E) + "käännetty"}
    hak = kirjoita(julkaise(tmp_path / "toiminta"), uusi(MUOKATTU | {"versiot": [paha, V1]}, KIINTEA))
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    sivu = dom(r)
    assert r.status_code == 200 and chr(0x202E) not in r.text
    assert sivu.find("textarea").get_text() == MUOKATTU["teksti"]
    assert "Aiempia versioita ei voi nyt näyttää." in sivu.find("section", attrs={"aria-labelledby": "h-versiot"}).get_text()
    assert sivu.find(id="voimassa").get_text() == "Voimassa: muokattu teksti"
    assert [f[0] for f in kaikki_lomakkeet(r)] == ["/ilmari/kehote/jarjestelma", "/ilmari/kehote/jarjestelma/oletus"]
    lista = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet")
    assert lista.status_code == 200 and dom(lista).find(id="lukko") is not None


def test_ilmarin_teksti_versioissa_koodataan(tmp_path, monkeypatch):
    paha = V2 | {"miksi": "<b>lihava</b><script>alert(1)</script>",
                 "teksti": "</textarea></div><script>alert(2)</script><img src=x onerror=alert(3)>"}
    hak = kirjoita(julkaise(tmp_path / "toiminta"), uusi(MUOKATTU | {"versiot": [paha, V1]}, KIINTEA))
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/kehotteet/jarjestelma")
    assert r.status_code == 200 and "<script>" not in r.text and "<img" not in r.text and "<b>lihava" not in r.text
    assert "&lt;b&gt;lihava&lt;/b&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    kohta = dom(r).select("ol.versiot > li")[0]
    assert kohta.find("div", class_="pre").get_text() == paha["teksti"] and not kohta.find("div", class_="pre").find_all(True)
