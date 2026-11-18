"""Dokumenttien lukija (aiops istunto 2): kelvollinen julkaisu, omistaja, tiivisteet ja kenttien tarkistus."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from ilmari_ui.dokumentit import ESIMERKKI, etsi, hae, jasenna, lue_dokumentit, osat, piirrettava, ryhmittain

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


# --- Rajattu Markdown (siirretty peruskirjan lukijasta 18.11.2026): käsin kirjoitetut odotetut rakenteet --------------

MD = """# Ilmarin säännöt (peruskirja)

- Tila: luonnos.

## Taso 1: Ehdottomat

### Laki (ei muutettavissa)

- **L1 — Ei todellisia ihmisiä.** Ei edes
  suostumuksella.
- **L2 — Ei alaikäisiä.** `ikäluokitin` aina.

---

| Sääntö | Nyt |
| --- | --- |
| S3 | `gpt-6.1-sol` |
"""


def test_jasennin_rakenne():
    assert jasenna(MD) == (
        {"tyyppi": "otsikko", "taso": 1, "osat": (("teksti", "Ilmarin säännöt (peruskirja)"),)},
        {"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
            {"osat": (("teksti", "Tila: luonnos."),), "sisennys": 0},)},
        {"tyyppi": "otsikko", "taso": 2, "osat": (("teksti", "Taso 1: Ehdottomat"),)},
        {"tyyppi": "otsikko", "taso": 3, "osat": (("teksti", "Laki (ei muutettavissa)"),)},
        {"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
            {"osat": (("lihava", "L1 — Ei todellisia ihmisiä."), ("teksti", " Ei edes suostumuksella.")), "sisennys": 0},
            {"osat": (("lihava", "L2 — Ei alaikäisiä."), ("teksti", " "), ("koodi", "ikäluokitin"),
                      ("teksti", " aina.")), "sisennys": 0},
        )},
        {"tyyppi": "viiva"},
        {"tyyppi": "taulukko", "otsikot": ((("teksti", "Sääntö"),), (("teksti", "Nyt"),)),
         "rivit": (((("teksti", "S3"),), (("koodi", "gpt-6.1-sol"),)),)},
    )


def test_jasennin_kappale_lainaus_koodi_ja_numeroitu():
    teksti = ("Eka rivi\ntoka rivi.\n\n> lainattu\n> jatkuu\n\n```\n<b>koodia</b>\n  sisennys\n```\n\n"
              "3. kolmas\n4. neljäs\n   jatko\n\n5. viides\n")
    assert jasenna(teksti) == (
        {"tyyppi": "kappale", "osat": (("teksti", "Eka rivi toka rivi."),)},
        {"tyyppi": "lainaus", "osat": (("teksti", "lainattu jatkuu"),)},
        {"tyyppi": "koodi", "teksti": "<b>koodia</b>\n  sisennys"},
        {"tyyppi": "lista", "jarjestetty": True, "alku": 3, "kohdat": (
            {"osat": (("teksti", "kolmas"),), "sisennys": 0},
            {"osat": (("teksti", "neljäs jatko"),), "sisennys": 0},
            {"osat": (("teksti", "viides"),), "sisennys": 0},
        )},
    )


def test_jasennin_sisakkainen_kohta_ja_vuosiluku_kappaleessa():
    assert jasenna("- yla\n  - ala\n- toinen\n") == ({"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
        {"osat": (("teksti", "yla"),), "sisennys": 0}, {"osat": (("teksti", "ala"),), "sisennys": 1},
        {"osat": (("teksti", "toinen"),), "sisennys": 0})},)
    assert jasenna("Päätös tehtiin\n2026. vuonna.\n") == (
        {"tyyppi": "kappale", "osat": (("teksti", "Päätös tehtiin 2026. vuonna."),)},)


@pytest.mark.parametrize("teksti,odotettu", [
    ("**kesken", (("teksti", "**kesken"),)),
    ("`kesken", (("teksti", "`kesken"),)),
    ("****", (("teksti", "****"),)),
    ("a **b** c `d` e", (("teksti", "a "), ("lihava", "b"), ("teksti", " c "), ("koodi", "d"), ("teksti", " e"))),
    ("[linkki](https://example.org)", (("teksti", "[linkki](https://example.org)"),)),
    ("<script>x</script>", (("teksti", "<script>x</script>"),)),
])
def test_tekstinsisaiset_osat(teksti, odotettu):
    assert osat(teksti) == odotettu


def test_repon_ulkopuolinen_crlf_ja_tyhja():
    assert jasenna("# a\r\n\r\nb\r\n") == ({"tyyppi": "otsikko", "taso": 1, "osat": (("teksti", "a"),)},
                                          {"tyyppi": "kappale", "osat": (("teksti", "b"),)})
    assert jasenna("") == ()


def test_liian_monta_lohkoa_ei_piirry():
    lohkot, virhe = piirrettava({"teksti": "x\n\n" * 4001})
    assert lohkot is None and "liikaa lohkoja" in virhe
