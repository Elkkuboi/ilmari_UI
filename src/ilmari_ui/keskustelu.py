"""Keskustelu Hubissa (aiops 28.10.2026: Hub on keskustelun pääpaikka; ADR-0031 3.11.2026: säikeet).

Gateway julkaisee aktiivisen säikeen viimeisimmät viestit ja mallin tilan tiedostoon
/srv/aiops/ilmari/keskustelu/viestit.json (muoto v1 ilman säiettä tai v2 kentällä saie) ja säikeet kansioittain
tiedostoon saikeet.json (aiops-gw:ilmari-julkaisu). Hub näyttää ne ilman skriptiä (sivu päivittyy meta refreshillä)
ja lähettää uuden viestin, uuden säikeen, säikeen valinnan, nimen, kansion ja arkistoinnin tavallisilla lomakkeilla
gatewayn reitteihin (/ilmari/viesti, /ilmari/saie, /ilmari/saie/<id>/<toimi>) samassa alkuperässä (paluu=hub).
Hub ei kirjoita mitään itse.
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
SAIKEET_TIEDOSTO = "saikeet.json"
RAJA = 1024 * 1024
MUODOT = ("aiops-keskustelu-v1", "aiops-keskustelu-v2")
MUOTO = MUODOT[0]   # vanha muoto ilman säikeitä (testit ja vanha gateway)
SAIKEET_MUOTO = "aiops-saikeet-v1"
KENTAT = frozenset({"muoto", "paivitetty", "viimeisin", "malli", "viestit"})
KENTAT_V2 = KENTAT | {"saie"}
VIESTI_KENTAT = frozenset({"id", "aika", "lahettaja", "teksti"})
VIESTI_KENTAT_V2 = VIESTI_KENTAT | {"saie"}
SAIE_KENTAT = frozenset({"id", "nimi", "kansio", "nimen_lahde", "luotu", "arkistoitu", "kanava", "viesteja", "viimeisin"})
LAHETTAJAT = {"elias": "Elias", "ilmari": "Ilmari"}
VIESTI_MAX = 8000
VIESTEJA_MAX = 100
SAIKEITA_MAX = 200
NIMI_MAX = 60
KANSIO_MAX = 40


@dataclass(frozen=True)
class Keskustelu:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    paivitetty: str = ""
    viimeisin: int = 0
    malli: dict[str, Any] = field(default_factory=dict)
    viestit: tuple[dict[str, Any], ...] = ()
    saie: dict[str, Any] | None = None                      # aktiivinen säie (v2), None = ei säikeitä
    saikeet: tuple[dict[str, Any], ...] = ()                # kaikki säikeet tuorein ensin (saikeet.json)
    aktiivinen: int | None = None

    @property
    def kansiot(self) -> list[tuple[str, list[dict[str, Any]]]]:
        """Avoimet säikeet kansioittain: ensin ilman kansiota (""), sitten kansiot nimen mukaan."""
        ryhmat: dict[str, list[dict[str, Any]]] = {}
        for s in self.saikeet:
            if s["arkistoitu"] is None:
                ryhmat.setdefault(s["kansio"], []).append(s)
        return [(k, ryhmat[k]) for k in sorted(ryhmat, key=lambda k: (k != "", k.casefold()))]

    @property
    def arkistoidut(self) -> list[dict[str, Any]]:
        return [s for s in self.saikeet if s["arkistoitu"] is not None]

    @property
    def kansionimet(self) -> list[str]:
        return sorted({s["kansio"] for s in self.saikeet if s["kansio"]}, key=str.casefold)


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _siisti(arvo: Any, raja: int, rivinvaihdot: bool = False) -> str:
    if type(arvo) is not str:
        return ""
    return "".join(c for c in arvo.replace("\r\n", "\n") if _kelpaa(c, rivinvaihdot))[:raja]


def _saie(s: Any, *, vaadi_lista: bool) -> dict[str, Any]:
    """Säikeen tiedot julkaisusta: nimi ja kansio tekstiä, ei valtaa (koodataan näyttäessä)."""
    if type(s) is not dict or type(s.get("id")) is not int or s["id"] <= 0:
        _virhe("Säikeen kentät eivät vastaa muotoa.")
    if vaadi_lista and set(s) != SAIE_KENTAT:
        _virhe("Säikeen kentät eivät vastaa muotoa.")
    nimi = _siisti(s.get("nimi"), NIMI_MAX) or f"Säie {s['id']}"
    return {"id": s["id"], "nimi": nimi, "kansio": _siisti(s.get("kansio"), KANSIO_MAX),
            "nimen_lahde": _siisti(s.get("nimen_lahde"), 10), "luotu": _siisti(s.get("luotu"), 40),
            "arkistoitu": None if s.get("arkistoitu") is None else _siisti(s.get("arkistoitu"), 40),
            "kanava": _siisti(s.get("kanava"), 10) or "sovellus",
            "viesteja": s.get("viesteja") if type(s.get("viesteja")) is int and s["viesteja"] >= 0 else 0,
            "viimeisin": None if s.get("viimeisin") is None else _siisti(s.get("viimeisin"), 40)}


def _tarkista_saikeet(data: Any) -> tuple[tuple[dict[str, Any], ...], int | None]:
    if not isinstance(data, dict) or set(data) != {"muoto", "paivitetty", "aktiivinen", "saikeet"} or data["muoto"] != SAIKEET_MUOTO:
        _virhe("saikeet.json:n kentät eivät vastaa muotoa.")
    if type(data["saikeet"]) is not list or len(data["saikeet"]) > SAIKEITA_MAX:
        _virhe("saikeet.json:n säielista ei kelpaa.")
    aktiivinen = data["aktiivinen"] if type(data["aktiivinen"]) is int else None
    return tuple(_saie(s, vaadi_lista=True) for s in data["saikeet"]), aktiivinen


def _tarkista(data: Any) -> Keskustelu:
    if not isinstance(data, dict) or data.get("muoto") not in MUODOT:
        _virhe("viestit.json:n kentät eivät vastaa muotoa.")
    v2 = data["muoto"] == MUODOT[1]
    if set(data) != (KENTAT_V2 if v2 else KENTAT):
        _virhe("viestit.json:n kentät eivät vastaa muotoa.")
    if type(data["viimeisin"]) is not int or type(data["viestit"]) is not list or len(data["viestit"]) > VIESTEJA_MAX:
        _virhe("viestit.json:n viestilista ei kelpaa.")
    malli_raaka = data["malli"] if isinstance(data["malli"], dict) else {}
    malli = {"tila": _siisti(malli_raaka.get("tila"), 30), "tila_teksti": _siisti(malli_raaka.get("tila_teksti"), 60),
             "tyo": malli_raaka.get("tyo") if type(malli_raaka.get("tyo")) is int else None,
             "dsh_tyo": malli_raaka.get("dsh_tyo") if type(malli_raaka.get("dsh_tyo")) is int else None,
             "yoajo": malli_raaka.get("yoajo") is True}
    saie = None
    if v2 and data["saie"] is not None:
        saie = _saie(data["saie"], vaadi_lista=False)
    viestit = []
    for v in data["viestit"]:
        if type(v) is not dict or set(v) != (VIESTI_KENTAT_V2 if v2 else VIESTI_KENTAT) or type(v["id"]) is not int:
            _virhe("Viestin kentät eivät vastaa muotoa.")
        lahettaja = _siisti(v["lahettaja"], 20)
        if lahettaja not in LAHETTAJAT:
            _virhe("Viestin lähettäjä on tuntematon.")
        viestit.append({"id": v["id"], "aika": _siisti(v["aika"], 40), "lahettaja": lahettaja,
                        "nimi": LAHETTAJAT[lahettaja], "teksti": _siisti(v["teksti"], VIESTI_MAX, rivinvaihdot=True)})
    return Keskustelu("ready", None, _siisti(data["paivitetty"], 40), data["viimeisin"], malli, tuple(viestit), saie)


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
            keskustelu = _tarkista(_json(data))
            # Säielista on valinnainen (vanha gateway ei julkaise sitä); rikkinäinen lista ei kaada keskustelua.
            try:
                tiedot = os.stat(SAIKEET_TIEDOSTO, dir_fd=hd, follow_symlinks=False)
                if omistajat is not None and tiedot.st_uid not in omistajat:
                    raise ReadFailure("wrong_owner", "Säielistan julkaisua ei ole tehnyt gateway.")
                lista = _lue(hd, SAIKEET_TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
                saikeet, aktiivinen = _tarkista_saikeet(_json(lista))
            except FileNotFoundError:
                saikeet, aktiivinen = (), None
            except ReadFailure as error:
                if error.code != "not_found":
                    raise
                saikeet, aktiivinen = (), None
        if keskustelu.saie is not None and aktiivinen is None:
            aktiivinen = keskustelu.saie["id"]
        return Keskustelu(keskustelu.tila, None, keskustelu.paivitetty, keskustelu.viimeisin, keskustelu.malli,
                          keskustelu.viestit, keskustelu.saie, saikeet, aktiivinen)
    except FileNotFoundError:
        return Keskustelu("not_published", "Gateway ei ole vielä julkaissut keskustelua.")
    except ReadFailure as error:
        if error.code == "not_found":
            return Keskustelu("not_published", "Gateway ei ole vielä julkaissut keskustelua.")
        return Keskustelu("error", error.message)
    except OSError as error:
        return Keskustelu("error", f"Keskustelua ei voi lukea ({error.strerror}).")
