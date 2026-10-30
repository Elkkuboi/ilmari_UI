"""Koneen mittarit (aiops jarjestelma.py, 30.10.2026): dispatcher (aiops-run) julkaisee tila.json-tiedoston 30 s välein
hakemistoon /srv/aiops/ilmari/jarjestelma, Hub lukee sen ryhmällä ilmari-julkaisu. Tuotannossa kelpaa vain
dispatcherin (aiops-run) tai rootin omistama tiedosto. Vain luku; ei komentoja eikä mittausta tässä prosessissa.
"""

from __future__ import annotations

import os
import pwd
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .dokumentit import _json, _kelpaa
from .peruskirja import ReadFailure, RunReader, _lue

OLETUS = Path("/srv/aiops/ilmari/jarjestelma")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "jarjestelma"
TIEDOSTO = "tila.json"
RAJA = 256 * 1024
MUOTO = "aiops-jarjestelma-v1"
KENTAT = frozenset({"muoto", "paivitetty", "cpu", "muisti", "gpu", "tyot"})
DISPATCHER_KAYTTAJA = "aiops-run"
VANHA_S = 120          # julkaisu 30 s välein; tätä vanhempi on "vanhentunut" (dispatcher ei käynnissä?)
TOITA_MAX = 20
TILAT = {"running": "käynnissä", "awaiting_gpu": "odottaa GPU:ta", "queued": "jonossa"}


@dataclass(frozen=True)
class Jarjestelma:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    paivitetty: str = ""
    ika_s: int | None = None
    vanhentunut: bool = False
    cpu: dict[str, Any] = field(default_factory=dict)
    muisti: dict[str, Any] | None = None
    gpu: dict[str, Any] | None = None
    tyot: tuple[dict[str, Any], ...] = ()


def sallitut_omistajat() -> frozenset[int] | None:
    """Tuotanto: root ja dispatcher (aiops-run). None = ei tarkistusta (kehitys ja esimerkkitila)."""
    omistajat = {0}
    try:
        omistajat.add(pwd.getpwnam(DISPATCHER_KAYTTAJA).pw_uid)
    except KeyError:
        pass
    return frozenset(omistajat)


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _siisti(arvo: Any, raja: int) -> str:
    if type(arvo) is not str:
        return ""
    return "".join(c for c in arvo if _kelpaa(c, False))[:raja]


def _luku(arvo: Any, alin: float, ylin: float) -> float | None:
    """Mittari lukuna rajojen sisällä, muuten None (näytetään viivana)."""
    if type(arvo) is bool or type(arvo) not in (int, float):
        return None
    return arvo if alin <= arvo <= ylin else None


def _tarkista(data: Any, now: datetime) -> Jarjestelma:
    if not isinstance(data, dict) or set(data) != KENTAT or data["muoto"] != MUOTO:
        _virhe("tila.json:n kentät eivät vastaa muotoa.")
    paivitetty = _siisti(data["paivitetty"], 40)
    try:
        aika = datetime.fromisoformat(paivitetty)
        ika = int((now - aika.astimezone(UTC)).total_seconds()) if aika.tzinfo is not None else None
    except ValueError:
        ika = None
    cpu_raaka = data["cpu"] if isinstance(data["cpu"], dict) else {}
    kuorma = cpu_raaka.get("kuorma")
    cpu = {"kaytto": _luku(cpu_raaka.get("kaytto"), 0, 100),
           "kuorma": [v for v in (kuorma if type(kuorma) is list else [])[:3] if _luku(v, 0, 100000) is not None],
           "ytimet": cpu_raaka.get("ytimet") if type(cpu_raaka.get("ytimet")) is int and 0 < cpu_raaka["ytimet"] < 10000 else None}
    muisti = None
    if isinstance(data["muisti"], dict):
        yhteensa, vapaa = _luku(data["muisti"].get("yhteensa_gb"), 0, 100000), _luku(data["muisti"].get("kaytettavissa_gb"), 0, 100000)
        if yhteensa is not None and vapaa is not None and vapaa <= yhteensa:
            muisti = {"yhteensa_gb": yhteensa, "kaytettavissa_gb": vapaa, "kaytossa_gb": round(yhteensa - vapaa, 1),
                      "prosentti": round(100 * (yhteensa - vapaa) / yhteensa) if yhteensa else 0}
    gpu = None
    if isinstance(data["gpu"], dict):
        g = data["gpu"]
        vram, vram_max = _luku(g.get("vram_kaytossa_gb"), 0, 10000), _luku(g.get("vram_yhteensa_gb"), 0, 10000)
        gpu = {"nimi": _siisti(g.get("nimi"), 60), "kayttoaste": _luku(g.get("kayttoaste"), 0, 100),
               "vram_kaytossa_gb": vram, "vram_yhteensa_gb": vram_max,
               "vram_prosentti": round(100 * vram / vram_max) if vram is not None and vram_max else None,
               "lampotila_c": _luku(g.get("lampotila_c"), -50, 200), "teho_w": _luku(g.get("teho_w"), 0, 5000)}
    tyot = []
    if type(data["tyot"]) is list:
        for t in data["tyot"][:TOITA_MAX]:
            if type(t) is not dict or type(t.get("id")) is not int:
                continue
            tila = _siisti(t.get("tila"), 20)
            tyot.append({"id": t["id"], "tyyppi": _siisti(t.get("tyyppi"), 20), "nimi": _siisti(t.get("nimi"), 64),
                         "malli": _siisti(t.get("malli"), 64), "tila": tila, "tila_teksti": TILAT.get(tila, tila),
                         "jattaja": _siisti(t.get("jattaja"), 40), "luotu": _siisti(t.get("luotu"), 40)})
    return Jarjestelma("ready", None, paivitetty, ika, ika is None or ika > VANHA_S, cpu, muisti, gpu, tuple(tyot))


def lue_jarjestelma(root: str | Path, *, omistajat: frozenset[int] | None = None, timeout_seconds: float = 2.0,
                    now: datetime | None = None) -> Jarjestelma:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa dispatcher (aiops-run) ja root."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Jarjestelma("error", "Mittareiden polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Mittareita ei ole julkaissut dispatcher.")
            tiedot = os.stat(TIEDOSTO, dir_fd=hd, follow_symlinks=False)
            if omistajat is not None and tiedot.st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Mittareita ei ole julkaissut dispatcher.")
            data = _lue(hd, TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
        return _tarkista(_json(data), now or datetime.now(UTC))
    except FileNotFoundError:
        return Jarjestelma("not_published", "Dispatcher ei ole vielä julkaissut mittareita.")
    except ReadFailure as error:
        if error.code == "not_found":
            return Jarjestelma("not_published", "Dispatcher ei ole vielä julkaissut mittareita.")
        return Jarjestelma("error", error.message)
    except OSError as error:
        return Jarjestelma("error", f"Mittareita ei voi lukea ({error.strerror}).")
