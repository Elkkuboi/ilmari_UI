"""Mallirekisteri vain luku -tilassa (aiops istunto 3, SUUNNITELMA 3.1–3.2).

aiopsin asennus (scripts/julkaise_mallit.py, deploy.sh) julkaisee asennetun commitin mallirekisterin hakemistoon
/srv/aiops/ilmari/mallit kahtena tiedostona: mallit.json ja meta.json (muoto aiops-mallit-v1). Lukija noudattaa
dokumenttien sääntöjä: hakemisto ja tiedostot rootin, linkkejä seuraamatta, kokorajat, SHA-256 meta.json:sta, tiukka
JSON ja kenttien tarkistus. Hub vain näyttää roolit ja mallit; roolin vaihto tulee gatewayn kautta myöhemmin.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .dokumentit import _json, _kelpaa
from .peruskirja import _COMMIT, ReadFailure, RunReader, _lue

OLETUS = Path("/srv/aiops/ilmari/mallit")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "mallit"
DATA = "mallit.json"
META = "meta.json"
RAJA_DATA = 256 * 1024
RAJA_META = 4 * 1024
MUOTO = "aiops-mallit-v1"
META_KENTAT = frozenset({"muoto", "commit", "sha256", "koko", "maara", "julkaistu"})
DATA_KENTAT = frozenset({"muoto", "commit", "mallit", "roolit"})
MALLI_KENTAT = frozenset({"nimi", "kuvaus", "tyyppi", "sijainti", "konteksti_max", "vram_gb", "kuva", "tiedosto",
                          "koko", "manifesti", "tarjoaja", "hinnasto", "roolit"})
ROOLIT = (("ceo", "Ilmarin aivot (CEO)"), ("tyontekija", "Työntekijä (dsh)"), ("kirjoittaja", "Kirjoittaja"),
          ("tarkastaja", "Tarkastaja"), ("kallis_paattely", "Kallis päättely"), ("kuva", "Kuva"), ("aani", "Ääni"),
          ("yoajo", "Yöajo"))
SIJAINNIT = {"paikallinen": "paikallinen", "pilvi": "pilvi"}
TYYPIT = {"chat": "keskustelu", "kuva": "kuva", "video": "video", "tts": "puhe"}
MAARA_MAX = 50
_NIMI = re.compile(r"[a-z0-9][a-z0-9.-]{0,39}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VIESTIT = {
    "wrong_owner": "Mallirekisterin julkaisua ei ole tehnyt asennus (omistaja ei ole root).",
    "too_large": "Julkaistu rekisteri ylittää lukurajan.",
    "changed": "Julkaisu muuttui lukemisen aikana. Yritä uudelleen.",
    "unsafe_file": "Julkaisun tiedostotyyppi tai linkitys ei ole sallittu.",
    "timeout": "Rekisterin lukuaikaraja ylittyi.",
}


@dataclass(frozen=True)
class Mallit:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    meta: dict[str, Any] | None = None
    mallit: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    roolit: dict[str, str] = field(default_factory=dict)

    def roolirivit(self) -> list[dict[str, str]]:
        """Kaikki roolit järjestyksessä; täyttämätön rooli näkyy tyhjänä, ei nollana."""
        return [{"rooli": r, "otsikko": o, "malli": self.roolit.get(r, "")} for r, o in ROOLIT]


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _tarkista_meta(meta: Any, data: bytes) -> None:
    if not isinstance(meta, dict) or set(meta) != META_KENTAT or meta["muoto"] != MUOTO:
        _virhe("meta.json:n kentät eivät vastaa muotoa.")
    if type(meta["commit"]) is not str or _COMMIT.fullmatch(meta["commit"]) is None:
        _virhe("Julkaisun commit ei ole täysi tiiviste.")
    if type(meta["sha256"]) is not str or _SHA256.fullmatch(meta["sha256"]) is None:
        _virhe("Julkaisun tiiviste ei ole SHA-256.")
    if type(meta["koko"]) is not int or type(meta["maara"]) is not int:
        _virhe("Julkaisun koko tai määrä ei ole kokonaisluku.")
    try:
        aika = datetime.fromisoformat(meta["julkaistu"]) if type(meta["julkaistu"]) is str else None
    except ValueError:
        aika = None
    if aika is None or aika.tzinfo is None:
        _virhe("Julkaisuaika ei ole aikavyöhykkeellinen ISO-aika.")
    if meta["koko"] != len(data) or meta["sha256"] != hashlib.sha256(data).hexdigest():
        _virhe("Julkaisu on kesken tai ristiriitainen (tiiviste ei täsmää).")


def _tarkista_sisalto(sisalto: Any, meta: dict[str, Any]) -> tuple[tuple[dict[str, Any], ...], dict[str, str]]:
    if not isinstance(sisalto, dict) or set(sisalto) != DATA_KENTAT:
        _virhe("mallit.json:n kentät eivät vastaa muotoa.")
    if sisalto["muoto"] != MUOTO or sisalto["commit"] != meta["commit"]:
        _virhe("mallit.json ei vastaa meta.json:ia.")
    lista, roolit = sisalto["mallit"], sisalto["roolit"]
    if type(lista) is not list or not 0 < len(lista) <= MAARA_MAX or len(lista) != meta["maara"]:
        _virhe("Mallien määrä ei vastaa julkaisua.")
    tunnetut = {r for r, _ in ROOLIT}
    nahty: set[str] = set()
    mallit: list[dict[str, Any]] = []
    for m in lista:
        if type(m) is not dict or set(m) != MALLI_KENTAT:
            _virhe("Mallin kentät eivät vastaa muotoa.")
        tekstit = ("nimi", "kuvaus", "tyyppi", "sijainti", "kuva", "tiedosto", "manifesti", "tarjoaja", "hinnasto")
        if any(type(m[k]) is not str for k in tekstit) or any(type(m[k]) is not int for k in ("konteksti_max", "koko")):
            _virhe("Mallin kenttä on väärää tyyppiä.")
        if m["vram_gb"] is not None and type(m["vram_gb"]) is not int:
            _virhe("Mallin vram_gb ei ole kokonaisluku.")
        if _NIMI.fullmatch(m["nimi"]) is None or m["nimi"] in nahty:
            _virhe("Mallin nimi ei kelpaa tai toistuu.")
        if m["sijainti"] not in SIJAINNIT or m["tyyppi"] not in TYYPIT:
            _virhe("Mallin sijainti tai tyyppi on tuntematon.")
        if type(m["roolit"]) is not list or any(type(r) is not str or r not in tunnetut for r in m["roolit"]):
            _virhe("Mallin roolit eivät kelpaa.")
        if any(len(m[k]) > 300 or not _kelpaa(m[k], False) for k in tekstit):
            _virhe("Mallin kenttä on liian pitkä tai sisältää kielletyn merkin.")
        nahty.add(m["nimi"])
        mallit.append({**m, "sijainti_teksti": SIJAINNIT[m["sijainti"]], "tyyppi_teksti": TYYPIT[m["tyyppi"]],
                       "koko_gb": round(m["koko"] / 1e9, 1) if m["koko"] else None})
    if type(roolit) is not dict:
        _virhe("Roolit eivät ole taulu.")
    for rooli, nimi in roolit.items():
        if rooli not in tunnetut or type(nimi) is not str or nimi not in nahty:
            _virhe("Rooli osoittaa tuntemattomaan malliin.")
        if rooli not in next(m["roolit"] for m in mallit if m["nimi"] == nimi):
            _virhe("Rooli osoittaa malliin, joka ei tarjoa sitä.")
    return tuple(mallit), dict(roolit)


def lue_mallit(root: str | Path, *, omistaja: int | None = 0, timeout_seconds: float = 2.0) -> Mallit:
    """Lukee julkaistun mallirekisterin. omistaja=None vain kehitys- ja esimerkkitilassa."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Mallit("error", "Mallirekisterin polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            if omistaja is not None and os.fstat(hd).st_uid != omistaja:
                raise ReadFailure("wrong_owner", VIESTIT["wrong_owner"])
            data = _lue(hd, DATA, omistaja, deadline, RAJA_DATA)
            meta_raaka = _lue(hd, META, omistaja, deadline, RAJA_META)
        meta = _json(meta_raaka)
        _tarkista_meta(meta, data)
        mallit, roolit = _tarkista_sisalto(_json(data), meta)
        return Mallit("ready", None, meta, mallit, roolit)
    except ReadFailure as error:
        if error.code == "not_found":
            return Mallit("not_published", "Mallirekisteriä ei ole julkaistu. aiopsin asennus (deploy.sh) julkaisee sen.")
        return Mallit("error", VIESTIT.get(error.code, error.message))
