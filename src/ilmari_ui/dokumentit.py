"""Dokumentit vain luku -tilassa (aiops istunto 2, 28.10.2026).

aiopsin asennus (scripts/julkaise_dokumentit.py, ajetaan deploy.sh:sta) julkaisee asennetun commitin dokumentit
hakemistoon /srv/aiops/ilmari/dokumentit kahtena tiedostona: dokumentit.json ja meta.json (muoto aiops-dokumentit-v1).
Lukija noudattaa peruskirjan sääntöjä ja käyttää sen tiedostonlukijaa: hakemisto ja tiedostot ovat rootin, tiedostot
luetaan linkkejä seuraamatta ja aikarajan sisällä, ja dokumentit näytetään vain, jos dokumentit.json:n SHA-256 ja koko
ovat meta.json:n arvot. Jokaisen dokumentin kentät ja teksti tarkistetaan uudelleen (sama merkkirajaus kuin
peruskirjassa). Teksti piirretään peruskirjan rajatulla Markdownilla (jasenna) ilman raakaa HTML:ää.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .peruskirja import _COMMIT, ReadFailure, RunReader, _lue, jasenna

OLETUS = Path("/srv/aiops/ilmari/dokumentit")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "dokumentit"
DATA = "dokumentit.json"
META = "meta.json"
RAJA_DATA = 6 * 1024 * 1024
RAJA_META = 4 * 1024
MUOTO = "aiops-dokumentit-v1"
META_KENTAT = frozenset({"muoto", "commit", "sha256", "koko", "maara", "julkaistu"})
DATA_KENTAT = frozenset({"muoto", "commit", "dokumentit"})
DOK_KENTAT = frozenset({"tunniste", "polku", "ryhma", "otsikko", "tila", "paiva", "teksti"})
RYHMAT = (("perus", "Perusdokumentit"), ("adr", "Päätökset (ADR)"), ("valmistelu", "Valmistelu"),
          ("historia", "Historia"), ("audit", "Auditointi"))
MAARA_MAX = 300
TEKSTI_MAX = 256 * 1024
HAKU_MAX = 100
OSUMIA_MAX = 50
_TUNNISTE = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")
_POLKU = re.compile(r"docs/[A-Za-z0-9._/-]{1,200}\.md\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VIESTIT = {
    "wrong_owner": "Dokumenttien julkaisua ei ole tehnyt asennus (omistaja ei ole root).",
    "too_large": "Julkaistut dokumentit ylittävät lukurajan.",
    "changed": "Julkaisu muuttui lukemisen aikana. Yritä uudelleen.",
    "unsafe_file": "Julkaisun tiedostotyyppi tai linkitys ei ole sallittu.",
    "timeout": "Dokumenttien lukuaikaraja ylittyi.",
}


@dataclass(frozen=True)
class Dokumentit:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    meta: dict[str, Any] | None = None
    dokumentit: tuple[dict[str, str], ...] = field(default_factory=tuple)


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _kelpaa(teksti: str, rivinvaihdot: bool) -> bool:
    for c in teksti:
        o = ord(c)
        if c in "\n\r" and not rivinvaihdot:
            return False
        if (o < 32 and c not in "\n\r\t") or 0x202A <= o <= 0x202E or 0x2066 <= o <= 0x2069:
            return False
    return True


def _ei_toistoja(parit: list[tuple[str, Any]]) -> dict[str, Any]:
    tulos: dict[str, Any] = {}
    for avain, arvo in parit:
        if avain in tulos:
            _virhe("Julkaisun JSON-objektissa on sama kenttä kahdesti.")
        tulos[avain] = arvo
    return tulos


def _ei_vakioita(_arvo: str) -> None:
    _virhe("Julkaisun JSON sisältää kielletyn vakion.")


def _json(raaka: bytes) -> Any:
    try:
        teksti = raaka.decode("utf-8")
    except UnicodeDecodeError:
        _virhe("Julkaisu ei ole UTF-8-muodossa.")
    try:
        return json.loads(teksti, object_pairs_hook=_ei_toistoja, parse_constant=_ei_vakioita)
    except ReadFailure:
        raise
    except ValueError:
        _virhe("Julkaisu ei ole kelvollista JSONia.")


def _tarkista_meta(meta: Any, data: bytes) -> None:
    if not isinstance(meta, dict) or set(meta) != META_KENTAT:
        _virhe("meta.json:n kentät eivät vastaa muotoa.")
    if meta["muoto"] != MUOTO:
        _virhe("meta.json on tuntematonta muotoa.")
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


def _tarkista_sisalto(sisalto: Any, meta: dict[str, Any]) -> tuple[dict[str, str], ...]:
    if not isinstance(sisalto, dict) or set(sisalto) != DATA_KENTAT:
        _virhe("dokumentit.json:n kentät eivät vastaa muotoa.")
    if sisalto["muoto"] != MUOTO or sisalto["commit"] != meta["commit"]:
        _virhe("dokumentit.json ei vastaa meta.json:ia.")
    lista = sisalto["dokumentit"]
    if type(lista) is not list or not 0 < len(lista) <= MAARA_MAX or len(lista) != meta["maara"]:
        _virhe("Dokumenttien määrä ei vastaa julkaisua.")
    ryhmat = {avain for avain, _ in RYHMAT}
    nahty: set[str] = set()
    tulos: list[dict[str, str]] = []
    for d in lista:
        if type(d) is not dict or set(d) != DOK_KENTAT or any(type(v) is not str for v in d.values()):
            _virhe("Dokumentin kentät eivät vastaa muotoa.")
        if _TUNNISTE.fullmatch(d["tunniste"]) is None or d["tunniste"] in nahty:
            _virhe("Dokumentin tunniste ei kelpaa tai toistuu.")
        if _POLKU.fullmatch(d["polku"]) is None or ".." in d["polku"].split("/"):
            _virhe("Dokumentin polku ei kelpaa.")
        if d["ryhma"] not in ryhmat:
            _virhe("Dokumentin ryhmä on tuntematon.")
        if (not 0 < len(d["otsikko"]) <= 200 or len(d["tila"]) > 200 or len(d["paiva"]) > 40
                or len(d["teksti"]) > TEKSTI_MAX):
            _virhe("Dokumentin kenttä on liian pitkä.")
        if not all(_kelpaa(d[k], False) for k in ("otsikko", "tila", "paiva")) or not _kelpaa(d["teksti"], True):
            _virhe("Dokumentti sisältää kielletyn merkin.")
        nahty.add(d["tunniste"])
        tulos.append(dict(d))
    return tuple(tulos)


def lue_dokumentit(root: str | Path, *, omistaja: int | None = 0, timeout_seconds: float = 2.0) -> Dokumentit:
    """Lukee julkaistut dokumentit. omistaja=None vain kehitys- ja esimerkkitilassa."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Dokumentit("error", "Dokumenttien polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            if omistaja is not None and os.fstat(hd).st_uid != omistaja:
                raise ReadFailure("wrong_owner", VIESTIT["wrong_owner"])
            data = _lue(hd, DATA, omistaja, deadline, RAJA_DATA)
            meta_raaka = _lue(hd, META, omistaja, deadline, RAJA_META)
        meta = _json(meta_raaka)
        _tarkista_meta(meta, data)
        dokumentit = _tarkista_sisalto(_json(data), meta)
        return Dokumentit("ready", None, meta, dokumentit)
    except ReadFailure as error:
        if error.code == "not_found":
            return Dokumentit("not_published", "Dokumentteja ei ole julkaistu. aiopsin asennus (deploy.sh) julkaisee ne.")
        return Dokumentit("error", VIESTIT.get(error.code, error.message))


def piirrettava(dokumentti: dict[str, str]) -> tuple[tuple[dict[str, Any], ...] | None, str | None]:
    """Rajatun Markdownin lohkot (peruskirjan jasenna) tai virheilmoitus."""
    try:
        return jasenna(dokumentti["teksti"]), None
    except ReadFailure as error:
        return None, error.message


def ryhmittain(kokoelma: Dokumentit) -> list[tuple[str, str, list[dict[str, str]]]]:
    tulos = []
    for avain, otsikko in RYHMAT:
        rivit = [d for d in kokoelma.dokumentit if d["ryhma"] == avain]
        if rivit:
            tulos.append((avain, otsikko, rivit))
    return tulos


def etsi(kokoelma: Dokumentit, tunniste: str) -> dict[str, str] | None:
    if _TUNNISTE.fullmatch(tunniste) is None:
        return None
    return next((d for d in kokoelma.dokumentit if d["tunniste"] == tunniste), None)


def hae(kokoelma: Dokumentit, kysely: str) -> list[dict[str, Any]]:
    """Kirjainkoosta riippumaton haku otsikoista ja teksteistä; ote ensimmäisen osuman ympäriltä."""
    k = kysely.strip()
    if not k or len(k) > HAKU_MAX:
        return []
    kk = k.lower()
    osumat: list[dict[str, Any]] = []
    for d in kokoelma.dokumentit:
        teksti = d["teksti"]
        pieni = teksti.lower()
        maara = pieni.count(kk) + d["otsikko"].lower().count(kk)
        if not maara:
            continue
        i = pieni.find(kk)
        ote = " ".join(teksti[max(0, i - 80): i + len(k) + 80].split()) if i >= 0 else d["otsikko"]
        osumat.append({"tunniste": d["tunniste"], "otsikko": d["otsikko"], "ryhma": d["ryhma"], "osumia": maara,
                       "ote": ote})
    osumat.sort(key=lambda o: -o["osumia"])
    return osumat[:OSUMIA_MAX]
