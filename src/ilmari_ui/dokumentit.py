"""Dokumentit vain luku -tilassa (aiops istunto 2, 28.10.2026).

aiopsin asennus (scripts/julkaise_dokumentit.py, ajetaan deploy.sh:sta) julkaisee asennetun commitin dokumentit
hakemistoon /srv/aiops/ilmari/dokumentit kahtena tiedostona: dokumentit.json ja meta.json (muoto aiops-dokumentit-v1).
Lukija käyttää yhteistä turvallista lukijaa (lukija.py): hakemisto ja tiedostot ovat rootin, tiedostot luetaan
linkkejä seuraamatta ja aikarajan sisällä, ja dokumentit näytetään vain, jos dokumentit.json:n SHA-256 ja koko ovat
meta.json:n arvot. Jokaisen dokumentin kentät ja teksti tarkistetaan uudelleen. Teksti piirretään rajatulla
Markdownilla (jasenna, tämän tiedoston lopussa), joka tuottaa tietorakenteen eikä HTML:ää: sivupohja koodaa jokaisen
tekstin, joten mikään dokumentin merkki ei voi muuttua merkinnäksi. Linkit näytetään tekstinä sellaisinaan.
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

from .lukija import _COMMIT, Hakemisto, ReadFailure, _lue

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
RYHMAT = (("perus", "Perusdokumentit"), ("promptit", "Ilmarin promptit"), ("adr", "Päätökset"),
          ("valmistelu", "Valmistelu"), ("historia", "Historia"), ("audit", "Auditointi"))
MAARA_MAX = 300
TEKSTI_MAX = 256 * 1024
LOHKORAJA = 4000
SARAKERAJA = 12
HAKU_MAX = 100
OSUMIA_MAX = 50
_TUNNISTE = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")
# docs/ ja repon juuren AGENTS.md (tekoälyavustajien ohjeet, 21.11.2026). src/aiops/: vanha julkaisu vei sinne
# Ilmarin masterpromptin (ryhmä promptit); se hylättiin tässä, jolloin koko Dokumentit-sivu jäi tyhjäksi.
_POLKU = re.compile(r"(?:(?:docs|src/aiops)/[A-Za-z0-9._/-]{1,200}|AGENTS)\.md\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VIESTIT = {
    "wrong_owner": "Dokumentit eivät ole asennuksen tekemiä (omistaja ei ole root).",
    "too_large": "Dokumentit ylittävät lukurajan.",
    "changed": "Dokumentit muuttuivat lukemisen aikana. Yritä uudelleen.",
    "unsafe_file": "Tiedostotyyppi tai linkitys ei ole sallittu.",
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
            _virhe("JSON-objektissa on sama kenttä kahdesti.")
        tulos[avain] = arvo
    return tulos


def _ei_vakioita(_arvo: str) -> None:
    _virhe("JSON sisältää kielletyn vakion.")


def _json(raaka: bytes) -> Any:
    try:
        teksti = raaka.decode("utf-8")
    except UnicodeDecodeError:
        _virhe("Tiedosto ei ole UTF-8-muodossa.")
    try:
        return json.loads(teksti, object_pairs_hook=_ei_toistoja, parse_constant=_ei_vakioita)
    except ReadFailure:
        raise
    except ValueError:
        _virhe("Tiedosto ei ole kelvollista JSONia.")


def _tarkista_meta(meta: Any, data: bytes) -> None:
    if not isinstance(meta, dict) or set(meta) != META_KENTAT:
        _virhe("meta.json:n kentät eivät vastaa muotoa.")
    if meta["muoto"] != MUOTO:
        _virhe("meta.json on tuntematonta muotoa.")
    if type(meta["commit"]) is not str or _COMMIT.fullmatch(meta["commit"]) is None:
        _virhe("Commit ei ole täysi tiiviste.")
    if type(meta["sha256"]) is not str or _SHA256.fullmatch(meta["sha256"]) is None:
        _virhe("Tiiviste ei ole SHA-256.")
    if type(meta["koko"]) is not int or type(meta["maara"]) is not int:
        _virhe("Koko tai määrä ei ole kokonaisluku.")
    try:
        aika = datetime.fromisoformat(meta["julkaistu"]) if type(meta["julkaistu"]) is str else None
    except ValueError:
        aika = None
    if aika is None or aika.tzinfo is None:
        _virhe("Aika ei ole aikavyöhykkeellinen ISO-aika.")
    if meta["koko"] != len(data) or meta["sha256"] != hashlib.sha256(data).hexdigest():
        _virhe("Tiedosto on kesken tai ristiriitainen (tiiviste ei täsmää).")


def _tarkista_sisalto(sisalto: Any, meta: dict[str, Any]) -> tuple[dict[str, str], ...]:
    if not isinstance(sisalto, dict) or set(sisalto) != DATA_KENTAT:
        _virhe("dokumentit.json:n kentät eivät vastaa muotoa.")
    if sisalto["muoto"] != MUOTO or sisalto["commit"] != meta["commit"]:
        _virhe("dokumentit.json ei vastaa meta.json:ia.")
    lista = sisalto["dokumentit"]
    if type(lista) is not list or not 0 < len(lista) <= MAARA_MAX or len(lista) != meta["maara"]:
        _virhe("Dokumenttien määrä ei vastaa meta.json:ia.")
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
    """Lukee asennetut dokumentit. omistaja=None vain kehitys- ja esimerkkitilassa."""
    try:
        kavelija = Hakemisto(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Dokumentit("error", "Dokumenttien polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija.juuri(deadline) as hd:
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
            return Dokumentit("not_published", "Dokumentteja ei ole vielä asennettu.")
        return Dokumentit("error", VIESTIT.get(error.code, error.message))


def piirrettava(dokumentti: dict[str, str]) -> tuple[tuple[dict[str, Any], ...] | None, str | None]:
    """Rajatun Markdownin lohkot (jasenna) tai virheilmoitus."""
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
            raise ReadFailure("too_large", "Dokumentissa on liikaa lohkoja.")
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
