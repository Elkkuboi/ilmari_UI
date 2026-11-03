"""Keskustelu Hubissa (28.10.): lukija ja sivu; lomake gatewaylle vain tuotannossa."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
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
    assert 'action="' not in r.text and "Refresh" not in r.headers and "Malli: käynnissä" in r.text
    r = c.get("/hub/keskustelu")
    assert r.status_code == 200 and "lähdettä ei ole määritetty" in r.text


def test_tuotannossa_lomake_gatewaylle(tmp_path):
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/keskustelu", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                               "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    assert r.status_code == 200 and 'action="https://tyoasema.test/ilmari/viesti"' in r.text
    assert 'name="paluu" value="hub"' in r.text and r.headers["refresh"] == "15"
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
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    root = tmp_path / "ajot"
    root.mkdir()
    hak = julkaise(tmp_path / "ajot" / "keskustelu", data=V2)
    (hak / "saikeet.json").write_text(json.dumps(SAIKEET, ensure_ascii=False), encoding="utf-8")
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    import ilmari_ui.keskustelu as km
    alkup = km.OLETUS
    km.OLETUS = hak
    try:
        with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                        client=None) as client:
            r = client.get("/keskustelu", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                                   "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    finally:
        km.OLETUS = alkup
    assert r.status_code == 200
    for osa in ('action="https://tyoasema.test/ilmari/saie"', 'action="https://tyoasema.test/ilmari/saie/1/valitse"',
                'action="https://tyoasema.test/ilmari/saie/2/nimea"', 'action="https://tyoasema.test/ilmari/saie/2/kansio"',
                'action="https://tyoasema.test/ilmari/saie/2/arkistoi"', 'action="https://tyoasema.test/ilmari/saie/4/palauta"',
                "Uusi keskustelu", "Arkisto (1)", "Ravintopolku", "Aiemmat keskustelut", 'value="Kuvareitti uusiksi"'):
        assert osa in r.text, osa
    assert 'action="https://tyoasema.test/ilmari/saie/2/valitse"' not in r.text   # aktiivista ei valita uudestaan
    c = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)
    r = c.get("/hub/keskustelu?demo=1")
    assert r.status_code == 200 and "Hahmon kuvaohje" in r.text and "Arkisto (1)" in r.text and 'action="' not in r.text
