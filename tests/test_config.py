"""Tuotantokonfiguraatio /etc/ilmari-hub/hub.toml (aiops ADR-0013 kohta 2): tiukka jäsennys, suljettu oletus."""

from __future__ import annotations

from pathlib import Path

import pytest

from ilmari_ui.config import ConfigError, load_config, parse_config

ESIMERKKI = Path(__file__).resolve().parents[1] / "config" / "hub.toml.esimerkki"
KELPO = """\
[hub]
rp_id = "tyoasema.taild1a5b7.ts.net"
julkaisut = "/srv/aiops/ilmari/ajot"

[hub.kayttajat]
"Elkkuboi@github" = "elias"
"""


def _kirjoita(tmp_path: Path, teksti: str | bytes) -> Path:
    polku = tmp_path / "hub.toml"
    polku.write_bytes(teksti.encode() if isinstance(teksti, str) else teksti)
    return polku


def test_kelvollinen_tiedosto(tmp_path):
    c = load_config(_kirjoita(tmp_path, KELPO))
    assert c.rp_id == "tyoasema.taild1a5b7.ts.net"
    assert c.origin == "https://tyoasema.taild1a5b7.ts.net"
    assert c.runs_dir == Path("/srv/aiops/ilmari/ajot")
    assert dict(c.users) == {"Elkkuboi@github": "elias"}
    with pytest.raises(TypeError):
        c.users["toinen@github"] = "x"  # lista ei muutu ajon aikana


def test_repon_esimerkki_kelpaa():
    c = load_config(ESIMERKKI)
    assert c.runs_dir == Path("/srv/aiops/ilmari/ajot") and dict(c.users) == {"tunnus@github": "elias"}


@pytest.mark.parametrize("muutos,virhe", [
    (lambda t: t + "\n[muu]\nx = 1\n", "tuntematon avain 'muu'"),
    (lambda t: t.replace('julkaisut =', 'kortit = "/x"\njulkaisut ='), "tuntematon avain 'kortit'"),
    (lambda t: t.replace("tyoasema.taild1a5b7.ts.net", "Tyoasema.taild1a5b7.ts.net"), "rp_id"),
    (lambda t: t.replace("tyoasema.taild1a5b7.ts.net", "tyoasema.taild1a5b7.ts.net:443"), "rp_id"),
    (lambda t: t.replace("tyoasema.taild1a5b7.ts.net", "tyoasema.taild1a5b7.ts.net."), "rp_id"),
    (lambda t: t.replace("tyoasema.taild1a5b7.ts.net", "localhost"), "rp_id"),
    (lambda t: t.replace('"/srv/aiops/ilmari/ajot"', '"srv/aiops/ilmari/ajot"'), "julkaisut"),
    (lambda t: t.replace('"/srv/aiops/ilmari/ajot"', '"/srv/aiops/../aiops/db"'), "julkaisut"),
    (lambda t: t.replace('"/srv/aiops/ilmari/ajot"', '"/"'), "julkaisut"),
    (lambda t: t.replace('"/srv/aiops/ilmari/ajot"', '"/srv/./aiops/ilmari/ajot"'), "julkaisut"),
    (lambda t: t.replace('"/srv/aiops/ilmari/ajot"', '"/srv/aiops/ilmari/ajot/"'), "julkaisut"),
    (lambda t: t.replace('"Elkkuboi@github" = "elias"', ''), "[hub.kayttajat] puuttuu tai on tyhjä"),
    (lambda t: t.replace('"Elkkuboi@github"', '"Elkku boi@github"'), "kelvoton tunnus"),
    (lambda t: t.replace('= "elias"', '= "Elias"'), "kelvoton nimi"),
    (lambda t: t.replace('= "elias"', '= 1'), "kelvoton nimi"),
    (lambda t: t.replace('rp_id = "tyoasema.taild1a5b7.ts.net"\n', ''), "rp_id"),
])
def test_kelvoton_tiedosto_hylataan(tmp_path, muutos, virhe):
    with pytest.raises(ConfigError, match=None) as e:
        load_config(_kirjoita(tmp_path, muutos(KELPO)))
    assert virhe in str(e.value)


@pytest.mark.parametrize("sisalto", [b"[hub\nrp_id = 1", b"\xff\xfe", b""])
def test_rikkinainen_tai_tyhja_tiedosto(tmp_path, sisalto):
    with pytest.raises(ConfigError):
        load_config(_kirjoita(tmp_path, sisalto))


def test_puuttuva_tiedosto(tmp_path):
    with pytest.raises(ConfigError, match="ei voi lukea"):
        load_config(tmp_path / "ei-ole.toml")


def test_hub_taulu_puuttuu():
    with pytest.raises(ConfigError, match=r"\[hub\] puuttuu"):
        parse_config({})
