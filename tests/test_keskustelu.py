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
