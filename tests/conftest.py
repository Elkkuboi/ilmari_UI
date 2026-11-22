"""Yhteiset testiapuvälineet.

Tuotantotilan lähteet ovat kiinteitä polkuja /srv/aiops/ilmari/... (moduulien OLETUS). Testikone on usein itse
työasema, joten jokainen testi ohjaa ne tyhjiin tmp-hakemistoihin: testi ei koskaan lue oikeaa tilaa. Testi, joka
tarvitsee lähteen, asettaa sen itse (monkeypatch.setattr toimii tämän päällä).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ilmari_ui import aivot, dokumentit, jarjestelma, kehitys, keskustelu, mallit, toiminta

LAHTEET = ((toiminta, "OLETUS"), (keskustelu, "OLETUS"), (kehitys, "OLETUS"), (kehitys, "OLETUS_KAYTTOONOTOT"),
           (mallit, "OLETUS"), (mallit, "OLETUS_ROOLIT"), (jarjestelma, "OLETUS"), (dokumentit, "OLETUS"),
           (aivot, "OLETUS"))
OLETUSPOLUT = {f"{moduuli.__name__.rsplit('.', 1)[1]}.{nimi}": getattr(moduuli, nimi) for moduuli, nimi in LAHTEET}


@pytest.fixture(autouse=True)
def eristetyt_lahteet(tmp_path_factory, monkeypatch):
    juuri = tmp_path_factory.mktemp("srv")
    for moduuli, nimi in LAHTEET:
        monkeypatch.setattr(moduuli, nimi, juuri / f"{moduuli.__name__.rsplit('.', 1)[1]}-{nimi.lower()}")


@pytest.fixture
def oletuspolut() -> dict[str, Path]:
    """Lähteiden alkuperäiset tuotantopolut (ennen eristystä)."""
    return dict(OLETUSPOLUT)
