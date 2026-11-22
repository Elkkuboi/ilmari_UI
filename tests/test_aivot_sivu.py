"""Aivojen koodi -sivu /hub/aivot (aiops ADR-0033 pala 7) Asetusten alla.

Sallittu suunta: mitkä aivot ovat käytössä, hätäjarru (Palauta alkuperäinen ja lukitse) heti sen alla, lukko,
asennusraja, vahdin viimeisin toimi, versiot uusin ensin (tulos, syy, muuttuneet tiedostot koon kanssa ja diff
taitettuna) ja pyynnöt. Tuotannossa lukko ja palautukset ovat lomakkeita gatewaylle (paluu=hub), esimerkkitilassa
napit ilman lomaketta. Turvallinen suunta (Lukitse, hätäjarru) on yksi napautus; Ilmarin koodin käyttöön vievät
toimet (Avaa lukko, Palauta edellinen) ovat taiton takana.

Kielletty suunta: kun itsepäivitys ei ole käytössä (tiedosto tai hakemisto puuttuu), ei lomakkeita; rikkinäinen,
väärän tyyppinen tai vieraan omistama tiedosto ei kaada sivua, ja lukko ja palautus näkyvät silti; tarpeeton tai jo
kesken oleva palautus ei näy; Ilmarin teksti on koodattua dataa, ja kielletty merkki piilottaa vain sen kentän.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

import ilmari_ui.app as app_moduuli
from ilmari_ui import aivot
from ilmari_ui.app import Settings, create_app, lyhyt_aika
from test_aivot import A_ID, AIKA, B_ID, C_ID, DIFF, PYYNTO, VERSIO_A, VERSIO_B, kirjoita, tila
from test_toiminta import OMAT, RP, tuotanto


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def dom(r) -> BeautifulSoup:
    return BeautifulSoup(r.text, "html.parser")


def lomakkeet(r, *, taitetut: bool | None = None) -> list[tuple[str, dict[str, str]]]:
    """[(action, {kenttä: arvo})] järjestyksessä; jokainen on POST gatewaylle, ja kaikki kentät ovat piilokenttiä.
    taitetut=False: vain yhden napautuksen lomakkeet (eivät taiton sisällä); True: vain taiton sisällä olevat."""
    tulos = []
    for f in dom(r).find_all("form"):
        assert f["method"] == "post" and f["action"].startswith(f"https://{RP}/ilmari/aivot/")
        kentat = f.find_all(["input", "textarea", "select"])
        assert all(k.name == "input" and k["type"] == "hidden" for k in kentat)
        if taitetut is None or (f.find_parent("details") is not None) is taitetut:
            tulos.append((f["action"][len(f"https://{RP}"):], {k["name"]: k["value"] for k in kentat}))
    return tulos


def taitto(r, tunniste: str) -> tuple[str, list[tuple[str, dict[str, str]]]] | None:
    """Taiton (details) otsikko ja sen lomakkeet, tai None."""
    d = dom(r).find("details", id=tunniste)
    if d is None:
        return None
    return d.summary.get_text(" ", strip=True), [
        (f["action"][len(f"https://{RP}"):], {k["name"]: k["value"] for k in f.find_all("input")}) for f in d.find_all("form")]


def jarjestys(r) -> list[str]:
    """Ensimmäisen osion tunnisteelliset osat järjestyksessä (hätäjarru ensin, sitten lukko ja muut)."""
    return [e["id"] for e in dom(r).find("section").find_all(id=True) if e.name != "h1"]


# Sivun kello: minuutti esimerkkitilan julkaisun (AIKA) jälkeen, joten tila on tuore. Vanhaa tilaa kokeillaan ajalla
# NYT - ikä. Kello vaikuttaa myös hätäjarruun (vanha tila ei ole tieto), joten oikeaa kelloa ei käytetä.
NYT = datetime.fromisoformat(AIKA) + timedelta(minutes=1)


def kello(hetki: datetime):
    class Kello(datetime):
        @classmethod
        def now(cls, tz=None):
            return hetki.astimezone(tz) if tz else hetki.replace(tzinfo=None)
    return Kello


def sivu(tmp_path, monkeypatch, data=None, *, omistajat=OMAT, nyt=NYT):
    """Tuotantotila kellolla nyt; data None = hakemistoa ei ole (itsepäivitys ei käytössä)."""
    hak = tmp_path / "aivot-julkaisu"
    if data is not None:
        kirjoita(hak, data)
    monkeypatch.setattr(aivot, "OLETUS", hak)
    monkeypatch.setattr(aivot, "OMISTAJAT", omistajat)
    monkeypatch.setattr(app_moduuli, "datetime", kello(nyt))
    return tuotanto(tmp_path, monkeypatch, tmp_path / "toiminta", polku="/aivot")


TEHDAS = {"versio": "tehdas", "aika": None, "kuka": None}
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
    assert [b.get_text() for b in s.find_all("button")] == ["Palauta alkuperäinen ja lukitse", "Lukitse",
                                                            "Vahvista: ota versio f1d58c2658bc käyttöön"]
    assert s.find(id="kaytossa").get_text(" ", strip=True) == ("Käytössä: Ilmarin versio 87478f15ae3a · "
                                                              + lyhyt_aika("2026-11-19T11:24:00+02:00"))
    assert jarjestys(r)[:4] == ["kaytossa", "palautus", "lukko", "asennuksia"]
    assert s.find(id="lukko").get_text() == "Ilmari saa ottaa oman koodinsa käyttöön."
    assert s.find(id="asennuksia").get_text() == "Asennuksia jäljellä 3/6 vuorokaudessa."
    assert s.find(id="vahti").get_text() == (
        f"Vahti {lyhyt_aika('2026-11-18T10:31:00+02:00')}: otti alkuperäisen käyttöön, hylkäsi version ja lukitsi "
        "(versio 8721ffde068e). Syy: palvelu on kaatunut (failed).")
    assert s.find(id="edellinen").summary.get_text(" ", strip=True) == "Palauta edellinen: Ilmarin versio f1d58c2658bc"
    assert s.find(id="avaa") is None
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
    assert taitot[0].find("pre").find_all("span")[-1].get_text() == "[diff katkaistu: yli 64 KiB]"
    assert uusin.find("p", class_="warn").get_text(" ", strip=True) == (
        "Muutokset katkesivat. Näitä ei ehditty verrata: kyvyt.py , rekisteri/kyvyt/haku.toml .")
    assert taitot[1].summary.get_text() == "Kaikki tiedostot (4)"            # muutoslista on vajaa
    assert hylatty.find("p", class_="small", string=lambda t: t and t.startswith("Syy: uusi versio ei ollut terve"))
    assert len(hylatty.find_all("details")) == 1                             # muutoslista on täydellinen
    assert hylatty.find("p", class_="warn") is None
    pyynnot = s.find("section", attrs={"aria-labelledby": "h-pyynnot"})
    assert pyynnot.details.summary.get_text() == "6 viimeisintä"
    assert "ehdokas hylätty: syntaksivirhe: ceo.py rivi 1: invalid syntax" in pyynnot.get_text()


def test_ilman_esimerkkitilaa_lahdetta_ei_ole():
    r = asiakas().get("/hub/aivot")
    assert r.status_code == 200 and "Aivojen tila ei ole saatavilla tässä ympäristössä." in r.text
    assert dom(r).find("button") is None and dom(r).select("h2.label") == []


def test_asetuksissa_linkki_aivojen_viereen():
    """Koko rivi on linkki (kosketuskohde), ei pieni tekstilinkki."""
    s = dom(asiakas().get("/hub/asetukset?demo=1"))
    linkki = s.find("section", id="aivot").select_one("div.rows > a")
    assert linkki["href"] == "/hub/aivot?demo=1"
    assert linkki.get_text(" ", strip=True) == "Aivojen koodi Ilmarin oma koodi, lukko ja palautus"
    assert dom(asiakas().get("/hub/asetukset")).find("section", id="aivot").select_one('div.rows > a[href="/hub/aivot"]')


# --- Tuotantotila ------------------------------------------------------------------------------------------------

def test_tuotannossa_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila())
    assert r.status_code == 200 and "Refresh" not in r.headers and "form-action 'self'" in r.headers["content-security-policy"]
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN]
    assert lomakkeet(r, taitetut=False) == [ALKUPERAINEN, LUKITSE]
    assert taitto(r, "edellinen") == ("Palauta edellinen: Ilmarin versio c3c3c3c3c3c3", [EDELLINEN])
    s = dom(r)
    assert s.find(id="kaytossa").get_text(" ", strip=True) == ("Käytössä: Ilmarin versio a1a1a1a1a1a1 · "
                                                              + lyhyt_aika(VERSIO_A["aika"]))
    assert [b.get_text() for b in s.find_all("button")] == ["Palauta alkuperäinen ja lukitse", "Lukitse",
                                                            "Vahvista: ota versio c3c3c3c3c3c3 käyttöön"]
    assert jarjestys(r) == ["kaytossa", "palautus", "lukko", "asennuksia", "vahti", "edellinen"]
    assert s.find("a", class_="back")["href"] == "/hub/asetukset#aivot"


def test_tuotannossa_lukittu_ja_avaus(tmp_path, monkeypatch):
    lukko = {"aika": "2026-11-21T10:31:00+02:00", "kuka": "vahti", "syy": "palvelu on kaatunut (failed)"}
    r = sivu(tmp_path, monkeypatch, tila(lukittu=True, lukko=lukko, asennuksia_24h=6, asennuksia_jaljella=0,
                                         asennukset_24h=[AIKA] * 6, seuraava_vapautuu="2026-11-22T10:00:00+02:00"))
    s = dom(r)
    assert lomakkeet(r) == [ALKUPERAINEN, AVAA, EDELLINEN] and lomakkeet(r, taitetut=False) == [ALKUPERAINEN]
    assert taitto(r, "avaa") == ("Avaa lukko", [AVAA])
    assert s.find(id="avaa").button.get_text() == "Vahvista: Ilmari saa taas ottaa koodinsa käyttöön"
    assert "vaikka lukko on päällä" in s.find(id="edellinen").get_text()          # lukko ei estä Eliaksen palautusta
    assert s.find(id="lukko").get_text() == "Lukittu: Ilmari ei voi ottaa omaa koodiaan käyttöön."
    assert s.find(id="lukitsija").get_text() == f"Lukitsi vahti {lyhyt_aika(lukko['aika'])}: palvelu on kaatunut (failed)"
    assert s.find(id="asennuksia").get_text() == (
        f"Asennuksia ei ole jäljellä (6 vuorokaudessa); seuraava vapautuu {lyhyt_aika('2026-11-22T10:00:00+02:00')}.")


def test_tuotannossa_alkuperainen_kaytossa_ei_turhia_palautuksia(tmp_path, monkeypatch):
    r = sivu(tmp_path, monkeypatch, tila(aktiivinen=TEHDAS, edellinen=None, versiot=[], pyynnot=[], vahti=None))
    s = dom(r)
    assert lomakkeet(r) == [LUKITSE] and s.find(id="palautus") is None and s.find(id="edellinen") is None
    assert s.find(id="kaytossa").get_text() == "Käytössä: alkuperäinen" and s.find(id="vahti") is None
    assert "Ilmari ei ole vielä ottanut omaa koodiaan käyttöön." in r.text and "Ei pyyntöjä." in r.text


def test_tuotannossa_kesken_paivittyy_ja_tarjoaa_palautuksen(tmp_path, monkeypatch):
    """Asennuksen aikana käytössä näkyy vielä alkuperäinen: palautus alkuperäiseen pitää silti olla tarjolla."""
    r = sivu(tmp_path, monkeypatch, tila(aktiivinen=TEHDAS, edellinen=None,
                                         kesken={"toimi": "asenna", "versio": B_ID, "aika": AIKA}))
    assert r.headers["refresh"] == "15" and lomakkeet(r) == [ALKUPERAINEN, LUKITSE]
    assert jarjestys(r)[:3] == ["kaytossa", "kesken", "palautus"]
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
    assert r.status_code == 200 and lomakkeet(r) == [ALKUPERAINEN, AVAA, EDELLINEN]
    assert lomakkeet(r, taitetut=False) == [ALKUPERAINEN]
    assert s.find("main").find("p", class_="empty").get_text() == "Aivojen tilaa ei voi lukea."
    miksi = s.find("main").find("details")
    assert miksi.summary.get_text() == "Miksi" and miksi.p.get_text() == "Tuntematon muoto."
    assert s.find(id="kaytossa") is None and s.select("h2.label") == [] and "refresh" not in r.headers
    assert taitto(r, "edellinen") == ("Palauta edellinen", [EDELLINEN])
    r = sivu(tmp_path, monkeypatch, b"{rikki")
    assert dom(r).find(id="lukko").get_text() == "Lukon tilaa ei voi lukea."
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, AVAA, EDELLINEN]
    assert lomakkeet(r, taitetut=False) == [ALKUPERAINEN, LUKITSE]


def test_tuotannossa_vieraan_omistama_tiedosto_ei_kelpaa(tmp_path, monkeypatch):
    """Tuotannossa vain root (asentaja) kelpaa omistajaksi: testin oma tiedosto hylätään, sisältöä ei näytetä."""
    r = sivu(tmp_path, monkeypatch, tila(versiot=[VERSIO_A | {"syy": "VIERAS TEKSTI"}]), omistajat=frozenset({0}))
    s = dom(r)
    assert r.status_code == 200 and "omistaja on väärä" in s.find("main").get_text()
    assert "VIERAS TEKSTI" not in r.text and s.find(id="lukko").get_text() == "Lukon tilaa ei voi lukea."
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, AVAA, EDELLINEN]


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
    assert chr(0x202E) not in r.text and lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN]
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
    assert r.status_code == 200 and lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN]
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
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE]
    assert dom(r).find(id="edellinen").get_text(" ", strip=True) == (
        "Edellinen: versio b2b2b2b2b2b2 · hylätty, ei palautettavissa")
    r = sivu(tmp_path, monkeypatch, tila(edellinen=B_ID, aktiivinen=TEHDAS))
    assert lomakkeet(r) == [LUKITSE] and dom(r).find(id="palautus") is None and dom(r).find(id="edellinen")
    r = sivu(tmp_path, monkeypatch, tila(edellinen=C_ID))               # C ei ole listalla: palautus tarjotaan
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN] and "hylätty" not in dom(r).find(id="edellinen").get_text()


def test_tuotannossa_vanha_tila_kerrotaan(tmp_path, monkeypatch):
    """Vahti julkaisee 2 min välein: yli 10 min vanha tila kerrotaan, tuore ei. Napit pysyvät molemmissa."""
    nyt = NYT
    for ika, vanha in ((timedelta(minutes=11), True), (timedelta(minutes=2), False), (timedelta(days=2), True)):
        r = sivu(tmp_path, monkeypatch, tila(aika=(nyt - ika).isoformat(timespec="seconds")))
        s = dom(r)
        assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN]
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
    assert [str(c) for c in pre.children if c.name != "span"] == []      # rivit ovat lohkoja, ei rivinvaihtoja välissä
    monkeypatch.setattr(aivot, "DIFF_RIVEJA_NAYTA", 15)
    assert "eivät mahdu" not in sivu(tmp_path, monkeypatch, tila()).text


# --- Katselmoinnin korjaukset 22.11.2026 ---------------------------------------------------------------------------

def test_tuotannossa_vanha_alkuperainen_tarjoaa_silti_hatajarrun(tmp_path, monkeypatch):
    """Asentaja asentaa, vaikka julkaisu epäonnistuisi: yli 10 min vanha "alkuperäinen" ei ole tieto. Tuoreena nappia
    ei tarjota (alkuperäinen on jo käytössä), vanhana tarjotaan."""
    nyt = NYT
    for ika, jarru in ((timedelta(hours=3), True), (timedelta(minutes=11), True), (timedelta(minutes=2), False)):
        r = sivu(tmp_path, monkeypatch, tila(aika=(nyt - ika).isoformat(timespec="seconds"), aktiivinen=TEHDAS,
                                             edellinen=None))
        assert lomakkeet(r) == ([ALKUPERAINEN, LUKITSE] if jarru else [LUKITSE])
        assert (dom(r).find(id="vanha") is not None) is jarru


def test_tuotannossa_ilmarin_koodiin_vievat_toimet_taiton_takana(tmp_path, monkeypatch):
    """Hätäjarrun jälkeen (alkuperäinen käytössä, lukittu) mikään yhden napautuksen nappi ei vie Ilmarin koodia
    takaisin: Avaa lukko ja Palauta edellinen ovat taiton takana, ja toinen napautus osuu eri kohtaan."""
    lukko = {"aika": AIKA, "kuka": "elias", "syy": "lukittu pyynnöstä"}
    r = sivu(tmp_path, monkeypatch, tila(aktiivinen=TEHDAS, edellinen=A_ID, lukittu=True, lukko=lukko))
    s = dom(r)
    assert lomakkeet(r, taitetut=False) == [] and s.find(id="palautus") is None
    assert not s.select("section > form button, section > .actions button, section > .toimirivi button")
    assert taitto(r, "avaa") == ("Avaa lukko", [AVAA])
    assert taitto(r, "edellinen") == ("Palauta edellinen: Ilmarin versio a1a1a1a1a1a1", [EDELLINEN])
    assert s.find(id="edellinen").button.get_text() == "Vahvista: ota versio a1a1a1a1a1a1 käyttöön"
    assert jarjestys(r) == ["kaytossa", "lukko", "lukitsija", "avaa", "asennuksia", "vahti", "edellinen"]
    assert s.find(id="lukitsija").get_text() == f"Lukitsi Elias {lyhyt_aika(AIKA)}"
    r = sivu(tmp_path, monkeypatch, tila())                             # auki: Lukitse yhdellä napautuksella
    assert lomakkeet(r, taitetut=False) == [ALKUPERAINEN, LUKITSE] and dom(r).find(id="avaa") is None
    assert "vaikka lukko" not in dom(r).find(id="edellinen").get_text()


def test_tuotannossa_kesken_oleva_palautus_ei_tarjoa_samaa_uudelleen(tmp_path, monkeypatch):
    """Toinen napautus jonottaisi uuden palautuksen ja käynnistäisi aivot uudelleen. Kesken olevaa palautusta ei
    tarjota; muut toimet näkyvät. Vanhana (huolto ei ehkä käynnissä) hätäjarru näkyy silti."""
    r = sivu(tmp_path, monkeypatch, tila(kesken={"toimi": "palauta_tehdas", "versio": "tehdas", "aika": AIKA}))
    assert r.headers["refresh"] == "15" and lomakkeet(r) == [LUKITSE, EDELLINEN]
    assert dom(r).find(id="kesken").get_text() == (f"Kesken: alkuperäisen palautus, alkoi {lyhyt_aika(AIKA)}. "
                                                   "Sivu päivittyy itsestään.")
    r = sivu(tmp_path, monkeypatch, tila(kesken={"toimi": "vahti", "versio": A_ID, "aika": AIKA}))
    assert lomakkeet(r) == [LUKITSE, EDELLINEN]
    r = sivu(tmp_path, monkeypatch, tila(kesken={"toimi": "palauta_edellinen", "versio": C_ID, "aika": AIKA}))
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE] and taitto(r, "edellinen") is None
    assert dom(r).find(id="edellinen").get_text(" ", strip=True) == "Edellinen: versio c3c3c3c3c3c3 · palautus kesken"
    vanha = (NYT - timedelta(minutes=30)).isoformat(timespec="seconds")
    r = sivu(tmp_path, monkeypatch, tila(aika=vanha, kesken={"toimi": "palauta_tehdas", "versio": "tehdas", "aika": vanha}))
    assert lomakkeet(r) == [ALKUPERAINEN, LUKITSE, EDELLINEN]


KAATAJAT = {
    "versio.tulos": dict(versiot=[VERSIO_A | {"tulos": []}, VERSIO_B]),
    "versio.tulos-olio": dict(versiot=[VERSIO_A | {"tulos": {}}, VERSIO_B]),
    "pyynto.toimi": dict(pyynnot=[PYYNTO | {"toimi": []}]),
    "pyynto.kuka": dict(pyynnot=[PYYNTO | {"kuka": ["elias"]}]),
    "pyynto.tulos": dict(pyynnot=[PYYNTO | {"tulos": []}]),
    "kesken.toimi": dict(kesken={"toimi": [], "versio": None, "aika": None}),
    "lukko.kuka": dict(lukittu=True, lukko={"aika": AIKA, "kuka": [], "syy": None}),
    "hunkki": dict(versiot=[VERSIO_A | {"diff": "--- tehdas/a.py\n+++ uusi/a.py\n@@ -1," + "9" * 5000 + " +1 @@\n x\n"}]),
}


@pytest.mark.parametrize("nimi", sorted(KAATAJAT))
def test_tuotannossa_vaara_tyyppi_ei_kaada_sivua(tmp_path, monkeypatch, nimi):
    """Ennen: 500 ilman turvaotsakkeita ja ilman hätäjarrua. Nyt sivu näkyy, ja vain kelvoton osa jää pois."""
    r = sivu(tmp_path, monkeypatch, tila(**KAATAJAT[nimi]))
    assert r.status_code == 200 and "script-src 'none'" in r.headers["content-security-policy"]
    assert lomakkeet(r)[0] == ALKUPERAINEN and dom(r).find(id="kaytossa")


def test_tuotannossa_odottamaton_virhe_nayttaa_lukon_ja_hatajarrun(tmp_path, monkeypatch):
    def kaatuu(data):
        raise RuntimeError("bugi")
    monkeypatch.setattr(aivot, "tarkista", kaatuu)
    r = sivu(tmp_path, monkeypatch, tila(lukittu=True))
    s = dom(r)
    assert r.status_code == 200 and s.find("main").find("p", class_="empty").get_text() == "Aivojen tilaa ei voi lukea."
    assert lomakkeet(r) == [ALKUPERAINEN, AVAA, EDELLINEN] and "bugi" not in r.text


def test_tuotannossa_katkaistu_diff_kertoo_vertaamatta_jaaneet(tmp_path, monkeypatch):
    """Katkaistusta diffistä jäävät pois aakkosissa myöhemmät tiedostot: ne luetellaan näkyvästi. Ehjästä ei."""
    katkaistu = VERSIO_A | {"diff": DIFF.split("--- /dev/null")[0] + "\n[diff katkaistu: yli 64 KiB]\n",
                            "diff_katkaistu": True}
    r = sivu(tmp_path, monkeypatch, tila(versiot=[katkaistu, VERSIO_B]))
    uusin, toinen = dom(r).select("ol.versiot > li")
    assert [li.code.get_text() for li in uusin.ul.find_all("li")] == ["ceo.py"]
    assert uusin.find("p", class_="warn").get_text(" ", strip=True) == "Muutokset katkesivat. Näitä ei ehditty verrata: kyvyt.py ."
    assert toinen.find("p", class_="warn") is None
    r = sivu(tmp_path, monkeypatch, tila())
    assert dom(r).select("ol.versiot > li")[0].find("p", class_="warn") is None


def test_tuotannossa_onnistuneen_palautuksen_kuittaus_jaa_pois(tmp_path, monkeypatch):
    """Terveystarkistuksen kuittaus (syke, prosessi) ei ole Eliakselle tietoa. Epäonnistunut tai poikkeava palautus
    näytetään."""
    def rivi(syy):
        return {"versio": "tehdas", "aika": AIKA, "kuka": "elias", "tulos": "palautettu", "syy": syy, "tiedostot": [],
                "diff": "", "diff_katkaistu": False, "varastossa": False, "hylatty": False}
    kuittaus = "tehdasversio käytössä: terve (syke käynnistyksen jälkeen, sama prosessi 60 s)"
    poikkeus = "versiota c3c3c3c3c3c3 ei voi käyttää (hylätty tai puuttuu); " + kuittaus
    huono = "tehdasversio ei ollut terve: palvelu kaatui (failed)"
    r = sivu(tmp_path, monkeypatch, tila(versiot=[rivi(kuittaus), rivi(poikkeus), rivi(huono),
                                                  VERSIO_A | {"tulos": "palautettu", "syy": "versio a1a1a1a1a1a1 käytössä: terve palvelun tilasta (sykettä ei ole; sama prosessi 60 s)"}]))
    tekstit = [li.get_text(" ", strip=True) for li in dom(r).select("ol.versiot > li")]
    assert "terve" not in tekstit[0] and "terve" not in tekstit[3]
    assert poikkeus in tekstit[1] and huono in tekstit[2]


def test_tuotannossa_nakymaton_merkki_ja_cr_diffissa(tmp_path, monkeypatch):
    """Vaihtelun valitsin näkyy diffissä koodina (eri muuttuja kuin ilman sitä); yksinäinen CR piilottaa diffin."""
    vs = VERSIO_A | {"diff": DIFF.replace("+X = 2\n", "+X" + chr(0xFE00) + " = 2\n")}
    cr = VERSIO_B | {"diff": VERSIO_B["diff"].replace("+RIKKI", "-X = 1" + chr(13) + "+RIKKI")}
    r = sivu(tmp_path, monkeypatch, tila(versiot=[vs, cr]))
    assert chr(0xFE00) not in r.text and chr(13) not in r.text
    uusin, toinen = dom(r).select("ol.versiot > li")
    assert "+X\\ufe00 = 2" in [sp.get_text() for sp in uusin.pre.find_all("span")]
    assert toinen.pre is None and "Muutoksia ei voi näyttää (kielletty merkki)." in toinen.get_text()


def test_diffin_laatikko_rajattu_ja_rivit_sisennetty():
    """Avattu 64 KiB:n diff ei ole kymmenien näyttöjen seinä, ja rivittyvä jatko sisennetään merkin alle."""
    css = (Path(aivot.__file__).parent / "static" / "app.css").read_text(encoding="utf-8")
    assert ".versiot pre.diff { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 70vh; overflow-y: auto; }" in css
    assert ".versiot pre.diff > span { display: block; padding-left: 1ch; text-indent: -1ch; min-height: 1.5em; }" in css
