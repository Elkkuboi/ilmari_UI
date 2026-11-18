"""Mallirekisterin lukija ja Mallit-näkymä (aiops istunto 3): kelvollinen julkaisu, ristiriidat, escapetus."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
from ilmari_ui.mallit import ESIMERKKI, lue_mallit

UID = os.getuid()
COMMIT = "b" * 40


def malli(nimi="hauhau-q6", **muutos):
    m = {"nimi": nimi, "kuvaus": "Aivot", "tyyppi": "chat", "sijainti": "paikallinen", "konteksti_max": 65536,
         "vram_gb": 29, "kuva": "aiops/llama-server:2", "tiedosto": "a.gguf", "koko": 25924151424,
         "manifesti": "config/mallit/x.tsv", "tarjoaja": "", "hinnasto": "", "roolit": ["ceo"]}
    m.update(muutos)
    return m


def julkaise(hak: Path, mallit=None, roolit=None, *, meta_muutos=None, raaka=None) -> Path:
    hak.mkdir(parents=True, exist_ok=True)
    mallit = mallit if mallit is not None else [malli()]
    roolit = roolit if roolit is not None else {"ceo": "hauhau-q6"}
    data = raaka if raaka is not None else json.dumps({"muoto": "aiops-mallit-v1", "commit": COMMIT, "mallit": mallit,
                                                       "roolit": roolit}, ensure_ascii=False).encode("utf-8")
    meta = {"muoto": "aiops-mallit-v1", "commit": COMMIT, "sha256": hashlib.sha256(data).hexdigest(), "koko": len(data),
            "maara": len(mallit), "julkaistu": "2026-10-28T18:00:00+02:00"} | (meta_muutos or {})
    (hak / "mallit.json").write_bytes(data)
    (hak / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return hak


def test_kelvollinen_julkaisu_luetaan(tmp_path):
    k = lue_mallit(julkaise(tmp_path / "m"), omistaja=UID)
    assert k.tila == "ready" and k.roolit == {"ceo": "hauhau-q6"} and k.mallit[0]["koko_gb"] == 25.9
    rivit = k.roolirivit()
    assert rivit[0]["rooli"] == "ceo" and rivit[0]["malli"] == "hauhau-q6" and rivit[0]["vaihtoehdot"] == ["hauhau-q6"]
    assert all(r["malli"] == "" for r in rivit[1:])  # täyttämätön rooli on tyhjä, ei nolla
    rivit = k.roolirivit({"ceo": "", "yoajo": "hauhau-q6"})
    assert rivit[0]["malli"] == "" and rivit[0]["valittu"] and rivit[0]["oletus"] == "hauhau-q6"
    assert [r for r in rivit if r["rooli"] == "yoajo"][0]["malli"] == "hauhau-q6"


def test_puuttuva_ja_vaara_omistaja(tmp_path):
    assert lue_mallit(tmp_path / "ei", omistaja=UID).tila == "not_published"
    assert lue_mallit(julkaise(tmp_path / "m"), omistaja=UID + 1).tila == "error"


@pytest.mark.parametrize("muutos", [
    {"meta_muutos": {"sha256": "0" * 64}}, {"meta_muutos": {"maara": 2}}, {"meta_muutos": {"muoto": "x"}},
    {"roolit": {"ceo": "tuntematon"}}, {"roolit": {"tyontekija": "hauhau-q6"}}, {"roolit": {"johtaja": "hauhau-q6"}},
    {"mallit": [malli(sijainti="kuu")]}, {"mallit": [malli(roolit=["x"])]}, {"mallit": [malli(kuvaus="a\x07")]},
    {"mallit": [malli(), malli()]}, {"mallit": [malli(ylimaarainen=1)]}, {"mallit": [malli(koko="iso")]},
    {"raaka": b"{ei json"},
])
def test_ristiriitainen_julkaisu_ei_nay(tmp_path, muutos):
    assert lue_mallit(julkaise(tmp_path / "m", **muutos), omistaja=UID).tila == "error"


def test_esimerkkiaineisto_kelpaa():
    k = lue_mallit(ESIMERKKI, omistaja=None)
    assert k.tila == "ready" and k.roolit["ceo"] == "hauhau-q6" and len(k.mallit) == 4
    assert set(k.profiilit) == {"raskas", "kevyt"} and k.nykyinen_profiili() == "kevyt"


# --- Aivoprofiilit (aiops ADR-0029) -------------------------------------------------------------------------------

RASKAS = {"kuvaus": "Raskaat", "ram_gb": 58, "roolit": {r: "flashnext" for r in ("ceo", "tyontekija", "kirjoittaja", "kuva_tulkki")}}
KEVYT = {"kuvaus": "Kevyet", "ram_gb": 32, "roolit": {"ceo": "hauhau-q6", "tyontekija": "hauhau-q6",
                                                      "kirjoittaja": "hauhau-q6", "kuva_tulkki": "sol"}}
KAIKKI = ["ceo", "tyontekija", "kirjoittaja", "kuva_tulkki"]


def julkaise_profiilit(hak: Path, profiilit, mallit=None):
    mallit = mallit if mallit is not None else [
        malli(roolit=KAIKKI), malli("flashnext", roolit=KAIKKI, moottori="strata", ram_gb=58, kuvat=True, konteksti_max=131072),
        malli("sol", sijainti="pilvi", vram_gb=None, kuva="", tiedosto="", koko=0, manifesti="", tarjoaja="openai",
              hinnasto="x", roolit=["kuva_tulkki"])]
    data = json.dumps({"muoto": "aiops-mallit-v1", "commit": COMMIT, "mallit": mallit,
                       "roolit": {r: "hauhau-q6" for r in KAIKKI[:3]} | {"kuva_tulkki": "sol"},
                       "profiilit": profiilit}, ensure_ascii=False).encode("utf-8")
    return julkaise(hak, mallit, raaka=data)


def test_profiilit_luetaan_ja_nykyinen_paatellaan(tmp_path):
    k = lue_mallit(julkaise_profiilit(tmp_path / "m", {"raskas": RASKAS, "kevyt": KEVYT}), omistaja=UID)
    assert k.tila == "ready" and set(k.profiilit) == {"raskas", "kevyt"} and k.profiilit["raskas"]["ram_gb"] == 58
    assert k.nykyinen_profiili() == "kevyt" and k.nykyinen_profiili(None) == "kevyt"
    assert k.nykyinen_profiili({r: "flashnext" for r in KAIKKI}) == "raskas"
    assert k.nykyinen_profiili({"ceo": "flashnext"}) is None            # vain osa vaihdettu
    assert k.nykyinen_profiili({"kuva_tulkki": ""}) is None             # rooli poistettu
    assert k.mallit[1]["moottori"] == "strata" and k.mallit[1]["kuvat"] and k.mallit[0]["moottori"] == ""
    # ilman profiileja (vanha julkaisu) toimii kuten ennen
    k2 = lue_mallit(julkaise(tmp_path / "v"), omistaja=UID)
    assert k2.tila == "ready" and k2.profiilit == {} and k2.nykyinen_profiili() is None


@pytest.mark.parametrize("profiilit", [
    [], {"Iso": RASKAS}, {"raskas": {**RASKAS, "lisa": 1}}, {"raskas": {**RASKAS, "roolit": {"ceo": "flashnext"}}},
    {"raskas": {**RASKAS, "roolit": {**RASKAS["roolit"], "kuva_tulkki": "tuntematon"}}},
    {"raskas": {**RASKAS, "roolit": {**RASKAS["roolit"], "ceo": "sol"}}},   # sol ei tarjoa ceo-roolia
    {"raskas": {**RASKAS, "ram_gb": "58"}}, {"raskas": {**RASKAS, "kuvaus": "a\x07"}},
])
def test_kelvoton_profiili_estaa_julkaisun(tmp_path, profiilit):
    assert lue_mallit(julkaise_profiilit(tmp_path / "m", profiilit), omistaja=UID).tila == "error"


@pytest.mark.parametrize("muutos", [{"moottori": 5}, {"ram_gb": "58"}, {"kuvat": "kyllä"}])
def test_kelvoton_lisakentta_estaa_julkaisun(tmp_path, muutos):
    assert lue_mallit(julkaise(tmp_path / "m", [malli(**muutos)]), omistaja=UID).tila == "error"


def test_aivot_nakyvat_asetuksissa_esimerkkitilassa_ja_vapaa_ram():
    """Hub juureksi (18.11.2026): mallit ovat Asetukset-sivun osio Aivot (#aivot), roolit ja rekisteri taiton alla."""
    from ilmari_ui.mallit import vapaa_ram_gb
    r = asiakas().get("/hub/asetukset?demo=1")
    aivot = BeautifulSoup(r.text, "html.parser").find("section", id="aivot")
    assert r.status_code == 200 and aivot.find("table") and "raskas" in aivot.get_text() and "kevyt" in aivot.get_text()
    assert "RAM 58 Gt" in aivot.get_text() and "strata" in aivot.get_text() and "<form" not in r.text
    rivit = aivot.find("ul", class_="rows")            # profiilit riveinä, ei taulukkona (mahtuu puhelimeen)
    assert rivit is not None and "raskas" in rivit.get_text() and "RAM 58 Gt" in rivit.get_text()
    assert not [th for th in aivot.find_all("th") if th.get_text() == "Profiili"]
    fold = aivot.find("details", class_="fold")
    assert fold.summary.get_text() == "Roolit ja mallirekisteri" and "Ilmarin aivot (CEO)" in fold.get_text()
    assert vapaa_ram_gb(Path("/proc/meminfo")) is None or vapaa_ram_gb(Path("/proc/meminfo")) > 0
    assert vapaa_ram_gb(Path("/ei/ole")) is None


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_sivu_esimerkkitilassa_ja_escapetus():
    r = asiakas().get("/hub/asetukset?demo=1")
    assert r.status_code == 200 and "Ilmarin aivot (CEO)" in r.text and "hauhau-q6" in r.text
    assert "&lt;b&gt;esimerkki&lt;/b&gt;" in r.text and "<b>esimerkki</b>" not in r.text
    assert "ei mallia" in r.text and "Esimerkkitila" in r.text and "gpt-6.1-sol/standard" in r.text
    assert "valittu; oletus" in r.text and 'action="' not in r.text   # esimerkkitila: ei lomakkeita


def test_ilman_lahdetta_ja_vanha_osoite():
    c = asiakas()
    r = c.get("/hub/asetukset")
    assert r.status_code == 200 and "Mallit eivät ole saatavilla" in r.text
    r = c.get("/hub/mallit", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/hub/asetukset#aivot"


def test_ylikirjoitus_luetaan(tmp_path):
    from ilmari_ui.mallit import lue_ylikirjoitus
    hak = tmp_path / "roolit"
    hak.mkdir()
    (hak / "roolit.toml").write_text('[roolit]\nkuva_tulkki = ""\nyoajo = "hauhau-q6"\njohtaja = "x"\n', encoding="utf-8")
    assert lue_ylikirjoitus(hak, omistajat=frozenset({UID})) == {"kuva_tulkki": "", "yoajo": "hauhau-q6"}
    assert lue_ylikirjoitus(hak, omistajat=frozenset({UID + 1})) is None
    assert lue_ylikirjoitus(tmp_path / "ei") is None
    (hak / "roolit.toml").write_text("ei tomlia = = =", encoding="utf-8")
    assert lue_ylikirjoitus(hak) is None


def test_tuotannossa_profiili_ja_roolilomakkeet(tmp_path, monkeypatch):
    """Sallittu: profiilin ja roolin vaihto ovat lomakkeita gatewaylle (paluu=hub), nykyinen profiili ei ole
    valittavissa. Kielletty: ilman luettavaa rekisteriä ei lomakkeita (asennus omistaa rekisterin: testissä oma uid)."""
    from ilmari_ui import mallit as mallit_moduuli
    from ilmari_ui.config import parse_config
    alkuperainen = mallit_moduuli.lue_mallit
    monkeypatch.setattr(mallit_moduuli, "lue_mallit", lambda polku, omistaja=0, **kw: alkuperainen(polku, omistaja=UID, **kw))
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(tmp_path / "ajot"),
                                   "kayttajat": {"elias@github": "elias"}}})
    otsakkeet = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}
    with TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None) as client:
        ilman = client.get("/asetukset", headers=otsakkeet)
        monkeypatch.setattr(mallit_moduuli, "OLETUS", julkaise_profiilit(tmp_path / "m", {"raskas": RASKAS, "kevyt": KEVYT}))
        r = client.get("/asetukset", headers=otsakkeet)
    assert ilman.status_code == 200 and "/mallit/" not in ilman.text and "Mallirekisteriä ei ole vielä asennettu." in ilman.text
    sivu = BeautifulSoup(r.text, "html.parser")
    profiilit = sivu.find_all("form", action="https://tyoasema.test/mallit/profiili")
    assert {f.find("input", attrs={"name": "profiili"})["value"]: f.button.has_attr("disabled") for f in profiilit} == \
        {"raskas": False, "kevyt": True}
    assert all(f.find("input", attrs={"name": "paluu"})["value"] == "hub" and f["method"] == "post" for f in profiilit)
    roolit = sivu.find_all("form", action="https://tyoasema.test/mallit/rooli")
    assert len(roolit) == 11 and {f.find("input", attrs={"name": "rooli"})["value"] for f in roolit} >= set(KAIKKI)
    assert all(f.find("select", attrs={"name": "malli"}) and f.find("input", attrs={"name": "paluu"})["value"] == "hub"
               for f in roolit)
