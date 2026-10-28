"""Dokumenttien lukija (aiops istunto 2): kelvollinen julkaisu, omistaja, tiivisteet ja kenttien tarkistus."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from ilmari_ui.dokumentit import ESIMERKKI, etsi, hae, lue_dokumentit, ryhmittain

UID = os.getuid()
COMMIT = "b" * 40


def dok(tunniste="tilanne", ryhma="perus", polku="docs/TILANNE.md", otsikko="Tilanne", tila="", paiva="",
        teksti="# Tilanne\n\nKaikki hyvin. Ilmari toimii.\n"):
    return {"tunniste": tunniste, "polku": polku, "ryhma": ryhma, "otsikko": otsikko, "tila": tila, "paiva": paiva,
            "teksti": teksti}


def julkaise(hak: Path, dokumentit=None, *, data_muutos=None, meta_muutos=None, raaka=None) -> Path:
    hak.mkdir(parents=True, exist_ok=True)
    if dokumentit is None:
        dokumentit = [dok(), dok("adr-0023-netti", "adr", "docs/adr/0023-netti.md", "ADR-0023: Netti", "ehdotettu",
                                 "2026-10-27", "# ADR-0023\n\nNetti on kyky.\n")]
    sisalto = {"muoto": "aiops-dokumentit-v1", "commit": COMMIT, "dokumentit": dokumentit} | (data_muutos or {})
    data = raaka if raaka is not None else json.dumps(sisalto, ensure_ascii=False).encode("utf-8")
    meta = {"muoto": "aiops-dokumentit-v1", "commit": COMMIT, "sha256": hashlib.sha256(data).hexdigest(),
            "koko": len(data), "maara": len(dokumentit), "julkaistu": "2026-10-28T18:00:00+02:00"} | (meta_muutos or {})
    (hak / "dokumentit.json").write_bytes(data)
    (hak / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return hak


def test_kelvollinen_julkaisu_luetaan(tmp_path):
    k = lue_dokumentit(julkaise(tmp_path / "d"), omistaja=UID)
    assert k.tila == "ready" and [d["tunniste"] for d in k.dokumentit] == ["tilanne", "adr-0023-netti"]
    assert [(a, [d["tunniste"] for d in r]) for a, _, r in ryhmittain(k)] == [("perus", ["tilanne"]),
                                                                            ("adr", ["adr-0023-netti"])]
    assert etsi(k, "adr-0023-netti")["otsikko"] == "ADR-0023: Netti"
    assert etsi(k, "../tilanne") is None and etsi(k, "ei-ole") is None


def test_puuttuva_julkaisu_ja_vaara_omistaja(tmp_path):
    assert lue_dokumentit(tmp_path / "ei-ole", omistaja=UID).tila == "not_published"
    k = lue_dokumentit(julkaise(tmp_path / "d"), omistaja=UID + 4242)
    assert k.tila == "error" and "root" in k.viesti


@pytest.mark.parametrize("muutos", [
    {"meta_muutos": {"sha256": "0" * 64}}, {"meta_muutos": {"koko": 1}}, {"meta_muutos": {"maara": 5}},
    {"meta_muutos": {"muoto": "x"}}, {"meta_muutos": {"julkaistu": "2026-10-28T18:00:00"}},
    {"data_muutos": {"commit": "c" * 40}}, {"data_muutos": {"ylimaarainen": 1}},
])
def test_ristiriitainen_julkaisu_ei_nay(tmp_path, muutos):
    assert lue_dokumentit(julkaise(tmp_path / "d", **muutos), omistaja=UID).tila == "error"


@pytest.mark.parametrize("vika", [
    {"tunniste": "../x"}, {"tunniste": "Iso"}, {"polku": "/etc/passwd"}, {"polku": "docs/../x.md"},
    {"ryhma": "salainen"}, {"otsikko": "rivi\nvaihto"}, {"teksti": "suunta\u202eohjaus"},
    {"teksti": "ohjaus\x1bmerkki"}, {"teksti": 5}, {"lisakentta": "x"},
])
def test_kelvoton_dokumentti_hylkaa_julkaisun(tmp_path, vika):
    assert lue_dokumentit(julkaise(tmp_path / "d", [dok() | vika]), omistaja=UID).tila == "error"


def test_sama_tunniste_kahdesti_ja_toistuva_kentta_hylataan(tmp_path):
    assert lue_dokumentit(julkaise(tmp_path / "a", [dok(), dok()]), omistaja=UID).tila == "error"
    raaka = b'{"muoto": "aiops-dokumentit-v1", "muoto": "x", "commit": "' + COMMIT.encode() + b'", "dokumentit": []}'
    assert lue_dokumentit(julkaise(tmp_path / "b", raaka=raaka), omistaja=UID).tila == "error"


def test_linkki_ja_kokoraja(tmp_path):
    hak = julkaise(tmp_path / "d")
    (hak / "dokumentit.json").rename(tmp_path / "oikea.json")
    (hak / "dokumentit.json").symlink_to(tmp_path / "oikea.json")
    assert lue_dokumentit(hak, omistaja=UID).tila == "error"
    iso = julkaise(tmp_path / "iso", raaka=b" " * (6 * 1024 * 1024 + 1))
    assert lue_dokumentit(iso, omistaja=UID).tila == "error"


def test_haku(tmp_path):
    k = lue_dokumentit(julkaise(tmp_path / "d"), omistaja=UID)
    osumat = hae(k, "ilmari")
    assert [o["tunniste"] for o in osumat] == ["tilanne"] and osumat[0]["osumia"] == 1
    assert "Ilmari toimii" in osumat[0]["ote"]
    assert hae(k, "") == [] and hae(k, "x" * 101) == [] and hae(k, "ei-löydy") == []


def test_esimerkkiaineisto_kelpaa():
    k = lue_dokumentit(ESIMERKKI, omistaja=None)
    assert k.tila == "ready" and len(k.dokumentit) == 3
