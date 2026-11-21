"""Keskustelu Hubissa (28.10.): lukija ja sivu; lomake gatewaylle vain tuotannossa."""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui.app import PACKAGE_DIR, Settings, create_app
from ilmari_ui.config import parse_config
from ilmari_ui.keskustelu import ESIMERKKI, lue_keskustelu

UID = os.getuid()


def julkaise(hak: Path, data=None, raaka=None) -> Path:
    hak.mkdir(parents=True, exist_ok=True)
    data = data if data is not None else {"muoto": "aiops-keskustelu-v1", "paivitetty": "2026-10-28T20:00:00+00:00",
                                          "viimeisin": 2, "malli": {"tila": "running", "tila_teksti": "käynnissä", "tyo": 5},
                                          "viestit": [{"id": 1, "aika": "2026-10-28T19:00:00+00:00", "lahettaja": "elias", "teksti": "hei"},
                                                      {"id": 2, "aika": "2026-10-28T19:00:05+00:00", "lahettaja": "ilmari", "teksti": "Hei!\x07"}]}
    (hak / "viestit.json").write_bytes(raaka if raaka is not None else json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return hak


def test_lukija(tmp_path):
    k = lue_keskustelu(julkaise(tmp_path / "k"), omistajat=frozenset({UID}))
    assert k.tila == "ready" and k.viimeisin == 2 and k.malli["tila"] == "running" and k.malli["tyo"] == 5
    assert [(v["nimi"], v["teksti"]) for v in k.viestit] == [("Elias", "hei"), ("Ilmari", "Hei!")]
    assert lue_keskustelu(tmp_path / "ei", omistajat=frozenset({UID})).tila == "not_published"
    assert lue_keskustelu(tmp_path / "k", omistajat=frozenset({UID + 1})).tila == "error"
    assert lue_keskustelu(julkaise(tmp_path / "r", raaka=b"{ei"), omistajat=frozenset({UID})).tila == "error"
    assert lue_keskustelu(julkaise(tmp_path / "x", data={"muoto": "x"}), omistajat=frozenset({UID})).tila == "error"
    assert lue_keskustelu(ESIMERKKI).tila == "ready"


def test_sivu_esimerkkitilassa_ilman_lomaketta():
    c = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)
    r = c.get("/hub/keskustelu?demo=1")
    assert r.status_code == 200 and "Mitä olen syönyt tänään?" in r.text and "&lt;b&gt;ei html&lt;/b&gt;" in r.text
    assert 'action="' not in r.text and "<form" not in r.text and "Refresh" not in r.headers
    # kenttä on aina näkyvissä viestilaatikon alla (21.11.2026): hyppylinkkiä kenttään ei enää ole
    assert 'id="viesti"' in r.text and "#viesti" not in r.text and "↓ Kirjoita" not in r.text
    # Hub juureksi (18.11.2026): selityspaneelit pois
    assert "Näin viesti etenee" not in r.text and "Kokeile" not in r.text and "<svg" not in r.text
    r = c.get("/hub/keskustelu")
    assert r.status_code == 200 and "Keskustelu ei ole saatavilla" in r.text and 'id="viesti"' not in r.text


def test_tuotannossa_lomake_gatewaylle(tmp_path):
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/keskustelu", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                               "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    assert r.status_code == 200 and 'action="https://tyoasema.test/ilmari/viesti"' in r.text
    assert 'name="paluu" value="hub"' in r.text and "refresh" not in r.headers   # kenttä näkyy: ei päivitystä
    assert "form-action 'self'" in r.headers["content-security-policy"]


# --- Säikeet (aiops ADR-0031, 3.11.2026) -------------------------------------------------------------------

V2 = {"muoto": "aiops-keskustelu-v2", "paivitetty": "2026-11-03T20:00:00+00:00", "viimeisin": 9,
      "malli": {"tila": None, "tila_teksti": "ei käynnissä", "tyo": None, "dsh_tyo": None, "yoajo": False},
      "saie": {"id": 2, "nimi": "Kuvareitti\x07 uusiksi", "kansio": "Ravintopolku", "nimen_lahde": "alustava",
               "luotu": "2026-11-03T19:00:00+00:00", "arkistoitu": None, "kanava": "sovellus"},
      "viestit": [{"id": 9, "aika": "2026-11-03T19:00:05+00:00", "lahettaja": "elias", "teksti": "hei", "saie": 2}]}
SAIKEET = {"muoto": "aiops-saikeet-v1", "paivitetty": "2026-11-03T20:00:00+00:00", "aktiivinen": 2, "saikeet": [
    {"id": 2, "nimi": "Kuvareitti uusiksi", "kansio": "Ravintopolku", "nimen_lahde": "alustava", "luotu": "2026-11-03T19:00:00+00:00",
     "arkistoitu": None, "kanava": "sovellus", "viesteja": 1, "viimeisin": "2026-11-03T19:00:05+00:00"},
    {"id": 3, "nimi": "b-kansio", "kansio": "beta", "nimen_lahde": "elias", "luotu": "2026-11-03T18:00:00+00:00",
     "arkistoitu": None, "kanava": "sovellus", "viesteja": 0, "viimeisin": None},
    {"id": 1, "nimi": "Aiemmat keskustelut", "kansio": "", "nimen_lahde": "elias", "luotu": "2026-10-20T20:00:00+00:00",
     "arkistoitu": None, "kanava": "sovellus", "viesteja": 240, "viimeisin": "2026-11-01T10:00:00+00:00"},
    {"id": 4, "nimi": "vanha", "kansio": "", "nimen_lahde": "elias", "luotu": "2026-10-20T20:00:00+00:00",
     "arkistoitu": "2026-11-02T10:00:00+00:00", "kanava": "sovellus", "viesteja": 3, "viimeisin": "2026-10-21T10:00:00+00:00"}]}


def test_lukija_v2_ja_saikeet(tmp_path):
    hak = julkaise(tmp_path / "k", data=V2)
    (hak / "saikeet.json").write_text(json.dumps(SAIKEET, ensure_ascii=False), encoding="utf-8")
    k = lue_keskustelu(hak, omistajat=frozenset({UID}))
    assert k.tila == "ready" and k.saie["id"] == 2 and k.saie["nimi"] == "Kuvareitti uusiksi" and k.aktiivinen == 2
    assert [s["id"] for s in k.saikeet] == [2, 3, 1, 4]
    assert [(kansio, [s["id"] for s in lista]) for kansio, lista in k.kansiot] == [("", [1]), ("beta", [3]), ("Ravintopolku", [2])]
    assert [s["id"] for s in k.arkistoidut] == [4] and k.kansionimet == ["beta", "Ravintopolku"]
    # v2 ilman säielistaa (vanhempi julkaisu tai lista puuttuu): keskustelu näkyy silti
    k2 = lue_keskustelu(julkaise(tmp_path / "k2", data=V2), omistajat=frozenset({UID}))
    assert k2.tila == "ready" and k2.saie["id"] == 2 and k2.saikeet == () and k2.aktiivinen == 2
    # rikkinäinen säielista ei kaada keskustelua; v1 ilman säiettä toimii kuten ennen
    hak3 = julkaise(tmp_path / "k3", data=V2)
    (hak3 / "saikeet.json").write_text("{ei", encoding="utf-8")
    assert lue_keskustelu(hak3, omistajat=frozenset({UID})).tila == "error"
    k4 = lue_keskustelu(julkaise(tmp_path / "k4"), omistajat=frozenset({UID}))
    assert k4.tila == "ready" and k4.saie is None and k4.kansiot == []
    # kielletyt suunnat: v2 ilman saie-kenttää, viesti ilman säiettä v2:ssa, v1 jossa saie
    assert lue_keskustelu(julkaise(tmp_path / "x1", data={k: v for k, v in V2.items() if k != "saie"}), omistajat=frozenset({UID})).tila == "error"
    assert lue_keskustelu(julkaise(tmp_path / "x2", data={**V2, "viestit": [{"id": 9, "aika": "", "lahettaja": "elias", "teksti": "x"}]}),
                          omistajat=frozenset({UID})).tila == "error"
    assert lue_keskustelu(julkaise(tmp_path / "x3", data={**V2, "muoto": "aiops-keskustelu-v1"}), omistajat=frozenset({UID})).tila == "error"


def test_saiesivu_tuotannossa_ja_esimerkkitilassa(tmp_path, monkeypatch):
    """Keskustelussa Uusi keskustelu ja linkki listaan; säikeiden vaihto, nimi, kansio ja arkisto ovat listassa
    (?lista=1, 21.11.2026)."""
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    root = tmp_path / "ajot"
    root.mkdir()
    hak = julkaise(tmp_path / "ajot" / "keskustelu", data=V2)
    (hak / "saikeet.json").write_text(json.dumps(SAIKEET, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", hak)
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None) as client:
        r = client.get("/keskustelu", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                               "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
        lista = client.get("/keskustelu?lista=1", headers=OTSAKKEET)
    assert r.status_code == 200 and 'action="https://tyoasema.test/ilmari/saie"' in r.text and "+ Uusi keskustelu" in r.text
    assert BeautifulSoup(r.text, "html.parser").find("a", string="Keskustelut (3)")["href"] == "/hub/keskustelu?lista=1"
    assert "/valitse" not in r.text and "/nimea" not in r.text and "/arkistoi" not in r.text and "Arkisto (1)" not in r.text
    assert lista.status_code == 200
    for osa in ('action="https://tyoasema.test/ilmari/saie"', 'action="https://tyoasema.test/ilmari/saie/1/valitse"',
                'action="https://tyoasema.test/ilmari/saie/2/nimea"', 'action="https://tyoasema.test/ilmari/saie/2/kansio"',
                'action="https://tyoasema.test/ilmari/saie/2/arkistoi"', 'action="https://tyoasema.test/ilmari/saie/4/palauta"',
                "+ Uusi keskustelu", "Arkisto (1)", "Ravintopolku", "Aiemmat keskustelut", 'value="Kuvareitti uusiksi"',
                "Tämä keskustelu"):
        assert osa in lista.text, osa
    assert 'action="https://tyoasema.test/ilmari/saie/2/valitse"' not in lista.text   # aktiivista ei valita uudestaan
    assert "säie" not in lista.text.lower() and "säie" not in r.text.lower()           # Eliaksen sana on keskustelu
    c = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)
    r = c.get("/hub/keskustelu?demo=1")
    assert r.status_code == 200 and "+ Uusi keskustelu" in r.text and "Hahmon kuvaohje" not in r.text and 'action="' not in r.text
    r = c.get("/hub/keskustelu?demo=1&lista=1")
    assert r.status_code == 200 and "Hahmon kuvaohje" in r.text and "Arkisto (1)" in r.text
    assert 'action="' not in r.text and "<form" not in r.text   # esimerkissä napit eivät tee mitään


def test_tuotannossa_kaynnista_malli_vain_kun_malli_ei_ole_kaynnissa(tmp_path, monkeypatch):
    import ilmari_ui.keskustelu as km
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(tmp_path / "ajot"),
                                   "kayttajat": {"elias@github": "elias"}}})
    for tila, nakyy in (("running", False), ("stopped", True), (None, True)):
        data = {"muoto": "aiops-keskustelu-v1", "paivitetty": "2026-10-28T20:00:00+00:00", "viimeisin": 0,
                "malli": {"tila": tila, "tila_teksti": "x", "tyo": None}, "viestit": []}
        monkeypatch.setattr(km, "OLETUS", julkaise(tmp_path / f"k-{tila}", data=data))
        with TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None) as client:
            r = client.get("/keskustelu", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"})
        assert r.status_code == 200 and 'action="https://tyoasema.test/ilmari/viesti"' in r.text
        assert ('action="https://tyoasema.test/kehita/malli"' in r.text) is nakyy
        assert ('name="toiminto" value="kaynnista"' in r.text) is nakyy
        assert r.text.count("ei ole käynnissä") == (1 if nakyy else 0)   # sama ilmoitus vain kerran


# --- Päivitys ei hävitä kesken olevaa viestiä (19.11.2026) --------------------------------------------------

OTSAKKEET = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}


def viestit(*lahettajat_ja_iat):
    """Viestit (lähettäjä, ikä sekunteina) nyt-hetkestä taaksepäin; viimeinen on uusin."""
    nyt = datetime.now(timezone.utc)
    return [{"id": n, "aika": (nyt - timedelta(seconds=ika)).isoformat(timespec="seconds"), "lahettaja": lahettaja,
             "teksti": f"viesti {n}"} for n, (lahettaja, ika) in enumerate(lahettajat_ja_iat, 1)]


def keskustelusivu(tmp_path, monkeypatch, lista, polku="/keskustelu", nimi="k", saikeet=SAIKEET, saie=None):
    data = {"muoto": "aiops-keskustelu-v2", "paivitetty": "2026-11-19T20:00:00+00:00", "viimeisin": len(lista),
            "malli": {"tila": "running", "tila_teksti": "käynnissä", "tyo": None, "dsh_tyo": None, "yoajo": False},
            "saie": saie or V2["saie"], "viestit": [{**v, "saie": (saie or V2["saie"])["id"]} for v in lista]}
    hak = julkaise(tmp_path / nimi, data=data)
    (hak / "saikeet.json").write_text(json.dumps(saikeet, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", hak)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(tmp_path / "ajot"),
                                   "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None) as client:
        return client.get(polku, headers=OTSAKKEET)


def kentat(r):
    return [k.get("name") for k in BeautifulSoup(r.text, "html.parser").find_all(["textarea", "select", "input"])
            if k.get("type") != "hidden"]


def test_ilmari_vastaa_sivu_odottaa_ilman_kenttaa_ja_paivittyy(tmp_path, monkeypatch):
    """Eliaksen viesti on uusin ja alle 10 min vanha: tilarivi, päivitys 5 s välein, ei yhtään tekstikenttää, ja linkki
    kirjoitustilaan vakioparametrilla. Uusi keskustelu ja linkki listaan näkyvät silti (21.11.2026): lomakkeessa on vain
    piilokenttä, joten päivitys toimii. Keskustelujen vaihto on listassa, jota päivitys ei sulje."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("ilmari", 600), ("elias", 20)))
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and r.headers["refresh"] == "5" and kentat(r) == []
    tila = sivu.find(attrs={"role": "status"})
    assert "Ilmari vastaa…" in tila.get_text() and tila.find("span", class_="dot--live")
    assert tila.find("a", string="Kirjoita lisää")["href"] == "/hub/keskustelu?kirjoita=1"
    assert "↓ Kirjoita" not in r.text and "#viesti" not in r.text
    assert "Päivitä" not in r.text and "päivittyy itsestään" not in r.text
    assert 'action="https://tyoasema.test/ilmari/viesti"' not in r.text
    uusi = sivu.find("form", action="https://tyoasema.test/ilmari/saie")
    assert uusi is not None and uusi.find("button", string="+ Uusi keskustelu") is not None
    assert [(i["name"], i["value"]) for i in uusi.find_all("input")] == [("paluu", "hub")]
    assert sivu.find("a", string="Keskustelut (3)")["href"] == "/hub/keskustelu?lista=1"
    assert "/valitse" not in r.text and "/nimea" not in r.text and "/kansio" not in r.text and "/arkistoi" not in r.text


def test_kirjoitustila_nayttaa_kentan_eika_paivity(tmp_path, monkeypatch):
    """Sama odotustila parametrilla kirjoita=1: kenttä näkyy, ei päivitystä, Päivitä-linkki vie takaisin. Kirjoitustila
    on sama ruudun korkuinen keskustelu, jossa vain viestilaatikko vierii."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("elias", 20)), polku="/keskustelu?kirjoita=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and "refresh" not in r.headers and "teksti" in kentat(r)
    assert sivu.find("a", string="Päivitä")["href"] == "/hub/keskustelu" and "Ilmari vastaa" not in r.text
    assert sivu.body["class"] == ["chat-sivu"] and sivu.select_one("section.chat-box .chat-scroll") is not None
    assert sivu.find("a", string="Keskustelut (3)")["href"] == "/hub/keskustelu?lista=1"
    assert sivu.find("form", action="https://tyoasema.test/ilmari/saie") is not None
    assert "/valitse" not in r.text and "/nimea" not in r.text and "↓ Kirjoita" not in r.text


@pytest.mark.parametrize("kysely", ["kirjoita=0", "kirjoita=", "kirjoita=1x", "kirjoita=%3Cb%3E", "Kirjoita=1"])
def test_vain_vakioarvo_avaa_kirjoitustilan(tmp_path, monkeypatch, kysely):
    """Kielletty suunta: muu arvo ei avaa kirjoitustilaa, eikä parametria kaiuteta sivulle."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("elias", 20)), polku="/keskustelu?" + kysely)
    assert r.headers["refresh"] == "5" and kentat(r) == []
    assert "<b>" not in r.text and "%3Cb" not in r.text and "1x" not in r.text


@pytest.mark.parametrize("lista,odottaa", [
    ((("elias", 590),), True),                     # alle 10 min: Ilmari vastaa vielä (esim. GPU varattu)
    ((("elias", 610),), False),                    # yli 10 min: vastausta ei enää odoteta
    ((("elias", 20), ("ilmari", 5)), False),       # Ilmari vastasi
    ((("ilmari", 5),), False),
    ((), False),                                   # tyhjä säie
    ((("elias", -30),), True),                     # kellon pieni ero
    ((("elias", -600),), False),                   # tulevaisuuteen merkitty viesti ei jätä sivua odottamaan
])
def test_odotustila_vain_tuoreelle_eliaksen_viestille(tmp_path, monkeypatch, lista, odottaa):
    r = keskustelusivu(tmp_path, monkeypatch, viestit(*lista))
    assert r.status_code == 200
    if odottaa:
        assert r.headers["refresh"] == "5" and kentat(r) == [] and "Ilmari vastaa…" in r.text
    else:
        assert "refresh" not in r.headers and "teksti" in kentat(r) and "Ilmari vastaa" not in r.text
        assert BeautifulSoup(r.text, "html.parser").find("a", string="Päivitä")["href"] == "/hub/keskustelu"
    assert "15 s" not in r.text and "Sivu päivittyy itsestään" not in r.text


def test_rikkinainen_aika_ei_jata_odottamaan(tmp_path, monkeypatch):
    lista = viestit(("elias", 20))
    for n, aika in enumerate(("", "eilen", "2026-11-19T20:00:00")):   # puuttuva, kelvoton, ilman aikavyöhykettä
        lista[0]["aika"] = aika
        r = keskustelusivu(tmp_path, monkeypatch, lista, nimi=f"k{n}")
        assert "viesti 1" in r.text and "refresh" not in r.headers and "teksti" in kentat(r)


# --- Ruudun korkuinen keskustelu ja keskustelujen lista (21.11.2026) ------------------------------------------

def test_lista_ei_paivity_odottaessakaan(tmp_path, monkeypatch):
    """Lista (?lista=1) näyttää vaihdon, palautuksen, nimen, kansion ja arkistoinnin. Se ei päivity koskaan, ei edes
    kun Ilmari vastaa vielä: päivitys sulkisi avatun kansion ja tyhjentäisi nimen."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("elias", 20)), polku="/keskustelu?lista=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and "refresh" not in r.headers and "Ilmari vastaa" not in r.text
    assert sivu.title.get_text() == "Keskustelut · Ilmari" and sivu.h1.get_text(" ", strip=True).startswith("Keskustelut")
    toimet = sorted(f["action"].removeprefix("https://tyoasema.test") for f in sivu.find_all("form"))
    assert toimet == ["/ilmari/saie", "/ilmari/saie/1/valitse", "/ilmari/saie/2/arkistoi", "/ilmari/saie/2/kansio",
                      "/ilmari/saie/2/nimea", "/ilmari/saie/3/valitse", "/ilmari/saie/4/palauta"]
    assert all(f.find("input", attrs={"name": "paluu", "value": "hub", "type": "hidden"}) for f in sivu.find_all("form"))
    nykyinen = sivu.select_one(".threads [aria-current='true']")
    assert nykyinen.name == "a" and nykyinen["href"] == "/hub/keskustelu" and "Kuvareitti uusiksi" in nykyinen.get_text()
    assert sorted(kentat(r)) == ["kansio", "nimi"] and not sivu.body.get("class")
    assert sivu.find("a", class_="back")["href"] == "/hub/keskustelu"
    assert not sivu.select(".chat-scroll, textarea") and "interactive-widget" not in r.text


@pytest.mark.parametrize("kysely", ["lista=0", "lista=", "lista=1x", "lista=01", "lista=%3Cb%3E", "Lista=1", "lista=true"])
def test_vain_vakioarvo_avaa_listan(tmp_path, monkeypatch, kysely):
    """Kielletty suunta: muu arvo näyttää tavallisen keskustelun (odotus ja päivitys ennallaan), eikä parametria
    kaiuteta sivulle."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("elias", 20)), polku="/keskustelu?" + kysely)
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and r.headers["refresh"] == "5" and kentat(r) == []
    assert sivu.body["class"] == ["chat-sivu"] and sivu.title.get_text() == "Keskustelu · Ilmari"
    assert "/valitse" not in r.text and "Tämä keskustelu" not in r.text
    assert "<b>" not in r.text and "%3Cb" not in r.text and "1x" not in r.text
    assert kysely == "lista=" or kysely not in r.text


def kansiot_auki(r) -> dict[str, bool]:
    return {d.summary.get_text(strip=True): d.has_attr("open") for d in BeautifulSoup(r.text, "html.parser").select(".threads details")}


def test_lista_avaa_vain_nykyisen_keskustelun_kansion(tmp_path, monkeypatch):
    """Nykyisen keskustelun kansio ja keskustelut ilman kansiota ovat auki; muut kansiot ja arkisto ovat kiinni."""
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("ilmari", 20)), polku="/keskustelu?lista=1")
    assert kansiot_auki(r) == {"Ilman kansiota (1)": True, "beta (1)": False, "Ravintopolku (1)": True, "Arkisto (1)": False}
    # toinen suunta: kun nykyinen keskustelu on kansiossa beta, Ravintopolku on kiinni
    beta = {**SAIKEET, "aktiivinen": 3}
    saie = {k: v for k, v in SAIKEET["saikeet"][1].items() if k not in ("viesteja", "viimeisin")}
    r = keskustelusivu(tmp_path, monkeypatch, viestit(("ilmari", 20)), polku="/keskustelu?lista=1", nimi="k2",
                       saikeet=beta, saie=saie)
    assert kansiot_auki(r) == {"Ilman kansiota (1)": True, "beta (1)": True, "Ravintopolku (1)": False, "Arkisto (1)": False}
    sivu = BeautifulSoup(r.text, "html.parser")
    assert sivu.select_one(".threads [aria-current='true']").get_text().startswith("b-kansio")
    assert sivu.find("form", action="https://tyoasema.test/ilmari/saie/2/valitse") is not None
    assert sivu.find("form", action="https://tyoasema.test/ilmari/saie/3/valitse") is None


def test_nimi_on_tekstia_otsikossa_ja_listassa(tmp_path, monkeypatch):
    """Keskustelun nimi ja kansio ovat dataa: koodataan otsikossa, listassa ja kentissä."""
    saikeet = json.loads(json.dumps(SAIKEET))
    saikeet["saikeet"][0].update(nimi="<b>lihava</b>", kansio="<i>k</i>")
    saie = {**V2["saie"], "nimi": "<b>lihava</b>", "kansio": "<i>k</i>"}
    for polku in ("/keskustelu", "/keskustelu?lista=1"):
        r = keskustelusivu(tmp_path, monkeypatch, viestit(("ilmari", 20)), polku=polku, nimi="k" + str(len(polku)),
                           saikeet=saikeet, saie=saie)
        assert r.status_code == 200 and "<b>lihava" not in r.text and "<i>k" not in r.text
        assert "&lt;b&gt;lihava&lt;/b&gt;" in r.text and "&lt;i&gt;k&lt;/i&gt;" in r.text


def test_viestit_aikajarjestyksessa_ja_maara_kun_kaikki_eivat_nay(tmp_path, monkeypatch):
    """HTML:ssä vanhin ensin (ruudunlukija lukee aikajärjestyksessä); laatikko näyttää uusimman alhaalla. Jos
    keskustelussa on enemmän viestejä kuin gateway julkaisee, laatikon alussa kerrotaan se."""
    lista = viestit(("elias", 300), ("ilmari", 200), ("elias", 100))
    r = keskustelusivu(tmp_path, monkeypatch, lista)
    sivu = BeautifulSoup(r.text, "html.parser")
    assert [li.select_one(".msg-body").get_text() for li in sivu.select(".chat-scroll ol.chat > li")] == \
        ["viesti 1", "viesti 2", "viesti 3"]
    assert "Näkyvissä" not in r.text and "kaikkiaan" not in r.text   # säielistan mukaan 1 viesti: lista on jäljessä
    pitka = json.loads(json.dumps(SAIKEET))
    pitka["saikeet"][0]["viesteja"] = 240
    r = keskustelusivu(tmp_path, monkeypatch, lista, nimi="k2", saikeet=pitka)
    huom = BeautifulSoup(r.text, "html.parser").select_one(".chat-scroll p.empty")
    assert huom.get_text() == "Näkyvissä 3 uusinta viestiä, kaikkiaan 240."
    tyhja = keskustelusivu(tmp_path, monkeypatch, [], nimi="k3")
    assert "Kirjoita ensimmäinen viesti alle." in tyhja.text and "Näkyvissä" not in tyhja.text


def test_kirjoituskentta_pysyy_nakyvissa_vain_viestilaatikko_vierii():
    """Tyyli (21.11.2026): keskustelusivu on ruudun korkuinen, viestilaatikko vierii ja aloittaa lopusta
    (column-reverse ilman skriptiä). Muut sivut eivät saa runkoluokkaa eivätkä näppäimistövihjettä."""
    css = re.sub(r"\s+", " ", (PACKAGE_DIR / "static" / "app.css").read_text(encoding="utf-8"))
    saanto = lambda valitsin: re.search(re.escape(valitsin) + r" \{([^}]*)\}", css).group(1)
    assert "flex-direction: column-reverse" in saanto(".chat-scroll") and "overflow-y: auto" in saanto(".chat-scroll")
    assert "min-height: 0" in saanto(".chat-scroll")
    assert "height: 100dvh" in saanto("body.chat-sivu") and "display: flex" in saanto("body.chat-sivu")
    assert "min-height: 9rem" in saanto("body.chat-sivu main > .wrap > .chat-box")
    c = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)
    chat = BeautifulSoup(c.get("/hub/keskustelu?demo=1").text, "html.parser")
    assert chat.body["class"] == ["chat-sivu"] and chat.select_one(".chat-scroll")["tabindex"] == "0"
    assert "interactive-widget=resizes-content" in chat.find("meta", attrs={"name": "viewport"})["content"]
    for polku in ("/hub?demo=1", "/hub/keskustelu?demo=1&lista=1", "/hub/kehita?demo=1", "/hub/asetukset?demo=1"):
        muu = BeautifulSoup(c.get(polku).text, "html.parser")
        assert not muu.body.get("class") and not muu.select(".chat-scroll"), polku
        assert muu.find("meta", attrs={"name": "viewport"})["content"] == "width=device-width, initial-scale=1", polku


def test_keskustelujen_maarat_ja_varanimi(tmp_path):
    hak = julkaise(tmp_path / "k", data=V2)
    saikeet = json.loads(json.dumps(SAIKEET))
    saikeet["saikeet"][1]["nimi"] = ""
    (hak / "saikeet.json").write_text(json.dumps(saikeet, ensure_ascii=False), encoding="utf-8")
    k = lue_keskustelu(hak, omistajat=frozenset({UID}))
    assert k.avoimia == 3 and k.kaikkiaan == 1   # arkistoitu ei ole avoin
    assert [s["nimi"] for s in k.saikeet if s["id"] == 3] == ["Keskustelu 3"]
    k2 = lue_keskustelu(julkaise(tmp_path / "k2", data=V2), omistajat=frozenset({UID}))
    assert k2.avoimia == 0 and k2.kaikkiaan == 1   # ilman säielistaa näkyvien määrä
