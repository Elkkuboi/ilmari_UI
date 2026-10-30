"""Järjestelmä-näkymä (aiops jarjestelma.py, 30.10.2026): mittarit dispatcherin julkaisusta, omistajatarkistus, ikä."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ilmari_ui import jarjestelma
from ilmari_ui.app import Settings, create_app

JUURI = Path(__file__).resolve().parents[1]
NYT = datetime(2026, 10, 30, 12, 0, 20, tzinfo=UTC)


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_esimerkki_luetaan_ja_tyypitetaan():
    j = jarjestelma.lue_jarjestelma(jarjestelma.ESIMERKKI, now=NYT)
    assert j.tila == "ready" and j.ika_s == 20 and not j.vanhentunut
    assert j.cpu == {"kaytto": 37.5, "kuorma": [10.85, 4.16, 3.13], "ytimet": 32}
    assert j.muisti == {"yhteensa_gb": 65.5, "kaytettavissa_gb": 6.2, "kaytossa_gb": 59.3, "prosentti": 91}
    assert j.gpu["vram_prosentti"] == 98 and j.gpu["nimi"] == "NVIDIA GeForce RTX 5090" and j.gpu["teho_w"] == 357
    assert [t["id"] for t in j.tyot] == [52, 53] and j.tyot[0]["tila_teksti"] == "käynnissä" and j.tyot[0]["malli"] == "flashnext-iq3s"


def test_vanha_julkaisu_ja_puuttuvat_osat(tmp_path):
    juuri = tmp_path / "j"
    juuri.mkdir(mode=0o2750)
    (juuri / "tila.json").write_text(json.dumps({
        "muoto": "aiops-jarjestelma-v1", "paivitetty": "2026-10-30T11:00:00+00:00",
        "cpu": {"kaytto": None, "kuorma": None, "ytimet": 32}, "muisti": None, "gpu": None, "tyot": []}))
    j = jarjestelma.lue_jarjestelma(juuri, now=NYT)
    assert j.tila == "ready" and j.vanhentunut and j.ika_s == 3620
    assert j.cpu["kaytto"] is None and j.cpu["kuorma"] == [] and j.muisti is None and j.gpu is None and j.tyot == ()
    # arvot rajojen ulkopuolella tai väärää tyyppiä putoavat Noneksi, roskatyöt ohitetaan, skriptit eivät läpäise
    (juuri / "tila.json").write_text(json.dumps({
        "muoto": "aiops-jarjestelma-v1", "paivitetty": "2026-10-30T12:00:00+00:00",
        "cpu": {"kaytto": 250, "kuorma": ["x", 1.5], "ytimet": "32"}, "muisti": {"yhteensa_gb": 10, "kaytettavissa_gb": 20},
        "gpu": {"nimi": "<script>alert(1)</script>", "kayttoaste": True, "vram_kaytossa_gb": 1, "vram_yhteensa_gb": 2},
        "tyot": ["roska", {"id": "1"}, {"id": 9, "tila": "running\u0007", "nimi": "x"}]}))
    j = jarjestelma.lue_jarjestelma(juuri, now=NYT)
    assert j.cpu == {"kaytto": None, "kuorma": [1.5], "ytimet": None} and j.muisti is None
    assert j.gpu["kayttoaste"] is None and j.gpu["vram_prosentti"] == 50 and j.gpu["nimi"] == "<script>alert(1)</script>"
    assert j.tyot == ({"id": 9, "tyyppi": "", "nimi": "x", "malli": "", "tila": "running", "tila_teksti": "käynnissä",
                       "jattaja": "", "luotu": ""},)
    r = asiakas().get("/hub/jarjestelma?demo=1")
    assert "&lt;script&gt;" not in r.text or "<script>alert" not in r.text


def test_vaara_muoto_puuttuva_ja_omistaja(tmp_path):
    juuri = tmp_path / "j"
    juuri.mkdir(mode=0o2750)
    assert jarjestelma.lue_jarjestelma(juuri).tila == "not_published"
    assert jarjestelma.lue_jarjestelma(tmp_path / "ei").tila in ("not_published", "error")
    (juuri / "tila.json").write_text('{"muoto": "toinen"}')
    assert jarjestelma.lue_jarjestelma(juuri).tila == "error"
    (juuri / "tila.json").write_text("ei jsonia")
    assert jarjestelma.lue_jarjestelma(juuri).tila == "error"
    (juuri / "tila.json").write_text((jarjestelma.ESIMERKKI / "tila.json").read_text())
    assert jarjestelma.lue_jarjestelma(juuri, now=NYT).tila == "ready"
    j = jarjestelma.lue_jarjestelma(juuri, omistajat=frozenset({os.getuid() + 1}), now=NYT)
    assert j.tila == "error" and "dispatcher" in (j.viesti or "")
    assert jarjestelma.lue_jarjestelma(juuri, omistajat=frozenset({os.getuid()}), now=NYT).tila == "ready"
    assert 0 in jarjestelma.sallitut_omistajat()


def test_sivu_esimerkkitilassa_ja_ilman_lahdetta():
    c = asiakas()
    r = c.get("/hub/jarjestelma?demo=1")
    assert r.status_code == 200 and "Kone nyt." in r.text and "Mitattu" in r.text
    assert "38 <span>%</span>" in r.text and "59.3 <span>/ 65.5 Gt</span>" in r.text and "31.2 <span>/ 31.8 Gt</span>" in r.text
    assert "Käyttöaste 99 %" in r.text and "58 °C" in r.text and "2 <span>kpl</span>" in r.text
    assert "52 ilmari-malli (flashnext-iq3s) · käynnissä" in r.text and "Päivitetty 20 s sitten" in r.text
    assert "Yhdistetty" in r.text and "<script" not in r.text
    r = c.get("/hub/jarjestelma")
    assert r.status_code == 200 and "Todennettu tila ensin." in r.text and "Ei mittauslähdettä" in r.text
    assert "lähde puuttuu" in r.text and "Ei yhdistetty" in r.text


def test_yksikko_liittaa_mittarihakemiston():
    yksikko = (JUURI / "config" / "systemd" / "ilmari-hub.service").read_text(encoding="utf-8")
    assert "BindReadOnlyPaths=-/srv/aiops/ilmari/jarjestelma" in yksikko
    assert jarjestelma.OLETUS == Path("/srv/aiops/ilmari/jarjestelma") and jarjestelma.DISPATCHER_KAYTTAJA == "aiops-run"
