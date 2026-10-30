"""Kehitystöiden ja käyttöönottojen lukija (aiops ADR-0024): tunnetut kentät, omistaja, rajat, rikkinäiset tiedostot."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from ilmari_ui.kehitys import (ESIMERKKI, ESIMERKKI_KAYTTOONOTOT, RAJAT, lue_kayttoonotot, lue_kehitystyo,
                               lue_kehitystyot)

UID = os.getuid()
OMAT = frozenset({UID})
PAA = "b" * 40


def meta(tyo=41, **muutos):
    m = {"tyo": tyo, "toive": "Lisää rivi", "jatka": None, "luotu": "2026-10-28T12:00:00+00:00", "jattaja": "elias",
         "tila": "succeeded", "tila_teksti": "valmis", "syy": "exit 0", "kesto": "1 min", "valmis": True,
         "tulos": {"paluukoodi": 0, "haara": "ilmari/41", "perus": "c" * 40, "paa": PAA, "commiteja": 1,
                   "tiedostot": ["docs/TILANNE.md"], "muutokset": " 1 file changed", "diff_sha256": "e" * 64,
                   "vastaus": "Tein.", "testit": {"paluukoodi": 0, "yhteenveto": "2300 passed"}},
         "tiedostot": ["muutos.diff"]}
    m.update(muutos)
    return m


def julkaise(juuri: Path, tyo=41, m=None, tiedostot=None, **lisat) -> Path:
    hak = juuri / str(tyo)
    hak.mkdir(parents=True, exist_ok=True)
    (hak / "meta.json").write_text(json.dumps(m if m is not None else meta(tyo)), encoding="utf-8")
    for nimi, sisalto in (tiedostot or {"muutos.diff": "+rivi\n"}).items():
        (hak / nimi).write_bytes(sisalto if isinstance(sisalto, bytes) else sisalto.encode("utf-8"))
    for nimi, sisalto in lisat.items():
        (hak / f"{nimi}.json").write_text(json.dumps(sisalto), encoding="utf-8")
    return hak


def test_tyo_luetaan_ja_vaihe_paatellaan(tmp_path):
    julkaise(tmp_path, paatos={"paatos": "hyvaksytty", "aika": "x", "kuka": "elias", "commit": PAA, "pyynto": "p"},
             yhdistys={"tila": "yhdistetty", "commit": "d" * 40, "viesti": "ok"})
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.meta["toive"] == "Lisää rivi" and t.meta["tulos"]["testit"] == {"paluukoodi": 0, "yhteenveto": "2300 passed"}
    assert t.paatos["teksti"] == "Hyväksytty" and t.yhdistys["commit"] == "d" * 40 and t.kayttoonotto is None
    assert t.vaihe == ("Yhdistetty mainiin", "success") and t.tekstit == {"muutos.diff": "+rivi\n"} and t.virheet == ()
    tyot = lue_kehitystyot(tmp_path, omistajat=OMAT)
    assert [x.tyo for x in tyot] == [41] and tyot[0].tekstit == {}


@pytest.mark.parametrize("osat, odotus", [
    ({}, ("Valmis, odottaa päätöstä", "accent")),
    ({"m": meta(tila="running")}, ("Käynnissä", "muted")),
    ({"m": meta(tila="failed")}, ("Epäonnistui", "danger")),
    ({"m": meta(tulos={**meta()["tulos"], "testit": {"paluukoodi": 1, "yhteenveto": "1 failed"}})},
     ("Valmis, testit epäonnistuivat", "warning")),
    ({"paatos": {"paatos": "hylatty", "aika": "x", "kuka": "elias"}}, ("Hylätty", "warning")),
    ({"paatos": {"paatos": "hyvaksytty", "aika": "x", "kuka": "elias"}}, ("Hyväksytty, odottaa yhdistystä", "accent")),
    ({"paatos": {"paatos": "hyvaksytty", "kayttoonotto_pyynto": "p"}, "yhdistys": {"tila": "yhdistetty"}},
     ("Käyttöönotto pyydetty", "accent")),
    ({"paatos": {"paatos": "hyvaksytty"}, "yhdistys": {"tila": "ristiriita"}}, ("Ristiriita mainin kanssa", "danger")),
    ({"paatos": {"paatos": "hyvaksytty"}, "yhdistys": {"tila": "yhdistetty"}, "kayttoonotto": {"tulos": "asennettu"}},
     ("Otettu käyttöön", "success")),
    ({"paatos": {"paatos": "hyvaksytty"}, "yhdistys": {"tila": "yhdistetty"}, "kayttoonotto": {"tulos": "palautettu"}},
     ("Palautettu edelliseen", "danger")),
])
def test_vaiheet(tmp_path, osat, odotus):
    osat = dict(osat)
    m = osat.pop("m", None)
    julkaise(tmp_path, m=m, **osat)
    assert lue_kehitystyo(tmp_path, 41, omistajat=OMAT).vaihe == odotus


def test_vieraat_kentat_ja_tyypit_siivotaan(tmp_path):
    m = meta(toive="a\x07b‮c", jattaja=5, jatka="40", ylimaarainen="x",
             tulos={"paluukoodi": "0", "commiteja": True, "paa": "<b>", "testit": {"paluukoodi": 0, "yhteenveto": 7},
                    "tiedostot": "docs"}, tiedostot=["muutos.diff", "../etc/passwd", "salainen.txt"])
    julkaise(tmp_path, m=m, paatos={"paatos": "keksitty"}, yhdistys={"tila": "yhdistetty", "commit": 5, "viesti": ["x"]})
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.meta["toive"] == "abc" and t.meta["jattaja"] == "" and t.meta["jatka"] is None
    assert t.meta["tulos"]["paluukoodi"] is None and t.meta["tulos"]["commiteja"] is None
    assert t.meta["tulos"]["testit"] == {"paluukoodi": 0, "yhteenveto": ""} and t.meta["tulos"]["tiedostot"] == []
    assert t.meta["tiedostot"] == ["muutos.diff"] and "ylimaarainen" not in t.meta
    assert t.paatos is None and t.yhdistys == {"tila": "yhdistetty", "teksti": "Yhdistetty mainiin", "commit": "",
                                                "viesti": "", "aika": "", "paluukoodi": None, "edellinen": ""}


@pytest.mark.parametrize("m", [meta(tyo=42), meta(tila="outo"), "ei objekti", {"tyo": 41}])
def test_kelvoton_meta_nakyy_virheena(tmp_path, m):
    julkaise(tmp_path, m=m)
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t is not None and t.virheet and t.virheet[0].startswith("meta.json") and t.meta["tila_teksti"] == "ei luettavissa"


def test_rikkinainen_sivutiedosto_ei_kaada(tmp_path):
    hak = julkaise(tmp_path)
    (hak / "paatos.json").write_text("{ei json", encoding="utf-8")
    (hak / "kayttoonotto.json").write_text(json.dumps({"tulos": "asennettu", "viesti": "ok"}), encoding="utf-8")
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.paatos is None and t.kayttoonotto["teksti"] == "Otettu käyttöön"
    assert any(v.startswith("paatos.json") for v in t.virheet)


def test_omistaja_koko_ja_linkki(tmp_path):
    hak = julkaise(tmp_path)
    assert lue_kehitystyo(tmp_path, 41, omistajat=frozenset({UID + 1})) is None  # juuri väärän omistajan
    t = lue_kehitystyo(tmp_path, 41, omistajat=frozenset({UID, UID + 1}))
    assert t.virheet == ()
    (hak / "muutos.diff").write_bytes(b"x" * (RAJAT["muutos.diff"] + 1))
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert "muutos.diff" not in t.tekstit and any("muutos.diff" in v for v in t.virheet)
    (hak / "muutos.diff").unlink()
    os.symlink("/etc/hostname", hak / "muutos.diff")
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert "muutos.diff" not in t.tekstit and any("muutos.diff" in v for v in t.virheet)
    assert lue_kehitystyo(tmp_path, 99, omistajat=OMAT) is None
    assert lue_kehitystyo(tmp_path / "ei-ole", 41, omistajat=OMAT) is None
    assert lue_kehitystyot(tmp_path / "ei-ole", omistajat=OMAT) is None


def test_tekstin_ohjausmerkit_poistetaan(tmp_path):
    julkaise(tmp_path, tiedostot={"muutos.diff": b"+rivi\x1b[31m\xff\n\t<x>\n"})
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.tekstit["muutos.diff"] == "+rivi[31m�\n\t<x>\n"


def test_tyolista_uusin_ensin_ja_vain_numerot(tmp_path):
    for tyo in (3, 12, 7):
        julkaise(tmp_path, tyo=tyo, m=meta(tyo))
    (tmp_path / "pyynnot").mkdir()
    (tmp_path / "007").mkdir()
    assert [t.tyo for t in lue_kehitystyot(tmp_path, omistajat=OMAT)] == [12, 7, 3]


def kayttoonotot(juuri: Path, rivit=None, meta_muutos=None, raaka=None) -> Path:
    juuri.mkdir(parents=True, exist_ok=True)
    rivit = rivit if rivit is not None else [{"aika": "2026-10-28T12:45:00+00:00", "kesto_s": 310, "commit": "d" * 40,
                                               "edellinen": "a" * 40, "tulos": "asennettu", "vaihe": "terveys",
                                               "viesti": "asennettu", "testit": "2300 passed", "loki": "OK\n"}]
    data = raaka if raaka is not None else json.dumps({"muoto": "aiops-kayttoonotot-v1", "commit": "d" * 40,
                                                       "kayttoonotot": rivit}).encode("utf-8")
    m = {"muoto": "aiops-kayttoonotot-v1", "commit": "d" * 40, "sha256": hashlib.sha256(data).hexdigest(),
         "koko": len(data), "maara": len(rivit), "julkaistu": "2026-10-28T12:45:10+00:00"} | (meta_muutos or {})
    (juuri / "historia.json").write_bytes(data)
    (juuri / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    return juuri


def test_kayttoonotot_luetaan(tmp_path):
    h = lue_kayttoonotot(kayttoonotot(tmp_path / "k"), omistaja=UID)
    assert h.tila == "ready" and h.kirjaukset[0]["tulos_teksti"] == "Otettu käyttöön" and h.meta["maara"] == 1
    assert lue_kayttoonotot(tmp_path / "ei", omistaja=UID).tila == "not_published"
    assert lue_kayttoonotot(tmp_path / "k", omistaja=UID + 1).tila == "error"


@pytest.mark.parametrize("muutos", [
    {"meta_muutos": {"sha256": "0" * 64}}, {"meta_muutos": {"maara": 2}}, {"meta_muutos": {"muoto": "x"}},
    {"rivit": [{"aika": "x", "kesto_s": 1, "commit": "d" * 40, "edellinen": "", "tulos": "keksitty", "vaihe": "", "viesti": "", "testit": "", "loki": ""}]},
    {"rivit": [{"aika": "x", "kesto_s": "1", "commit": "d" * 40, "edellinen": "", "tulos": "virhe", "vaihe": "", "viesti": "", "testit": "", "loki": ""}]},
    {"rivit": [{"aika": "x", "kesto_s": 1, "commit": "lyhyt", "edellinen": "", "tulos": "virhe", "vaihe": "", "viesti": "", "testit": "", "loki": ""}]},
    {"rivit": [{"aika": "x", "kesto_s": 1, "commit": "d" * 40, "edellinen": "", "tulos": "virhe", "vaihe": "\x07", "viesti": "", "testit": "", "loki": ""}]},
    {"raaka": b"{ei json"},
])
def test_ristiriitainen_historia_ei_nay(tmp_path, muutos):
    assert lue_kayttoonotot(kayttoonotot(tmp_path / "k", **muutos), omistaja=UID).tila == "error"


def test_esimerkkiaineisto_kelpaa():
    tyot = lue_kehitystyot(ESIMERKKI)
    assert [t.tyo for t in tyot] == [42, 41, 40] and all(t.virheet == () for t in tyot)
    assert lue_kehitystyo(ESIMERKKI, 41).vaihe == ("Otettu käyttöön", "success")
    assert lue_kayttoonotot(ESIMERKKI_KAYTTOONOTOT, omistaja=None).tila == "ready"


# --- 31.10.: eteneminen, palautus, toimet ja diff tiedostoittain ------------------------------------------------------


def test_eteneminen_ja_ansi_siivotaan(tmp_path):
    m = meta(tila="running", tulos={"paluukoodi": 0, "testit": {"paluukoodi": 0, "yhteenveto": "\x1b[2m Duration \x1b[22m 343ms"}},
             eteneminen=["11:05 dsh alkaa", 5, "  ", "Luen README.md\x07", "x" * 300] + ["y"] * 20)
    julkaise(tmp_path, m=m)
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.meta["eteneminen"][:2] == ["11:05 dsh alkaa", "Luen README.md"] and len(t.meta["eteneminen"][2]) == 200
    assert len(t.meta["eteneminen"]) <= 10 and t.kesken is True and t.vaihe == ("Käynnissä", "muted")
    assert t.meta["tulos"]["testit"]["yhteenveto"] == " Duration  343ms"
    julkaise(tmp_path, m=meta(eteneminen="ei lista"))
    assert lue_kehitystyo(tmp_path, 41, omistajat=OMAT).meta["eteneminen"] == []


def test_palautus_ja_toimet(tmp_path):
    k = {"tulos": "asennettu", "viesti": "ok", "paluukoodi": 0, "edellinen": "e" * 40}
    p = {"paatos": "hyvaksytty", "aika": "x", "kuka": "elias", "commit": PAA, "kayttoonotto_pyynto": "k"}
    julkaise(tmp_path, paatos=p, yhdistys={"tila": "yhdistetty", "commit": "d" * 40}, kayttoonotto=k)
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.kayttoonotto["edellinen"] == "e" * 40 and t.toimet["palauta"] is True and t.kesken is False
    assert t.toimet == {"hyvaksy": False, "hylkaa": False, "muutos": False, "kayttoonotto": False, "palauta": True}
    julkaise(tmp_path, paatos={**p, "palautus_pyynto": "q", "palautus_commit": "e" * 40, "palautus_aika": "x"},
             yhdistys={"tila": "yhdistetty", "commit": "d" * 40}, kayttoonotto=k)
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.vaihe == ("Palautus pyydetty", "accent") and t.kesken is True and t.toimet["palauta"] is False
    julkaise(tmp_path, paatos={**p, "palautus_pyynto": "q"}, yhdistys={"tila": "yhdistetty", "commit": "d" * 40},
             kayttoonotto=k, palautus={"tulos": "asennettu", "viesti": "Tulos: asennettu", "paluukoodi": 0})
    t = lue_kehitystyo(tmp_path, 41, omistajat=OMAT)
    assert t.vaihe == ("Palautettu edelliseen", "success") and t.kesken is False
    julkaise(tmp_path, paatos={**p, "palautus_pyynto": "q"}, yhdistys={"tila": "yhdistetty", "commit": "d" * 40},
             kayttoonotto=k, palautus={"tulos": "virhe", "viesti": "x", "paluukoodi": 2})
    assert lue_kehitystyo(tmp_path, 41, omistajat=OMAT).vaihe == ("Palautus: virhe", "danger")
    # ilman edellistä ei palautusta; valmis työ ilman päätöstä: hyväksy, hylkää, muutos (omat hakemistot: julkaise lisää)
    a, b, c, d = (tmp_path / n for n in "abcd")
    julkaise(a, paatos=p, yhdistys={"tila": "yhdistetty", "commit": "d" * 40}, kayttoonotto={**k, "edellinen": "lyhyt"})
    assert lue_kehitystyo(a, 41, omistajat=OMAT).toimet["palauta"] is False
    julkaise(b)
    t = lue_kehitystyo(b, 41, omistajat=OMAT)
    assert t.toimet == {"hyvaksy": True, "hylkaa": True, "muutos": True, "kayttoonotto": False, "palauta": False}
    julkaise(c, paatos={"paatos": "hyvaksytty", "aika": "x", "kuka": "elias"})
    t = lue_kehitystyo(c, 41, omistajat=OMAT)
    assert t.kesken is True and not any(t.toimet.values())
    julkaise(d, paatos={"paatos": "hyvaksytty", "aika": "x", "kuka": "elias"}, yhdistys={"tila": "yhdistetty", "commit": "d" * 40})
    assert lue_kehitystyo(d, 41, omistajat=OMAT).toimet["kayttoonotto"] is True


def test_diff_jaetaan_tiedostoittain():
    from ilmari_ui.kehitys import jaa_diff
    teksti = ("diff --git a/src/a.py b/src/a.py\nindex 1..2 100644\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1,2 +1,3 @@\n x\n-y\n+y2\n+z\n"
              "diff --git a/kuva.png b/kuva.png\nBinary files a/kuva.png and b/kuva.png differ\n")
    d = jaa_diff(teksti)
    assert [x["tiedosto"] for x in d] == ["src/a.py", "kuva.png"]
    assert (d[0]["lisatty"], d[0]["poistettu"], d[1]["binaari"]) == (2, 1, True)
    assert [l for l, _ in d[0]["rivit"]] == ["meta", "meta", "meta", "meta", "hunk", "ctx", "del", "add", "add"]
    assert jaa_diff("") == [] and jaa_diff("+rivi\n")[0]["tiedosto"] == "(ilman otsikkoa)"
    iso = "diff --git a/x b/x\n" + "+r\n" * 5000
    assert jaa_diff(iso)[0]["leikattu"] is True and len(jaa_diff(iso)[0]["rivit"]) <= 4000
