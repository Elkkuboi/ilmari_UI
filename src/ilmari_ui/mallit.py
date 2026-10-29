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
DATA_VALINNAISET = frozenset({"profiilit"})          # aivoprofiilit (aiops ADR-0029)
MALLI_KENTAT = frozenset({"nimi", "kuvaus", "tyyppi", "sijainti", "konteksti_max", "vram_gb", "kuva", "tiedosto",
                          "koko", "manifesti", "tarjoaja", "hinnasto", "roolit"})
MALLI_VALINNAISET = frozenset({"moottori", "ram_gb", "kuvat"})   # ADR-0029: moottori, muistiraja, kuvat
PROFIILI_KENTAT = frozenset({"kuvaus", "roolit", "ram_gb"})
PROFIILIEN_ROOLIT = ("ceo", "tyontekija", "kirjoittaja", "kuva_tulkki")
RAM_MARGINAALI_GB = 2
MEMINFO = Path("/proc/meminfo")
ROOLIT = (("ceo", "Ilmarin aivot (CEO)"), ("tyontekija", "Työntekijä (dsh)"), ("kirjoittaja", "Kirjoittaja"),
          ("tarkastaja", "Tarkastaja"), ("kallis_paattely", "Kallis päättely"), ("kuva_tulkki", "Kuvantulkinta (Hubin valinta)"),
          ("kuva_tulkki_pilvi", "Kuvantulkinta pilvessä"), ("kuva_tulkki_paikallinen", "Kuvantulkinta paikallisesti"),
          ("kuva", "Kuva"), ("aani", "Ääni"), ("yoajo", "Yöajo"))
OLETUS_ROOLIT = Path("/srv/aiops/ilmari/roolit")
YLIKIRJOITUS = "roolit.toml"
RAJA_YLIKIRJOITUS = 16 * 1024
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
    profiilit: dict[str, dict[str, Any]] = field(default_factory=dict)

    def nykyinen_profiili(self, ylikirjoitus: dict[str, str] | None = None) -> str | None:
        """Profiili, jonka kaikki roolit täsmäävät nykyisiin valintoihin (ylikirjoitus voittaa rekisterin), tai None."""
        nyt = {**self.roolit, **{r: m for r, m in (ylikirjoitus or {}).items() if m}}
        for r, m in (ylikirjoitus or {}).items():
            if m == "":
                nyt.pop(r, None)
        for nimi, p in self.profiilit.items():
            if all(nyt.get(r) == m for r, m in p["roolit"].items()):
                return nimi
        return None

    def roolirivit(self, ylikirjoitus: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """Kaikki roolit järjestyksessä; täyttämätön rooli näkyy tyhjänä, ei nollana. Ylikirjoitus (Eliaksen valinta
        gatewayn kautta) korvaa rekisterin arvon; vaihtoehdot ovat rekisterin mallit, jotka tarjoavat roolin."""
        yk = ylikirjoitus or {}
        rivit = []
        for r, o in ROOLIT:
            nyt = yk[r] if r in yk else self.roolit.get(r, "")
            rivit.append({"rooli": r, "otsikko": o, "malli": nyt, "oletus": self.roolit.get(r, ""),
                          "valittu": r in yk, "vaihtoehdot": [m["nimi"] for m in self.mallit if r in m["roolit"]]})
        return rivit


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


def vapaa_ram_gb(polku: Path = MEMINFO) -> float | None:
    """Käytettävissä oleva RAM gigatavuina (MemAvailable), tai None. Sama laskutapa kuin aiopsin gatewayssa."""
    try:
        for rivi in polku.read_text(encoding="ascii").splitlines():
            if rivi.startswith("MemAvailable:"):
                return round(int(rivi.split()[1]) / 1_000_000, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


def _tarkista_profiilit(raaka: Any, mallit: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if type(raaka) is not dict or len(raaka) > 10:
        _virhe("Profiilit eivät ole taulu.")
    nimet = {m["nimi"]: m for m in mallit}
    tulos: dict[str, dict[str, Any]] = {}
    for nimi, p in raaka.items():
        if type(nimi) is not str or _NIMI.fullmatch(nimi) is None or type(p) is not dict or set(p) != PROFIILI_KENTAT:
            _virhe("Profiilin kentät eivät vastaa muotoa.")
        if type(p["kuvaus"]) is not str or len(p["kuvaus"]) > 300 or not _kelpaa(p["kuvaus"], False):
            _virhe("Profiilin kuvaus ei kelpaa.")
        if p["ram_gb"] is not None and type(p["ram_gb"]) is not int:
            _virhe("Profiilin ram_gb ei ole kokonaisluku.")
        roolit = p["roolit"]
        if type(roolit) is not dict or set(roolit) != set(PROFIILIEN_ROOLIT):
            _virhe("Profiilin roolit eivät vastaa muotoa.")
        for rooli, malli in roolit.items():
            if type(malli) is not str or malli not in nimet or rooli not in nimet[malli]["roolit"]:
                _virhe("Profiilin rooli osoittaa malliin, joka ei tarjoa sitä.")
        tulos[nimi] = {"nimi": nimi, "kuvaus": p["kuvaus"], "roolit": dict(roolit), "ram_gb": p["ram_gb"]}
    return tulos


def _tarkista_sisalto(sisalto: Any, meta: dict[str, Any]) -> tuple[tuple[dict[str, Any], ...], dict[str, str],
                                                                    dict[str, dict[str, Any]]]:
    if not isinstance(sisalto, dict) or not DATA_KENTAT <= set(sisalto) <= DATA_KENTAT | DATA_VALINNAISET:
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
        if type(m) is not dict or not MALLI_KENTAT <= set(m) <= MALLI_KENTAT | MALLI_VALINNAISET:
            _virhe("Mallin kentät eivät vastaa muotoa.")
        if ("moottori" in m and (type(m["moottori"]) is not str or len(m["moottori"]) > 20 or not _kelpaa(m["moottori"], False))
                or ("ram_gb" in m and m["ram_gb"] is not None and type(m["ram_gb"]) is not int)
                or ("kuvat" in m and type(m["kuvat"]) is not bool)):
            _virhe("Mallin moottori, ram_gb tai kuvat ei kelpaa.")
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
        mallit.append({"moottori": "", "ram_gb": None, "kuvat": False, **m, "sijainti_teksti": SIJAINNIT[m["sijainti"]],
                       "tyyppi_teksti": TYYPIT[m["tyyppi"]], "koko_gb": round(m["koko"] / 1e9, 1) if m["koko"] else None})
    if type(roolit) is not dict:
        _virhe("Roolit eivät ole taulu.")
    for rooli, nimi in roolit.items():
        if rooli not in tunnetut or type(nimi) is not str or nimi not in nahty:
            _virhe("Rooli osoittaa tuntemattomaan malliin.")
        if rooli not in next(m["roolit"] for m in mallit if m["nimi"] == nimi):
            _virhe("Rooli osoittaa malliin, joka ei tarjoa sitä.")
    profiilit = _tarkista_profiilit(sisalto["profiilit"], mallit) if "profiilit" in sisalto else {}
    return tuple(mallit), dict(roolit), profiilit


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
        mallit, roolit, profiilit = _tarkista_sisalto(_json(data), meta)
        return Mallit("ready", None, meta, mallit, roolit, profiilit)
    except ReadFailure as error:
        if error.code == "not_found":
            return Mallit("not_published", "Mallirekisteriä ei ole julkaistu. aiopsin asennus (deploy.sh) julkaisee sen.")
        return Mallit("error", VIESTIT.get(error.code, error.message))


def lue_ylikirjoitus(root: str | Path, *, omistajat: frozenset[int] | None = None,
                     timeout_seconds: float = 1.0) -> dict[str, str] | None:
    """Eliaksen roolivalinnat (gateway kirjoittaa roolit.toml:n). None, jos tiedostoa ei ole tai se ei kelpaa."""
    import tomllib
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return None
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            tiedot = os.stat(YLIKIRJOITUS, dir_fd=hd, follow_symlinks=False)
            if omistajat is not None and tiedot.st_uid not in omistajat:
                return None
            data = _lue(hd, YLIKIRJOITUS, tiedot.st_uid if omistajat is not None else None, deadline, RAJA_YLIKIRJOITUS)
        parsed = tomllib.loads(data.decode("utf-8"))
    except (ReadFailure, OSError, ValueError, UnicodeDecodeError):
        return None
    roolit = parsed.get("roolit") if isinstance(parsed, dict) else None
    if not isinstance(roolit, dict):
        return None
    tunnetut = {r for r, _ in ROOLIT}
    return {r: m for r, m in roolit.items() if r in tunnetut and type(m) is str and _NIMI.fullmatch(m or "a") is not None and len(m) <= 40}
