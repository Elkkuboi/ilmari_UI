"""Peruskirjan (aiops docs/saannot.md) lukija ja rajattu Markdown-jäsennin sääntöpaneelille.

aiops ADR-0013, tarkennus 2026-10-20, ja ADR-0017. aiopsin deploy.sh julkaisee asennetun commitin peruskirjan
hakemistoon /srv/aiops/ilmari/peruskirja kahtena tiedostona: saannot.md ja meta.json (muoto aiops-peruskirja-v1).

Luku:
  - Hakemisto avataan samalla polkukävelyllä kuin ajot (RunReader: dir_fd, O_NOFOLLOW, vaihtokilpailun tunnistus).
  - Vain kaksi nimeä, tavalliset tiedostot, yksi linkki, kokorajat ja muuttumattomuus luvun aikana.
  - Tuotannossa hakemiston ja tiedostojen omistajan on oltava root (uid 0): vain deploy kirjoittaa, eikä eliaksena
    ajettava yöajo voi vaihtaa sääntöpaneelin sisältöä.
  - saannot.md:n SHA-256 on oltava meta.json:n sha256 ja koko sen koko. Muuten julkaisu on kesken tai ristiriitainen,
    eikä mitään näytetä.

Jäsennin tuottaa tietorakenteen (otsikot, kappaleet, listat, taulukot, koodi, lainaukset, vaakaviiva ja
tekstinsisäinen lihavointi ja koodi). Se ei tuota HTML:ää: sivupohja koodaa jokaisen tekstin, joten mikään peruskirjan
merkki ei voi muuttua merkinnäksi. Linkit näytetään tekstinä sellaisinaan.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .runs import ReadFailure, RunReader, _fail_os, _parse_json, _snapshot

SAANNOT = "saannot.md"
META = "meta.json"
RAJAT = {SAANNOT: 64 * 1024, META: 4 * 1024}  # saannot.md: sama raja kuin aiopsin julkaisijassa
MUOTO = "aiops-peruskirja-v1"
META_KENTAT = frozenset({"muoto", "lahde", "commit", "sha256", "koko", "julkaistu"})
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY
LOHKORAJA = 4000
SARAKERAJA = 12


@dataclass(frozen=True)
class Peruskirja:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    meta: dict[str, Any] | None = None
    lohkot: tuple[dict[str, Any], ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------------------------------
# Luku
# --------------------------------------------------------------------------------------------------

def _lue(hd: int, nimi: str, omistaja: int | None, deadline: float, raja: int | None = None) -> bytes:
    raja = RAJAT[nimi] if raja is None else raja  # raja: dokumenttien lukija (aiops istunto 2)
    fd: int | None = None
    try:
        ennen = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
        if not stat.S_ISREG(ennen.st_mode) or ennen.st_nlink != 1:
            raise ReadFailure("unsafe_file", "Julkaisun tiedostotyyppi tai linkitys ei ole sallittu.")
        if omistaja is not None and ennen.st_uid != omistaja:
            raise ReadFailure("wrong_owner", "Peruskirjan tiedostoa ei ole julkaissut asennus (omistaja ei ole root).")
        if ennen.st_size > raja:
            raise ReadFailure("too_large", "Julkaistu tiedosto ylittää lukurajan.")
        fd = os.open(nimi, _FILE_FLAGS, dir_fd=hd)
        avattu = os.fstat(fd)
        if _snapshot(ennen) != _snapshot(avattu):
            raise ReadFailure("changed", "Julkaistu tiedosto muuttui lukemisen aikana.")
        sisalto = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise ReadFailure("timeout", "Julkaisun lukuaikaraja ylittyi.")
            pala = os.read(fd, min(64 * 1024, raja + 1 - len(sisalto)))
            if not pala:
                break
            sisalto.extend(pala)
            if len(sisalto) > raja:
                raise ReadFailure("too_large", "Julkaistu tiedosto ylittää lukurajan.")
        jalkeen = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
        if _snapshot(avattu) != _snapshot(os.fstat(fd)) or _snapshot(avattu) != _snapshot(jalkeen):
            raise ReadFailure("changed", "Julkaistu tiedosto muuttui lukemisen aikana.")
        return bytes(sisalto)
    except OSError as error:
        raise _fail_os(error) from None
    finally:
        if fd is not None:
            os.close(fd)


def _teksti(data: bytes) -> str:
    try:
        teksti = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ReadFailure("invalid_text", "Peruskirja ei ole UTF-8-muodossa.") from None
    for c in teksti:
        o = ord(c)
        if (o < 32 and c not in "\n\r\t") or 0x202A <= o <= 0x202E or 0x2066 <= o <= 0x2069:
            raise ReadFailure("invalid_text", "Peruskirja sisältää kielletyn merkin.")
    return teksti


def _tarkista_meta(meta: dict[str, Any], data: bytes) -> None:
    if set(meta) != META_KENTAT:
        raise ReadFailure("invalid_meta", "Peruskirjan meta.json:n kentät eivät vastaa muotoa.")
    if meta["muoto"] != MUOTO or meta["lahde"] != "docs/saannot.md":
        raise ReadFailure("invalid_meta", "Peruskirjan meta.json on tuntematonta muotoa.")
    if type(meta["commit"]) is not str or _COMMIT.fullmatch(meta["commit"]) is None:
        raise ReadFailure("invalid_meta", "Peruskirjan commit ei ole täysi tiiviste.")
    if type(meta["sha256"]) is not str or _SHA256.fullmatch(meta["sha256"]) is None:
        raise ReadFailure("invalid_meta", "Peruskirjan tiiviste ei ole SHA-256.")
    if type(meta["koko"]) is not int:
        raise ReadFailure("invalid_meta", "Peruskirjan koko ei ole kokonaisluku.")
    try:
        aika = datetime.fromisoformat(meta["julkaistu"]) if type(meta["julkaistu"]) is str else None
    except ValueError:
        aika = None
    if aika is None or aika.tzinfo is None:
        raise ReadFailure("invalid_meta", "Peruskirjan julkaisuaika ei ole aikavyöhykkeellinen ISO-aika.")
    if meta["koko"] != len(data) or meta["sha256"] != hashlib.sha256(data).hexdigest():
        raise ReadFailure("mismatch", "Peruskirjan julkaisu on kesken tai ristiriitainen (tiiviste ei täsmää).")


def lue_peruskirja(root: str | Path, *, omistaja: int | None = 0, timeout_seconds: float = 1.0) -> Peruskirja:
    """Lukee julkaistun peruskirjan. omistaja=None vain kehitys- ja esimerkkitilassa."""
    try:
        polkukavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Peruskirja("error", "Peruskirjan polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with polkukavelija._root_fd(deadline) as hd:
            if omistaja is not None and os.fstat(hd).st_uid != omistaja:
                raise ReadFailure("wrong_owner", "Peruskirjan hakemistoa ei ole luonut asennus (omistaja ei ole root).")
            data = _lue(hd, SAANNOT, omistaja, deadline)
            meta_teksti = _teksti(_lue(hd, META, omistaja, deadline))
        meta = _parse_json(meta_teksti, object_only=True)
        assert isinstance(meta, dict)
        _tarkista_meta(meta, data)
        return Peruskirja("ready", None, meta, jasenna(_teksti(data)))
    except ReadFailure as error:
        if error.code == "not_found":
            return Peruskirja("not_published", "Peruskirjaa ei ole julkaistu. aiopsin asennus (deploy.sh) julkaisee sen.")
        return Peruskirja("error", error.message)


# --------------------------------------------------------------------------------------------------
# Rajattu Markdown
# --------------------------------------------------------------------------------------------------

_OTSIKKO = re.compile(r"(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*\Z")
_VIIVA = re.compile(r"(?:-[ \t]*){3,}\Z|(?:\*[ \t]*){3,}\Z|(?:_[ \t]*){3,}\Z")
_LUETTELO = re.compile(r"([ \t]*)([-*+])[ \t]+(.*)\Z")
_NUMERO = re.compile(r"([ \t]*)([0-9]{1,9})[.)][ \t]+(.*)\Z")
_EROTIN = re.compile(r"\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*\Z")


def osat(teksti: str) -> tuple[tuple[str, str], ...]:
    """Tekstinsisäiset osat: ("teksti"|"lihava"|"koodi", merkkijono). Pariton merkki jää tekstiksi."""
    tulos: list[tuple[str, str]] = []
    puskuri: list[str] = []
    i = 0

    def tyhjenna() -> None:
        if puskuri:
            tulos.append(("teksti", "".join(puskuri)))
            puskuri.clear()

    while i < len(teksti):
        if teksti[i] == "`":
            j = teksti.find("`", i + 1)
            if j > i + 1:
                tyhjenna()
                tulos.append(("koodi", teksti[i + 1:j]))
                i = j + 1
                continue
        if teksti.startswith("**", i):
            j = teksti.find("**", i + 2)
            if j > i + 2:
                tyhjenna()
                tulos.append(("lihava", teksti[i + 2:j]))
                i = j + 2
                continue
        puskuri.append(teksti[i])
        i += 1
    tyhjenna()
    return tuple(tulos)


def _solut(rivi: str) -> list[str]:
    rivi = rivi.strip()
    if rivi.startswith("|"):
        rivi = rivi[1:]
    if rivi.endswith("|"):
        rivi = rivi[:-1]
    return [solu.strip() for solu in rivi.split("|")][:SARAKERAJA]


def _sisennys(alku: str) -> int:
    return 1 if len(alku.expandtabs(4)) >= 2 else 0


def jasenna(teksti: str) -> tuple[dict[str, Any], ...]:
    rivit = teksti.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lohkot: list[dict[str, Any]] = []
    kappale: list[str] = []
    i, n = 0, len(rivit)

    def lisaa(lohko: dict[str, Any]) -> None:
        if len(lohkot) >= LOHKORAJA:
            raise ReadFailure("too_large", "Peruskirjassa on liikaa lohkoja.")
        lohkot.append(lohko)

    def tyhjenna() -> None:
        if kappale:
            lisaa({"tyyppi": "kappale", "osat": osat(" ".join(kappale))})
            kappale.clear()

    while i < n:
        rivi = rivit[i]
        riisuttu = rivi.strip()
        if riisuttu.startswith("```"):
            tyhjenna()
            koodi: list[str] = []
            i += 1
            while i < n and not rivit[i].strip().startswith("```"):
                koodi.append(rivit[i])
                i += 1
            i += 1  # sulkeva aita (tai tiedoston loppu)
            lisaa({"tyyppi": "koodi", "teksti": "\n".join(koodi)})
            continue
        if not riisuttu:
            tyhjenna()
            i += 1
            continue
        otsikko = _OTSIKKO.fullmatch(riisuttu) if not rivi[:1].isspace() else None
        if otsikko:
            tyhjenna()
            lisaa({"tyyppi": "otsikko", "taso": len(otsikko.group(1)), "osat": osat(otsikko.group(2))})
            i += 1
            continue
        if _VIIVA.fullmatch(riisuttu):
            tyhjenna()
            lisaa({"tyyppi": "viiva"})
            i += 1
            continue
        if riisuttu.startswith("|") and i + 1 < n and _EROTIN.fullmatch(rivit[i + 1].strip()):
            tyhjenna()
            otsikot = _solut(riisuttu)
            leveys = len(otsikot)
            i += 2
            taulu: list[tuple] = []
            while i < n and rivit[i].strip().startswith("|"):
                solut = (_solut(rivit[i]) + [""] * leveys)[:leveys]
                taulu.append(tuple(osat(s) for s in solut))
                i += 1
            lisaa({"tyyppi": "taulukko", "otsikot": tuple(osat(s) for s in otsikot), "rivit": tuple(taulu)})
            continue
        if riisuttu.startswith(">"):
            tyhjenna()
            lainaus: list[str] = []
            while i < n and rivit[i].strip().startswith(">"):
                lainaus.append(rivit[i].strip()[1:].strip())
                i += 1
            lisaa({"tyyppi": "lainaus", "osat": osat(" ".join(lainaus))})
            continue
        luettelo, numero = _LUETTELO.fullmatch(rivi), _NUMERO.fullmatch(rivi)
        # Lista voi keskeyttää kappaleen; numeroitu vain numerolla 1 (muuten "2026. vuonna" olisi lista).
        if luettelo or (numero and (not kappale or numero.group(2) == "1")):
            tyhjenna()
            jarjestetty = luettelo is None
            sama, muu = (_NUMERO, _LUETTELO) if jarjestetty else (_LUETTELO, _NUMERO)
            alku = int(numero.group(2)) if jarjestetty else 1
            kohdat: list[dict[str, Any]] = []
            nykyinen: list[str] = []
            sisennys = 0
            while i < n:
                r = rivit[i]
                if not r.strip():
                    seuraava = sama.fullmatch(rivit[i + 1]) if i + 1 < n else None
                    if seuraava and not seuraava.group(1):  # tyhjä rivi saman listan kohtien välissä
                        i += 1
                        continue
                    break
                m_sama, m_muu = sama.fullmatch(r), muu.fullmatch(r)
                if m_sama or (m_muu and m_muu.group(1)):
                    m = m_sama or m_muu
                    if nykyinen:
                        kohdat.append({"osat": osat(" ".join(nykyinen)), "sisennys": sisennys})
                        nykyinen = []
                    sisennys = _sisennys(m.group(1))
                    nykyinen.append(m.group(3).strip())
                elif m_muu:
                    break  # toisenlainen lista alkaa
                elif r[:1].isspace():
                    nykyinen.append(r.strip())  # kohdan jatkorivi
                elif _OTSIKKO.fullmatch(r.strip()) or _VIIVA.fullmatch(r.strip()) or r.strip().startswith(("|", ">", "```")):
                    break
                else:
                    nykyinen.append(r.strip())  # laiska jatkorivi
                i += 1
            if nykyinen:
                kohdat.append({"osat": osat(" ".join(nykyinen)), "sisennys": sisennys})
            lisaa({"tyyppi": "lista", "jarjestetty": jarjestetty, "alku": alku, "kohdat": tuple(kohdat)})
            continue
        kappale.append(riisuttu)
        i += 1
    tyhjenna()
    return tuple(lohkot)
