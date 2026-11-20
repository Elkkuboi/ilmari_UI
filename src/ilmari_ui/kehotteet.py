"""Promptit ja säännöt (aiops 21.11.2026): jokainen teksti, jonka aiops antaa kielimalleille ohjeeksi.

Gateway (aiops-gw) kirjoittaa luettelon tiedostoon toiminta/kehotteet.json (aiops: src/aiops/gateway/kehotteet.py)
käynnistyessään ja aina, kun Elias muokkaa kehotetta. Luettelo kootaan samoista vakioista ja tiedostoista, joita
aiopsin koodi käyttää, joten teksti on se, minkä malli saa. Hub vain näyttää sen: muokkaus on gatewayn lomake
(POST /ilmari/kehote/{tunniste}, paluu=hub) ja palautus /ilmari/kehote/{tunniste}/oletus. Muokattavia ovat ne rivit,
joilla muokattava on tosi (järjestelmäkehote ja vuoron ohje); muut ovat aiopsin koodin vakioita.

Tiedosto luetaan yhteisellä lukijalla (lukija.py: linkkejä seuraamatta, omistaja, kokoraja, muuttumattomuus luvun
aikana) ja tarkoilla kenttäjoukoilla. Teksti on dataa: pohja koodaa sen, eikä sitä piirretä Markdownina.
Ryhmän nimi tulee gatewaylta (rivit ovat ryhmittäin peräkkäin), joten uusi ryhmä ei vaadi muutosta Hubiin.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lukija import Hakemisto, ReadFailure, _lue
from .toiminta import VIESTIT, _aika, _jasenna, _kentat, _stat, _teksti, _virhe

TIEDOSTO = "kehotteet.json"
RAJA = 1024 * 1024
KENTAT = frozenset({"versio", "aika", "kehotteet"})
RIVI_KENTAT = frozenset({"tunniste", "ryhma", "otsikko", "kuvaus", "lahde", "teksti", "oletus", "muokattu",
                         "muokattava", "enint"})
MAARA_MAX = 60
TEKSTI_MAX = 32_000
ENINT_MAX = 20_000                 # muokattavan tekstin yläraja, jonka gateway ilmoittaa (nyt 6 000)
OTSIKKO_MAX, KUVAUS_MAX, LAHDE_MAX, RYHMA_MAX = 80, 400, 200, 60
RIVEJA_MIN, RIVEJA_MAX, RIVIN_LEVEYS = 10, 40, 60   # muokkauskentän korkeus tekstin mukaan (puhelimen rivinleveys)
# Säännöt julkaisee aiopsin asennus dokumentteina; nämä näytetään samalla sivulla, jos ne ovat asennetussa versiossa.
SAANTODOKUMENTIT = ("saannot", "agents")
_TUNNISTE = re.compile(r"[a-z][a-z0-9_]{0,39}\Z", re.ASCII)


@dataclass(frozen=True)
class Kehotteet:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    aika: str | None = None
    kehotteet: tuple[dict[str, Any], ...] = ()


def tarkista(data: Any) -> tuple[str, tuple[dict[str, Any], ...]]:
    """kehotteet.json tarkoilla kentillä. Muokkauksen tiedot (oletus ja muokattu) ovat joko molemmat tai eivät
    kumpikaan, ja vain muokattavalla rivillä: kiinteää tekstiä ei voi esittää muokattuna."""
    _kentat(data, KENTAT, TIEDOSTO)
    aika = _aika(data["aika"])
    lista = data["kehotteet"]
    if type(lista) is not list or not 0 < len(lista) <= MAARA_MAX:
        _virhe("Luettelo ei kelpaa.")
    rivit, nahty = [], set()
    for r in lista:
        _kentat(r, RIVI_KENTAT, "kehote")
        tunniste = r["tunniste"]
        if type(tunniste) is not str or _TUNNISTE.fullmatch(tunniste) is None or tunniste in nahty:
            _virhe("Kehotteen tunniste ei kelpaa tai toistuu.")
        nahty.add(tunniste)
        if type(r["muokattava"]) is not bool or type(r["enint"]) is not int or not 0 < r["enint"] <= ENINT_MAX:
            _virhe("Kehotteen muokkaustiedot eivät kelpaa.")
        oletus = None if r["oletus"] is None else _teksti(r["oletus"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True)
        muokattu = _aika(r["muokattu"], tyhja=True)
        if (oletus is None) != (muokattu is None) or (oletus is not None and not r["muokattava"]):
            _virhe("Kehotteen muokkaustiedot ovat ristiriitaiset.")
        rivit.append({
            "tunniste": tunniste, "ryhma": _teksti(r["ryhma"], RYHMA_MAX, tyhja=False),
            "otsikko": _teksti(r["otsikko"], OTSIKKO_MAX, tyhja=False),
            "kuvaus": _teksti(r["kuvaus"], KUVAUS_MAX, tyhja=False), "lahde": _teksti(r["lahde"], LAHDE_MAX, tyhja=False),
            "teksti": _teksti(r["teksti"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True), "oletus": oletus,
            "muokattu": muokattu, "muokattava": r["muokattava"], "enint": r["enint"]})
    return aika, tuple(rivit)


def lue_kehotteet(root: str | Path, *, omistajat: frozenset[int] | None = None,
                  timeout_seconds: float = 2.0) -> Kehotteet:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa gateway (aiops-gw) ja root."""
    try:
        kavelija = Hakemisto(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Kehotteet("error", "Polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija.juuri(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Hakemiston omistaja on väärä.")
            tiedot = _stat(hd, TIEDOSTO, omistajat)
            if tiedot is None:
                return Kehotteet("not_published", "Prompteja ei ole vielä tallennettu.")
            raaka = _lue(hd, TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
        aika, rivit = tarkista(_jasenna(raaka))
        return Kehotteet("ready", None, aika, rivit)
    except ReadFailure as error:
        if error.code == "not_found":
            return Kehotteet("not_published", "Prompteja ei ole vielä tallennettu.")
        return Kehotteet("error", VIESTIT.get(error.code, error.message))
    except OSError as error:
        return Kehotteet("error", f"Prompteja ei voi lukea ({error.strerror}).")


def ryhmittain(luettelo: Kehotteet) -> list[tuple[str, list[dict[str, Any]]]]:
    """Ryhmät ensimmäisen esiintymän järjestyksessä; rivit ryhmän sisällä luettelon järjestyksessä."""
    ryhmat: dict[str, list[dict[str, Any]]] = {}
    for rivi in luettelo.kehotteet:
        ryhmat.setdefault(rivi["ryhma"], []).append(rivi)
    return list(ryhmat.items())


def etsi(luettelo: Kehotteet, tunniste: str) -> dict[str, Any] | None:
    if _TUNNISTE.fullmatch(tunniste) is None:
        return None
    return next((r for r in luettelo.kehotteet if r["tunniste"] == tunniste), None)


def korkeus(teksti: str) -> int:
    """Muokkauskentän rivimäärä: pitkät rivit rivittyvät puhelimella, joten ne lasketaan useana."""
    riveja = sum(max(1, math.ceil(len(rivi) / RIVIN_LEVEYS)) for rivi in teksti.split("\n"))
    return max(RIVEJA_MIN, min(RIVEJA_MAX, riveja + 2))
