"""Yhteinen turvallinen lukija (lukija.py): käsin tehdyt tiedostojärjestelmän tilanteet, molemmat suunnat.

Siirretty ajojen lukijan testeistä (runs.py poistettiin 18.11.2026), koska kaikki Hubin lukijat käyttävät samaa
hakemisto- ja tiedostolukua.
"""

import os
import time
from pathlib import Path

import pytest

from ilmari_ui import lukija
from ilmari_ui.lukija import Hakemisto, ReadFailure, _lue

RAJA = 1024


@pytest.fixture
def juuri(tmp_path: Path) -> Path:
    hak = tmp_path / "julkaisu"
    (hak / "7").mkdir(parents=True)
    (hak / "tieto.json").write_text('{"a": 1}', encoding="utf-8")
    (hak / "7" / "meta.json").write_text('{"tyo": 7}', encoding="utf-8")
    return hak


def lue(hak: Path, nimi: str = "tieto.json", omistaja: int | None = None, raja: int = RAJA) -> bytes:
    with Hakemisto(hak).juuri(time.monotonic() + 1) as hd:
        return _lue(hd, nimi, omistaja, time.monotonic() + 1, raja)


def test_kelvollinen_tiedosto_ja_alihakemisto(juuri):
    assert lue(juuri) == b'{"a": 1}'
    assert lue(juuri, omistaja=os.getuid()) == b'{"a": 1}'
    h = Hakemisto(juuri)
    with h.juuri(time.monotonic() + 1) as hd, h.ali(hd, "7") as ad:
        assert _lue(ad, "meta.json", None, time.monotonic() + 1, RAJA) == b'{"tyo": 7}'


@pytest.mark.parametrize("root", ["relative/x", "/tmp/../x", "/tmp/./x", "/tmp//x", "/", "/tmp/x/", "/tmp/x\\y",
                                  "/tmp/x\0y"])
def test_kelvoton_polku_hylataan_ennen_lukua(root):
    with pytest.raises(ValueError):
        Hakemisto(root)


def test_linkki_polussa_hylataan(juuri, tmp_path):
    (tmp_path / "linkki").symlink_to(juuri, target_is_directory=True)
    with pytest.raises(ReadFailure) as virhe:
        lue(tmp_path / "linkki")
    assert virhe.value.code == "unsafe_path"


def test_linkki_alihakemistona_hylataan(juuri):
    (juuri / "8").symlink_to(juuri / "7", target_is_directory=True)
    h = Hakemisto(juuri)
    with pytest.raises(ReadFailure) as virhe:
        with h.juuri(time.monotonic() + 1) as hd, h.ali(hd, "8"):
            pass
    assert virhe.value.code == "unsafe_path"


def test_puuttuva_on_not_found(juuri, tmp_path):
    with pytest.raises(ReadFailure) as virhe:
        lue(tmp_path / "ei-ole")
    assert virhe.value.code == "not_found"
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri, "ei-ole.json")
    assert virhe.value.code == "not_found"


def test_tiedostolinkki_ja_kova_linkki_hylataan(juuri):
    (juuri / "linkki.json").symlink_to(juuri / "tieto.json")
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri, "linkki.json")
    assert virhe.value.code == "unsafe_file"
    os.link(juuri / "tieto.json", juuri / "toinen.json")
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri)
    assert virhe.value.code == "unsafe_file"


@pytest.mark.parametrize("laji", ["fifo", "hakemisto"])
def test_erikoistiedosto_ei_jumita(juuri, laji):
    kohde = juuri / "erikois.json"
    os.mkfifo(kohde) if laji == "fifo" else kohde.mkdir()
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri, "erikois.json")
    assert virhe.value.code == "unsafe_file"


def test_kokoraja_ja_omistaja(juuri):
    (juuri / "iso.json").write_bytes(b"x" * (RAJA + 1))
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri, "iso.json")
    assert virhe.value.code == "too_large"
    assert lue(juuri, "iso.json", raja=RAJA + 1) == b"x" * (RAJA + 1)
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri, omistaja=os.getuid() + 1)
    assert virhe.value.code == "wrong_owner"


def test_tiedoston_vaihto_avauksen_valissa_hylataan(juuri, monkeypatch):
    oikea_open = lukija.os.open
    vaihdettu = False

    def vaihtava_open(polku, liput, *args, **kwargs):
        nonlocal vaihdettu
        if polku == "tieto.json" and not vaihdettu:
            vaihdettu = True
            (juuri / "tieto.json").rename(juuri / "vanha.json")
            (juuri / "tieto.json").write_text("vaihdettu", encoding="utf-8")
        return oikea_open(polku, liput, *args, **kwargs)
    monkeypatch.setattr(lukija.os, "open", vaihtava_open)
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri)
    assert virhe.value.code == "changed"


def test_juuren_vaihto_luvun_aikana_hylataan(juuri, monkeypatch):
    oikea_read = lukija.os.read
    vaihdettu = False

    def vaihtava_read(fd, maara):
        nonlocal vaihdettu
        tulos = oikea_read(fd, maara)
        if tulos.startswith(b'{"a"') and not vaihdettu:
            vaihdettu = True
            juuri.rename(juuri.parent / "vanha-juuri")
            juuri.mkdir()
        return tulos
    monkeypatch.setattr(lukija.os, "read", vaihtava_read)
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri)
    assert virhe.value.code == "changed"


def test_aikaraja(juuri, monkeypatch):
    hetket = iter([0.0, 5.0])
    monkeypatch.setattr(lukija.time, "monotonic", lambda: next(hetket, 5.0))
    with pytest.raises(ReadFailure) as virhe:
        with Hakemisto(juuri).juuri(1.0):
            pass
    assert virhe.value.code == "timeout"


def test_kayttooikeusvirhe_ei_paljasta_polkua(juuri, monkeypatch):
    oikea_open = lukija.os.open

    def kielletty(polku, liput, *args, **kwargs):
        if polku == "tieto.json":
            raise PermissionError(13, "salainen absoluuttinen polku")
        return oikea_open(polku, liput, *args, **kwargs)
    monkeypatch.setattr(lukija.os, "open", kielletty)
    with pytest.raises(ReadFailure) as virhe:
        lue(juuri)
    assert virhe.value.code == "forbidden"
    assert "salainen" not in virhe.value.message and str(juuri) not in virhe.value.message
