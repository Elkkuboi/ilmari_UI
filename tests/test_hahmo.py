"""Hahmo Hubissa (aiops ADR-0026, 2.11.2026): Hub ei kutsu Hahmoa, vaan linkittää sen omaan käyttöliittymään
Tailscale Serven portissa ja näyttää Ilmarin mallin tilan keskustelun julkaisusta."""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from ilmari_ui.app import HAHMO_PORTTI, Settings, create_app
from ilmari_ui.config import parse_config

OTSAKKEET = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github", "x-forwarded-proto": "https",
             "x-forwarded-for": "100.67.5.28"}


def _tuotanto(tmp_path):
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    return TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost", client=None)


def test_hahmo_on_katalogissa_omana_sovelluksena_ei_yhdistamatta():
    c = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)
    r = c.get("/hub/sovellukset")
    assert r.status_code == 200 and "Hahmo" in r.text and "Oma sovellus" in r.text
    assert "app-icon--hahmo" in r.text
    r = c.get("/hub/sovellukset/hahmo?demo=1")
    assert r.status_code == 200 and "Linkkiä ei ole" in r.text and f":{HAHMO_PORTTI}/" not in r.text


def test_tuotannossa_linkki_serven_porttiin_ja_mallin_tila(tmp_path, monkeypatch):
    from ilmari_ui import keskustelu as k
    julkaisu = tmp_path / "keskustelu"
    julkaisu.mkdir(mode=0o750)
    (julkaisu / k.TIEDOSTO).write_text(json.dumps({
        "muoto": k.MUOTO, "paivitetty": "2026-11-02T20:00:00+00:00", "viimeisin": 1,
        "malli": {"tila": "running", "tila_teksti": "käynnissä", "tyo": 70, "dsh_tyo": None, "yoajo": False},
        "viestit": [{"id": 1, "aika": "2026-11-02T20:00:00+00:00", "lahettaja": "elias", "teksti": "hei"}]}))
    monkeypatch.setattr(k, "OLETUS", julkaisu)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({os.getuid()}))
    with _tuotanto(tmp_path) as client:
        r = client.get("/sovellukset/hahmo", headers=OTSAKKEET)
    assert r.status_code == 200
    assert f'href="https://tyoasema.test:{HAHMO_PORTTI}/"' in r.text and "Avaa Hahmo" in r.text
    assert "Malli: käynnissä" in r.text and "Käynnissä" in r.text
    assert "/hub/kehita" in r.text


def test_tuotannossa_ilman_julkaisua_tila_puuttuu_mutta_linkki_on(tmp_path, monkeypatch):
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", tmp_path / "ei-ole")
    with _tuotanto(tmp_path) as client:
        r = client.get("/sovellukset/hahmo", headers=OTSAKKEET)
    assert r.status_code == 200 and f'href="https://tyoasema.test:{HAHMO_PORTTI}/"' in r.text
    assert "Mallin tilaa ei voitu lukea" in r.text
