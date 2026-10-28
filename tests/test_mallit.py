"""Mallirekisterin lukija ja Mallit-näkymä (aiops istunto 3): kelvollinen julkaisu, ristiriidat, escapetus."""

import hashlib
import json
import os
from pathlib import Path

import pytest
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
    assert k.tila == "ready" and k.roolit["ceo"] == "hauhau-q6" and len(k.mallit) == 3


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_sivu_esimerkkitilassa_ja_escapetus():
    r = asiakas().get("/hub/mallit?demo=1")
    assert r.status_code == 200 and "Ilmarin aivot (CEO)" in r.text and "<code>hauhau-q6</code>" in r.text
    assert "&lt;b&gt;esimerkki&lt;/b&gt;" in r.text and "<b>esimerkki</b>" not in r.text
    assert "ei mallia" in r.text and "Esimerkkitila" in r.text and "gpt-6.1-sol/standard" in r.text


def test_ilman_lahdetta_ja_valikko():
    c = asiakas()
    r = c.get("/hub/mallit")
    assert r.status_code == 200 and "lähdettä ei ole määritetty" in r.text
    assert 'href="/hub/mallit' in c.get("/hub?demo=1").text


def test_ylikirjoitus_luetaan_ja_lomake_tuotannossa(tmp_path):
    from ilmari_ui.config import parse_config
    from ilmari_ui.mallit import lue_ylikirjoitus
    hak = tmp_path / "roolit"
    hak.mkdir()
    (hak / "roolit.toml").write_text('[roolit]\nkuva_tulkki = ""\nyoajo = "hauhau-q6"\njohtaja = "x"\n', encoding="utf-8")
    assert lue_ylikirjoitus(hak, omistajat=frozenset({UID})) == {"kuva_tulkki": "", "yoajo": "hauhau-q6"}
    assert lue_ylikirjoitus(hak, omistajat=frozenset({UID + 1})) is None
    assert lue_ylikirjoitus(tmp_path / "ei") is None
    (hak / "roolit.toml").write_text("ei tomlia = = =", encoding="utf-8")
    assert lue_ylikirjoitus(hak) is None
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/mallit", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                           "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    assert r.status_code == 200 and "Mallit" in r.text  # testikoneella rekisteriä ei välttämättä voi lukea


def test_esimerkkitilassa_valinta_nakyy_ilman_lomaketta():
    r = asiakas().get("/hub/mallit?demo=1")
    assert r.status_code == 200 and "(valittu; oletus" in r.text and 'action="' not in r.text
