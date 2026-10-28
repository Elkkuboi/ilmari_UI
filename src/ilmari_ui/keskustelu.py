"""Keskustelu Hubissa (aiops 28.10.2026: Hub on keskustelun pääpaikka).

Gateway julkaisee viimeisimmät viestit ja mallin tilan tiedostoon /srv/aiops/ilmari/keskustelu/viestit.json
(aiops-gw:ilmari-julkaisu). Hub näyttää ne ilman skriptiä (sivu päivittyy meta refreshillä) ja lähettää uuden
viestin tavallisella lomakkeella gatewayn reittiin /ilmari/viesti samassa alkuperässä (paluu=hub). Hub ei kirjoita
mitään itse: viestit ja mallin käynnistys ovat gatewayn toimia, joihin lomake vain johtaa.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dokumentit import _json, _kelpaa
from .peruskirja import ReadFailure, RunReader, _lue

OLETUS = Path("/srv/aiops/ilmari/keskustelu")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "keskustelu"
TIEDOSTO = "viestit.json"
RAJA = 1024 * 1024
MUOTO = "aiops-keskustelu-v1"
KENTAT = frozenset({"muoto", "paivitetty", "viimeisin", "malli", "viestit"})
VIESTI_KENTAT = frozenset({"id", "aika", "lahettaja", "teksti"})
LAHETTAJAT = {"elias": "Elias", "ilmari": "Ilmari"}
VIESTI_MAX = 8000
VIESTEJA_MAX = 100


@dataclass(frozen=True)
class Keskustelu:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    paivitetty: str = ""
    viimeisin: int = 0
    malli: dict[str, Any] = field(default_factory=dict)
    viestit: tuple[dict[str, Any], ...] = ()


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _siisti(arvo: Any, raja: int, rivinvaihdot: bool = False) -> str:
    if type(arvo) is not str:
        return ""
    return "".join(c for c in arvo.replace("\r\n", "\n") if _kelpaa(c, rivinvaihdot))[:raja]


def _tarkista(data: Any) -> Keskustelu:
    if not isinstance(data, dict) or set(data) != KENTAT or data["muoto"] != MUOTO:
        _virhe("viestit.json:n kentät eivät vastaa muotoa.")
    if type(data["viimeisin"]) is not int or type(data["viestit"]) is not list or len(data["viestit"]) > VIESTEJA_MAX:
        _virhe("viestit.json:n viestilista ei kelpaa.")
    malli_raaka = data["malli"] if isinstance(data["malli"], dict) else {}
    malli = {"tila": _siisti(malli_raaka.get("tila"), 30), "tila_teksti": _siisti(malli_raaka.get("tila_teksti"), 60),
             "tyo": malli_raaka.get("tyo") if type(malli_raaka.get("tyo")) is int else None,
             "dsh_tyo": malli_raaka.get("dsh_tyo") if type(malli_raaka.get("dsh_tyo")) is int else None,
             "yoajo": malli_raaka.get("yoajo") is True}
    viestit = []
    for v in data["viestit"]:
        if type(v) is not dict or set(v) != VIESTI_KENTAT or type(v["id"]) is not int:
            _virhe("Viestin kentät eivät vastaa muotoa.")
        lahettaja = _siisti(v["lahettaja"], 20)
        if lahettaja not in LAHETTAJAT:
            _virhe("Viestin lähettäjä on tuntematon.")
        viestit.append({"id": v["id"], "aika": _siisti(v["aika"], 40), "lahettaja": lahettaja,
                        "nimi": LAHETTAJAT[lahettaja], "teksti": _siisti(v["teksti"], VIESTI_MAX, rivinvaihdot=True)})
    return Keskustelu("ready", None, _siisti(data["paivitetty"], 40), data["viimeisin"], malli, tuple(viestit))


def lue_keskustelu(root: str | Path, *, omistajat: frozenset[int] | None = None,
                   timeout_seconds: float = 2.0) -> Keskustelu:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa gateway (aiops-gw) ja root."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Keskustelu("error", "Keskustelun polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Keskustelun julkaisua ei ole tehnyt gateway.")
            tiedot = os.stat(TIEDOSTO, dir_fd=hd, follow_symlinks=False)
            if omistajat is not None and tiedot.st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Keskustelun julkaisua ei ole tehnyt gateway.")
            data = _lue(hd, TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
        return _tarkista(_json(data))
    except FileNotFoundError:
        return Keskustelu("not_published", "Gateway ei ole vielä julkaissut keskustelua.")
    except ReadFailure as error:
        if error.code == "not_found":
            return Keskustelu("not_published", "Gateway ei ole vielä julkaissut keskustelua.")
        return Keskustelu("error", error.message)
    except OSError as error:
        return Keskustelu("error", f"Keskustelua ei voi lukea ({error.strerror}).")
