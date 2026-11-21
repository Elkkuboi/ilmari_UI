"""Aivojen koodi -sivu /hub/aivot (aiops ADR-0033 pala 7) Asetusten alla.

Sallittu suunta: mitkä aivot ovat käytössä, lukko yhdellä napilla, asennusraja, vahdin viimeisin toimi, versiot
uusin ensin (tulos, syy, muuttuneet tiedostot koon kanssa ja diff taitettuna) ja pyynnöt. Tuotannossa lukko ja
palautukset ovat lomakkeita gatewaylle (paluu=hub), esimerkkitilassa napit ilman lomaketta.

Kielletty suunta: kun itsepäivitys ei ole käytössä (tiedosto tai hakemisto puuttuu), ei lomakkeita; rikkinäinen tai
vieraan omistama tiedosto ei kaada sivua, ja lukko ja palautus näkyvät silti; tarpeeton palautusnappi ei näy; Ilmarin
teksti on koodattua dataa, ja kielletty merkki piilottaa vain sen kentän.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui import aivot
from ilmari_ui.app import Settings, create_app, lyhyt_aika
from test_aivot import A_ID, AIKA, B_ID, C_ID, DIFF, PYYNTO, VERSIO_A, VERSIO_B, kirjoita, tila
from test_toiminta import OMAT, RP, tuotanto


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def dom(r) -> BeautifulSoup:
    return BeautifulSoup(r.text, "html.parser")


def lomakkeet(r) -> list[tuple[str, dict[str, str]]]:
    """[(action, {kenttä: arvo})] järjestyksessä; jokainen on POST gatewaylle, ja kaikki kentät ovat piilokenttiä."""
    tulos = []
    for f in dom(r).find_all("form"):
        assert f["method"] == "post" and f["action"].startswith(f"https://{RP}/ilmari/aivot/")
        kentat = f.find_all(["input", "textarea", "select"])
        assert all(k.name == "input" and k["type"] == "hidden" for k in kentat)
        tulos.append((f["action"][len(f"https://{RP}"):], {k["name"]: k["value"] for k in kentat}))
    return tulos


def sivu(tmp_path, monkeypatch, data=None, *, omistajat=OMAT):
    """Tuotantotila; data None = hakemistoa ei ole (itsepäivitys ei käytössä)."""
    hak = tmp_path / "aivot-julkaisu"
    if data is not None:
        kirjoita(hak, data)
    monkeypatch.setattr(aivot, "OLETUS", hak)
    monkeypatch.setattr(aivot, "OMISTAJAT", omistajat)
    return tuotanto(tmp_path, monkeypatch, tmp_path / "toiminta", polku="/aivot")


LUKITSE = ("/ilmari/aivot/lukko", {"paluu": "hub", "lukittu": "1"})
AVAA = ("/ilmari/aivot/lukko", {"paluu": "hub", "lukittu": "0"})
EDELLINEN = ("/ilmari/aivot/palauta", {"paluu": "hub", "kohde": "edellinen"})
ALKUPERAINEN = ("/ilmari/aivot/palauta", {"paluu": "hub", "kohde": "tehdas", "lukitse": "1"})


# --- Esimerkkitila -----------------------------------------------------------------------------------------------

def test_sivu_esimerkkitilassa():
    r = asiakas().get("/hub/aivot?demo=1")
    s = dom(r)
    assert r.status_code == 200 and "refresh" not in r.headers and s.title.get_text() == "Aivojen koodi · Ilmari"
    assert s.find("a", class_="back")["href"] == "/hub/asetukset?demo=1#aivot"
    assert [a.get_text() for a in s.select('nav a[aria-current="page"]')] == ["Asetukset"]
    assert s.find("form") is None                                   # napit eivät tee mitään esimerkkitilassa
    assert s.find(id="vanha") is None and "warn" not in s.find("h1").span["class"]
    assert [b.get_text() for b in s.find_all("button")] == ["Lukitse", "Palauta edellinen",
                                                            "Palauta alkuperäinen ja lukitse"]
    assert s.find(id="kaytossa").get_text(" ", strip=True) == ("Käytössä: Ilmarin versio 87478f15ae3a · "
                                                              + lyhyt_aika("2026-11-19T11:24:00+02:00"))
    assert s.find(id="lukko").get_text() == "Ilmari saa ottaa oman koodinsa käyttöön."
    assert s.find(id="asennuksia").get_text() == "Asennuksia jäljellä 3/6 vuorokaudessa."
    assert s.find(id="vahti").get_text() == (
        f"Vahti {lyhyt_aika('2026-11-18T10:31:00+02:00')}: otti alkuperäisen käyttöön, hylkäsi version ja lukitsi "
        "(versio 8721ffde068e). Syy: palvelu on kaatunut (failed).")
    assert s.find(id="edellinen").get_text(" ", strip=True) == "Edellinen: versio f1d58c2658bc"
    rivit = s.select("ol.versiot > li")
    ajat = [lyhyt_aika(f"2026-11-{p}:00+02:00") for p in ("19T11:24", "19T10:51", "19T10:00", "18T10:31", "18T10:00")]
    assert [r.find("div").get_text(" ", strip=True) for r in rivit] == [
        f"{ajat[0]} · asennus · Ilmari käytössä", f"{ajat[1]} · asennus · Ilmari hylätty",
        f"{ajat[2]} · asennus · Ilmari edellinen", f"{ajat[3]} · vahti poisti käytöstä hylätty",
        f"{ajat[4]} · asennus · Ilmari hylätty myöhemmin"]
    uusin, hylatty = rivit[0], rivit[1]
    assert [li.get_text(" ", strip=True) for li in uusin.find("ul").find_all("li")] == [
        "ceo.py +2 −2 · 175 tavua", "ceo_masterprompt.md +26 −0 · 88,3 kt"]
    assert "terve (syke" not in uusin.get_text()                             # onnistuneen asennuksen kuittaus pois
    taitot = uusin.find_all("details")
    assert taitot[0].summary.get_text() == "Muutokset alkuperäiseen (+28 −2 riviä, katkaistu)"
    assert taitot[0].find("pre").get_text().endswith("[diff katkaistu: yli 64 KiB]\n")
    assert taitot[1].summary.get_text() == "Kaikki tiedostot (4)"            # muutoslista on vajaa
    assert hylatty.find("p", class_="small", string=lambda t: t and t.startswith("Syy: uusi versio ei ollut terve"))
    assert len(hylatty.find_all("details")) == 1                             # muutoslista on täydellinen
    pyynnot = s.find("section", attrs={"aria-labelledby": "h-pyynnot"})
    assert pyynnot.details.summary.get_text() == "6 viimeisintä"
    assert "ehdokas hylätty: syntaksivirhe: ceo.py rivi 1: invalid syntax" in pyynnot.get_text()


def test_ilman_esimerkkitilaa_lahdetta_ei_ole():
    r = asiakas().get("/hub/aivot")
    assert r.status_code == 200 and "Aivojen tila ei ole saatavilla tässä ympäristössä." in r.text
    assert dom(r).find("button") is None and dom(r).select("h2.label") == []


def test_asetuksissa_linkki_aivojen_viereen():
    s = dom(asiakas().get("/hub/asetukset?demo=1"))
    aivo = s.find("section", id="aivot")
    assert aivo.find("a", href="/hub/aivot?demo=1").get_text() == "Aivojen koodi"
    assert dom(asiakas().get("/hub/asetukset")).find("section", id="aivot").find("a", href="/hub/aivot")


# --- Tuotantotila ------------------------------------------------------------------------------------------------

def test_tuotannossa_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila())
    assert r.status_code == 200 and "Refresh" not in r.headers and "form-action 'self'" in r.headers["content-security-policy"]
    assert lomakkeet(r) == [LUKITSE, EDELLINEN, ALKUPERAINEN]
    s = dom(r)
    assert s.find(id="kaytossa").get_text(" ", strip=True) == ("Käytössä: Ilmarin versio a1a1a1a1a1a1 · "
                                                              + lyhyt_aika(VERSIO_A["aika"]))
    assert [b.get_text() for b in s.find_all("button")] == ["Lukitse", "Palauta edellinen",
                                                            "Palauta alkuperäinen ja lukitse"]
    assert s.find("a", class_="back")["href"] == "/hub/asetukset#aivot"


def test_tuotannossa_lukittu_ja_avaus(tmp_path, monkeypatch):
    lukko = {"aika": "2026-11-21T10:31:00+02:00", "kuka": "vahti", "syy": "palvelu on kaatunut (failed)"}
    r = sivu(tmp_path, monkeypatch, tila(lukittu=True, lukko=lukko, asennuksia_24h=6, asennuksia_jaljella=0,
                                         asennukset_24h=[AIKA] * 6, seuraava_vapautuu="2026-11-22T10:00:00+02:00"))
    s = dom(r)
    assert lomakkeet(r) == [AVAA, EDELLINEN, ALKUPERAINEN]
    assert s.find(id="lukko").get_text() == "Lukittu: Ilmari ei voi ottaa omaa koodiaan käyttöön."
    assert s.find(id="lukitsija").get_text() == f"Lukitsi vahti {lyhyt_aika(lukko['aika'])}: palvelu on kaatunut (failed)"
    assert s.find(id="asennuksia").get_text() == (
        f"Asennuksia ei ole jäljellä (6 vuorokaudessa); seuraava vapautuu {lyhyt_aika('2026-11-22T10:00:00+02:00')}.")


def test_tuotannossa_alkuperainen_kaytossa_ei_turhia_palautuksia(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila(aktiivinen={"versio": "tehdas", "aika": None, "kuka": None}, edellinen=None,
                                         versiot=[], pyynnot=[], vahti=None))
    s = dom(r)
    assert lomakkeet(r) == [LUKITSE]
    assert s.find(id="kaytossa").get_text() == "Käytössä: alkuperäinen" and s.find(id="vahti") is None
    assert "Ilmari ei ole vielä ottanut omaa koodiaan käyttöön." in r.text and "Ei pyyntöjä." in r.text


def test_tuotannossa_kesken_paivittyy_ja_tarjoaa_palautuksen(tmp_path, monkeypatch):
    """Asennuksen aikana käytössä näkyy vielä alkuperäinen: palautus alkuperäiseen pitää silti olla tarjolla."""
    r = sivu(tmp_path, monkeypatch, tila(aktiivinen={"versio": "tehdas", "aika": None, "kuka": None}, edellinen=None,
                                         kesken={"toimi": "asenna", "versio": B_ID, "aika": AIKA}))
    assert r.headers["refresh"] == "15" and lomakkeet(r) == [LUKITSE, ALKUPERAINEN]
    assert dom(r).find(id="kesken").get_text() == (f"Kesken: asennus (versio b2b2b2b2b2b2), alkoi {lyhyt_aika(AIKA)}. "
                                                   "Sivu päivittyy itsestään.")
    r = sivu(tmp_path, monkeypatch, tila(kesken={"toimi": "?"}))
    assert r.headers["refresh"] == "15"
    assert dom(r).find(id="kesken").get_text() == "Kesken: tuntematon toimi. Sivu päivittyy itsestään."


def test_tuotannossa_ei_kaytossa_ei_lomakkeita(tmp_path, monkeypatch):
    for data in (None, False):
        if data is False:
            (tmp_path / "aivot-julkaisu").mkdir()                  # hakemisto on, tiedostoa ei vielä
        r = sivu(tmp_path, monkeypatch, None)
        s = dom(r)
        assert r.status_code == 200 and lomakkeet(r) == [] and s.find("button") is None
        assert s.find("main").find("p", class_="empty").get_text() == "Itsepäivitys ei ole käytössä tällä koneella."
        assert s.select("h2.label") == [] and "refresh" not in r.headers


def test_tuotannossa_rikkinainen_tiedosto_nayttaa_lukon_ja_palautuksen(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila(muoto="aiops-aivot-tila-v9", lukittu=True))
    s = dom(r)
    assert r.status_code == 200 and lomakkeet(r) == [AVAA, EDELLINEN, ALKUPERAINEN]
    assert s.find("main").find("p", class_="empty").get_text() == "Aivojen tilaa ei voi lukea."
    miksi = s.find("main").find("details")
    assert miksi.summary.get_text() == "Miksi" and miksi.p.get_text() == "Tuntematon muoto."
    assert s.find(id="kaytossa") is None
    assert s.select("h2.label") == [] and "refresh" not in r.headers
    r = sivu(tmp_path, monkeypatch, b"{rikki")
    assert dom(r).find(id="lukko").get_text() == "Lukon tilaa ei voi lukea."
    assert lomakkeet(r) == [LUKITSE, AVAA, EDELLINEN, ALKUPERAINEN]


def test_tuotannossa_vieraan_omistama_tiedosto_ei_kelpaa(tmp_path, monkeypatch):
    """Tuotannossa vain root (asentaja) kelpaa omistajaksi: testin oma tiedosto hylätään, sisältöä ei näytetä."""
    r = sivu(tmp_path, monkeypatch, tila(versiot=[VERSIO_A | {"syy": "VIERAS TEKSTI"}]), omistajat=frozenset({0}))
    s = dom(r)
    assert r.status_code == 200 and "omistaja on väärä" in s.find("main").get_text()
    assert "VIERAS TEKSTI" not in r.text and s.find(id="lukko").get_text() == "Lukon tilaa ei voi lukea."
    assert lomakkeet(r) == [LUKITSE, AVAA, EDELLINEN, ALKUPERAINEN]


def test_tuotannossa_ilmarin_teksti_on_koodattua_dataa(tmp_path, monkeypatch):
    paha = "<script>alert(1)</script>"
    diff = DIFF.replace("+X = 2", "+X = '<img src=x onerror=alert(1)>'")
    tiedostot = [{"polku": "ceo.py", "koko": 110}, {"polku": "<b>kyvyt</b>.py", "koko": 1}]
    r = sivu(tmp_path, monkeypatch, tila(versiot=[VERSIO_B | {"syy": paha, "diff": diff, "tiedostot": tiedostot}],
                                         pyynnot=[PYYNTO | {"syy": paha}],
                                         vahti={"aika": AIKA, "syy": paha, "versio": C_ID, "toimi": paha,
                                                "uudelleenkaynnistys": paha}))
    assert r.status_code == 200 and "<script>" not in r.text and "<img" not in r.text and "<b>kyvyt" not in r.text
    assert r.text.count("&lt;script&gt;alert(1)&lt;/script&gt;") == 5 and "&lt;img src=x onerror=alert(1)&gt;" in r.text
    s = dom(r)
    assert s.find("script") is None and s.find("img") is None and not s.select("pre.diff b, pre.diff img")
    assert s.find(id="vahti").get_text(" ", strip=True).endswith(f"Uudelleenkäynnistys: {paha}.")


def test_tuotannossa_kielletty_merkki_piilottaa_vain_kentan(tmp_path, monkeypatch):
    """Ilmari ei voi piilottaa versiotaan, syytä tai nappeja kielletyllä merkillä: vain kenttä jää pois."""
    bidi = "x" + chr(0x202E) + "y"
    tiedostot = [{"polku": "ceo.py", "koko": 110}, {"polku": "a" + bidi + ".py", "koko": 3}]
    r = sivu(tmp_path, monkeypatch, tila(versiot=[VERSIO_A | {"syy": bidi, "diff": DIFF + "+" + bidi + "\n",
                                                              "diff_katkaistu": True, "tiedostot": tiedostot},
                                                  VERSIO_B],
                                         pyynnot=[PYYNTO | {"syy": bidi}]))
    assert chr(0x202E) not in r.text and lomakkeet(r) == [LUKITSE, EDELLINEN, ALKUPERAINEN]
    uusin, toinen = dom(r).select("ol.versiot > li")
    teksti = uusin.get_text(" ", strip=True)
    assert "Syy ei voi näyttää (kielletty merkki)." in teksti and "Muutoksia ei voi näyttää (kielletty merkki)." in teksti
    assert "käytössä" in uusin.find("div").get_text() and uusin.find("pre") is None
    assert [li.get_text(" ", strip=True) for li in uusin.find("details").find_all("li")] == [
        "ceo.py · 110 tavua", "nimi ei voi näyttää (kielletty merkki) · 3 tavua"]
    assert toinen.find("pre") is not None and "Syy: uusi versio ei ollut terve" in toinen.get_text()
    assert "Syy ei voi näyttää (kielletty merkki)." in dom(r).find("section", attrs={"aria-labelledby": "h-pyynnot"}).get_text()


def test_tuotannossa_kelvoton_rivi_ei_piilota_muita(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila(versiot=[VERSIO_A | {"tulos": "tuntematon"}, VERSIO_B],
                                         pyynnot=["x", PYYNTO], aktiivinen={"versio": "?"}))
    s = dom(r)
    assert r.status_code == 200 and lomakkeet(r) == [LUKITSE, EDELLINEN, ALKUPERAINEN]
    assert s.find(id="kaytossa").get_text() == "Käytössä: ei voi näyttää"
    rivit = s.select("ol.versiot > li")
    assert rivit[0].get_text(strip=True) == "Tätä riviä ei voi näyttää." and "hylätty" in rivit[1].find("div").get_text()
    pyynnot = s.find("section", attrs={"aria-labelledby": "h-pyynnot"}).select("ol > li")
    assert pyynnot[0].get_text(strip=True) == "Tätä pyyntöä ei voi näyttää." and "asennettu" in pyynnot[1].get_text()


def test_tuotannossa_vanhoja_ja_poistettuja_versioita(tmp_path, monkeypatch):
    karsittu = VERSIO_A | {"versio": B_ID, "diff": "", "diff_katkaistu": True}
    poistettu = VERSIO_A | {"versio": C_ID, "diff": "", "tiedostot": [], "varastossa": False}
    sama = VERSIO_A | {"diff": ""}
    r = sivu(tmp_path, monkeypatch, tila(versiot=[sama, karsittu, poistettu]))
    tekstit = [li.get_text(" ", strip=True) for li in dom(r).select("ol.versiot > li")]
    assert "Sama kuin alkuperäinen." in tekstit[0]
    assert "Muutokset eivät mahtuneet tähän." in tekstit[1] and "Kaikki tiedostot (2)" in tekstit[1]
    assert "Versiota ei ole enää tallessa." in tekstit[2]
    assert A_ID[:12] in tekstit[0] and Path(__file__).name not in r.text


def test_tuotannossa_hylattya_edellista_ei_tarjota(tmp_path, monkeypatch):
    """Asentaja hylkää palautuksen hylättyyn versioon: nappia ei näytetä, ja rivi kertoo syyn. Alkuperäinen jää."""
    r = sivu(tmp_path, monkeypatch, tila(edellinen=B_ID))
    assert lomakkeet(r) == [LUKITSE, ALKUPERAINEN]
    assert dom(r).find(id="edellinen").get_text(" ", strip=True) == (
        "Edellinen: versio b2b2b2b2b2b2 · hylätty, ei palautettavissa")
    r = sivu(tmp_path, monkeypatch, tila(edellinen=B_ID, aktiivinen={"versio": "tehdas", "aika": None, "kuka": None}))
    assert lomakkeet(r) == [LUKITSE] and dom(r).find(id="palautus") is None and dom(r).find(id="edellinen")
    r = sivu(tmp_path, monkeypatch, tila(edellinen=C_ID))               # C ei ole listalla: palautus tarjotaan
    assert lomakkeet(r) == [LUKITSE, EDELLINEN, ALKUPERAINEN] and "hylätty" not in dom(r).find(id="edellinen").get_text()


def test_tuotannossa_vanha_tila_kerrotaan(tmp_path, monkeypatch):
    """Vahti julkaisee 2 min välein: yli 10 min vanha tila kerrotaan, tuore ei. Napit pysyvät molemmissa."""
    nyt = datetime.now(timezone.utc)
    for ika, vanha in ((timedelta(minutes=11), True), (timedelta(minutes=2), False), (timedelta(days=2), True)):
        r = sivu(tmp_path, monkeypatch, tila(aika=(nyt - ika).isoformat(timespec="seconds")))
        s = dom(r)
        assert lomakkeet(r) == [LUKITSE, EDELLINEN, ALKUPERAINEN]
        assert ("warn" in s.find("h1").span["class"]) is vanha
        if vanha:
            assert s.find(id="vanha").get_text() == "Tieto on yli 10 min vanha: aivojen huolto ei ehkä ole käynnissä."
        else:
            assert s.find(id="vanha") is None
    r = sivu(tmp_path, monkeypatch, tila(muoto="x", aika=(nyt - timedelta(days=2)).isoformat()))
    assert dom(r).find(id="vanha") is None                              # rikkinäisestä ei väitetä mitään


def test_tuotannossa_pitka_diff_kertoo_leikatut_rivit(tmp_path, monkeypatch):
    monkeypatch.setattr(aivot, "DIFF_RIVEJA_NAYTA", 5)
    pre = dom(sivu(tmp_path, monkeypatch, tila())).select("ol.versiot > li")[0].find("pre")
    assert len(pre.find_all("span")) == 6 and pre.find_all("span")[-1].get_text() == (
        "[… loput 10 riviä eivät mahdu tähän …]")
    monkeypatch.setattr(aivot, "DIFF_RIVEJA_NAYTA", 15)
    assert "eivät mahdu" not in sivu(tmp_path, monkeypatch, tila()).text
