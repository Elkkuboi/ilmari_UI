"""Kehitystyöt ja käyttöönotot vain luku -tilassa (aiops istunto 2, ADR-0024).

Kaksi lähdettä:

- /srv/aiops/ilmari/kehitys/<työ>/: gateway (aiops-gw) julkaisee kehitystyön tilan (meta.json), päätöksen
  (paatos.json) ja kopiot kontin tulosteista; käyttöönottopalvelu (root) kirjoittaa vastaukset yhdistys.json ja
  kayttoonotto.json. Tuotannossa kelpaavat vain rootin tai gatewayn kirjoittamat tiedostot.
- /srv/aiops/ilmari/kayttoonotot/: käyttöönoton kääre (root) julkaisee historian historia.json + meta.json
  SHA-256:lla, sama malli kuin dokumenteissa.

Hub ei kirjoita mitään eikä tee toimia: Hyväksy, Hylkää, Pyydä muutosta ja Ota käyttöön ovat gatewayn sivuja, joihin
tästä vain linkitetään (passkey gatewayssa). Tiedostot luetaan peruskirjan lukijalla (linkkejä seuraamatta, kokorajat,
aikaraja), JSON tiukasti (ei toistuvia kenttiä, ei vakioita) ja tekstit näytetään vain ilman ohjausmerkkejä.
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

from .dokumentit import _json, _kelpaa
from .peruskirja import _COMMIT, ReadFailure, RunReader, _lue

OLETUS = Path("/srv/aiops/ilmari/kehitys")
OLETUS_KAYTTOONOTOT = Path("/srv/aiops/ilmari/kayttoonotot")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "kehitys"
ESIMERKKI_KAYTTOONOTOT = Path(__file__).resolve().parent / "demo" / "kayttoonotot"
GATEWAY_KAYTTAJA = "aiops-gw"
TOITA_MAX = 50
RAJAT = {"meta.json": 256 * 1024, "paatos.json": 16 * 1024, "yhdistys.json": 16 * 1024, "kayttoonotto.json": 16 * 1024,
         "muutos.diff": 1024 * 1024 + 256, "muutos-stat.txt": 64 * 1024 + 256, "vastaus.md": 64 * 1024 + 256,
         "testit.txt": 256 * 1024 + 256, "aiops-dsh.log": 64 * 1024 + 256, "dsh-stderr.log": 256 * 1024 + 256}
TEKSTIT = ("muutos.diff", "muutos-stat.txt", "vastaus.md", "testit.txt", "aiops-dsh.log", "dsh-stderr.log")
TILAT = {"queued": "jonossa", "awaiting_approval": "odottaa hyväksyntää", "awaiting_gpu": "odottaa GPU:ta",
         "running": "käynnissä", "succeeded": "valmis", "failed": "epäonnistui", "cancelled": "peruttu"}
PAATOKSET = {"hylatty": "Hylätty", "hyvaksytty": "Hyväksytty"}
YHDISTYKSET = {"yhdistetty": "Yhdistetty mainiin", "ristiriita": "Ristiriita mainin kanssa", "hylatty": "Yhdistys hylätty",
               "virhe": "Yhdistys epäonnistui"}
KAYTTOONOTOT = {"asennettu": "Otettu käyttöön", "ei_mainissa": "Ei GitHubin mainissa",
                "vanhempi_kuin_asennettu": "Vanhempi kuin asennettu, ei alennettu",
                "testit_epaonnistuivat": "Testit epäonnistuivat", "tyot_kaynnissa": "Töitä käynnissä, yritä myöhemmin",
                "palautettu": "Palautettu edelliseen", "palautus_epaonnistui": "Palautus epäonnistui", "virhe": "Virhe",
                "hylatty": "Pyyntö hylätty"}
MUOTO_KAYTTOONOTOT = "aiops-kayttoonotot-v1"
META_KENTAT = frozenset({"muoto", "commit", "sha256", "koko", "maara", "julkaistu"})
HISTORIA_KENTAT = frozenset({"muoto", "commit", "kayttoonotot"})
KIRJAUS_KENTAT = frozenset({"aika", "kesto_s", "commit", "edellinen", "tulos", "vaihe", "viesti", "testit", "loki"})
RAJA_HISTORIA = 2 * 1024 * 1024
RAJA_META = 4 * 1024
_TYO = re.compile(r"[1-9][0-9]{0,17}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VIESTIT = {
    "wrong_owner": "Julkaisua ei ole tehnyt gateway tai asennus (väärä omistaja).",
    "too_large": "Julkaisu ylittää lukurajan.",
    "changed": "Julkaisu muuttui lukemisen aikana. Yritä uudelleen.",
    "unsafe_file": "Julkaisun tiedostotyyppi tai linkitys ei ole sallittu.",
    "timeout": "Lukuaikaraja ylittyi.",
}


@dataclass(frozen=True)
class Kehitystyo:
    tyo: int
    meta: dict[str, Any]
    paatos: dict[str, Any] | None = None
    yhdistys: dict[str, Any] | None = None
    kayttoonotto: dict[str, Any] | None = None
    tekstit: dict[str, str] = field(default_factory=dict)
    virheet: tuple[str, ...] = ()

    @property
    def vaihe(self) -> tuple[str, str]:
        """(teksti, sävy): yksi rivi, joka kertoo, missä työ on menossa."""
        if self.kayttoonotto is not None:
            t = self.kayttoonotto.get("tulos", "virhe")
            return KAYTTOONOTOT.get(t, "Käyttöönotto: " + str(t)), "success" if t == "asennettu" else "danger"
        if self.paatos is not None and self.paatos.get("kayttoonotto_pyynto"):
            return "Käyttöönotto pyydetty", "accent"
        if self.yhdistys is not None:
            t = self.yhdistys.get("tila", "virhe")
            return YHDISTYKSET.get(t, "Yhdistys: " + str(t)), "success" if t == "yhdistetty" else "danger"
        if self.paatos is not None:
            p = self.paatos.get("paatos", "")
            return ("Hyväksytty, odottaa yhdistystä", "accent") if p == "hyvaksytty" else ("Hylätty", "warning")
        tila = str(self.meta.get("tila", ""))
        if tila == "succeeded":
            testit = (self.meta.get("tulos") or {}).get("testit")
            if isinstance(testit, dict) and testit.get("paluukoodi") not in (0, None):
                return "Valmis, testit epäonnistuivat", "warning"
            return "Valmis, odottaa päätöstä", "accent"
        if tila in ("failed", "cancelled"):
            return TILAT[tila].capitalize(), "danger"
        return TILAT.get(tila, tila or "tuntematon").capitalize(), "muted"


@dataclass(frozen=True)
class Kayttoonotot:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    meta: dict[str, Any] | None = None
    kirjaukset: tuple[dict[str, Any], ...] = ()


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def sallitut_omistajat() -> frozenset[int] | None:
    """Tuotanto: root ja gateway. None = ei tarkistusta (kehitys ja esimerkkitila)."""
    import pwd
    omistajat = {0}
    try:
        omistajat.add(pwd.getpwnam(GATEWAY_KAYTTAJA).pw_uid)
    except KeyError:
        pass
    return frozenset(omistajat)


def _teksti(data: bytes, raja: int) -> str:
    teksti = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    puhdas = "".join(c for c in teksti if c in "\n\t" or (ord(c) >= 32 and ord(c) != 0x7F and not 0x80 <= ord(c) <= 0x9F
                                                           and not 0x202A <= ord(c) <= 0x202E
                                                           and not 0x2066 <= ord(c) <= 0x2069))
    return puhdas[:raja]


def _siisti(arvo: Any, raja: int = 2000, rivinvaihdot: bool = False) -> str:
    """Näytettävä merkkijono: vain merkkijonot kelpaavat, ohjausmerkit pois, pituus rajattu."""
    if type(arvo) is not str:
        return ""
    puhdas = "".join(c for c in arvo.replace("\r\n", "\n") if _kelpaa(c, rivinvaihdot))
    return puhdas[:raja]


def _kokonaisluku(arvo: Any) -> int | None:
    return arvo if type(arvo) is int and -(2**53) < arvo < 2**53 else None


def _siivoa_meta(tyo: int, meta: Any) -> dict[str, Any]:
    """Gatewayn meta.json tunnettuina, tyypitettyinä kenttinä. Ylimääräiset kentät jätetään pois."""
    if not isinstance(meta, dict) or _kokonaisluku(meta.get("tyo")) != tyo:
        _virhe("meta.json ei kuulu tälle työlle.")
    tila = _siisti(meta.get("tila"), 40)
    if tila not in TILAT:
        _virhe("meta.json:n tila on tuntematon.")
    tulos_raaka = meta.get("tulos") if isinstance(meta.get("tulos"), dict) else {}
    testit_raaka = tulos_raaka.get("testit") if isinstance(tulos_raaka.get("testit"), dict) else None
    tulos = {
        "paluukoodi": _kokonaisluku(tulos_raaka.get("paluukoodi")),
        "haara": _siisti(tulos_raaka.get("haara"), 120),
        "perus": _siisti(tulos_raaka.get("perus"), 64), "paa": _siisti(tulos_raaka.get("paa"), 64),
        "commiteja": _kokonaisluku(tulos_raaka.get("commiteja")),
        "tiedostot": [_siisti(t, 300) for t in tulos_raaka.get("tiedostot", [])[:200]
                      if type(t) is str] if isinstance(tulos_raaka.get("tiedostot"), list) else [],
        "muutokset": _siisti(tulos_raaka.get("muutokset"), 300),
        "vastaus": _siisti(tulos_raaka.get("vastaus"), 8000, rivinvaihdot=True),
        "virhe": _siisti(tulos_raaka.get("virhe"), 500),
        "testit": None if testit_raaka is None else {"paluukoodi": _kokonaisluku(testit_raaka.get("paluukoodi")),
                                                     "yhteenveto": _siisti(testit_raaka.get("yhteenveto"), 300)},
    }
    return {
        "tyo": tyo, "toive": _siisti(meta.get("toive"), 4000, rivinvaihdot=True), "jatka": _kokonaisluku(meta.get("jatka")),
        "luotu": _siisti(meta.get("luotu"), 40), "paivitetty": _siisti(meta.get("paivitetty"), 40),
        "jattaja": _siisti(meta.get("jattaja"), 40), "tila": tila, "tila_teksti": TILAT[tila],
        "syy": _siisti(meta.get("syy"), 500), "kesto": _siisti(meta.get("kesto"), 60), "valmis": meta.get("valmis") is True,
        "tulos": tulos if tulos_raaka else None,
        "tiedostot": [t for t in meta.get("tiedostot", []) if type(t) is str and t in TEKSTIT]
        if isinstance(meta.get("tiedostot"), list) else [],
    }


def _siivoa_paatos(paatos: Any) -> dict[str, Any] | None:
    if not isinstance(paatos, dict):
        return None
    p = _siisti(paatos.get("paatos"), 20)
    if p not in PAATOKSET:
        return None
    return {"paatos": p, "teksti": PAATOKSET[p], "aika": _siisti(paatos.get("aika"), 40),
            "kuka": _siisti(paatos.get("kuka"), 40), "commit": _siisti(paatos.get("commit"), 64),
            "kayttoonotto_pyynto": _siisti(paatos.get("kayttoonotto_pyynto"), 120),
            "kayttoonotto_commit": _siisti(paatos.get("kayttoonotto_commit"), 64),
            "kayttoonotto_aika": _siisti(paatos.get("kayttoonotto_aika"), 40)}


def _siivoa_vastaus(vastaus: Any, tilat: dict[str, str], avain: str) -> dict[str, Any] | None:
    if not isinstance(vastaus, dict):
        return None
    t = _siisti(vastaus.get(avain), 40)
    if t not in tilat:
        return None
    return {avain: t, "teksti": tilat[t], "commit": _siisti(vastaus.get("commit"), 64),
            "viesti": _siisti(vastaus.get("viesti"), 600), "aika": _siisti(vastaus.get("aika"), 40),
            "paluukoodi": _kokonaisluku(vastaus.get("paluukoodi"))}


def _lue_json(hd: int, nimi: str, omistajat: frozenset[int] | None, deadline: float) -> Any | None:
    """Puuttuva tiedosto on None; muu ongelma on ReadFailure."""
    try:
        return _json(_lue(hd, nimi, None, deadline, RAJAT[nimi]) if omistajat is None else _lue_omistajista(hd, nimi, omistajat, deadline))
    except ReadFailure as error:
        if error.code == "not_found":
            return None
        raise


def _lue_omistajista(hd: int, nimi: str, omistajat: frozenset[int], deadline: float) -> bytes:
    try:
        tiedot = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
    except OSError as error:
        raise ReadFailure("not_found" if error.errno == 2 else "unsafe_file", VIESTIT["unsafe_file"]) from None
    if tiedot.st_uid not in omistajat:
        raise ReadFailure("wrong_owner", VIESTIT["wrong_owner"])
    return _lue(hd, nimi, tiedot.st_uid, deadline, RAJAT[nimi])


def lue_kehitystyo(root: str | Path, tyo: int, *, omistajat: frozenset[int] | None = None,
                   timeout_seconds: float = 2.0, tekstit: bool = True) -> Kehitystyo | None:
    """Yksi kehitystyö tai None, jos sitä ei ole. Rikkinäinen tiedosto näkyy virheenä, ei kaada sivua."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return None
    deadline = time.monotonic() + timeout_seconds
    virheet: list[str] = []
    try:
        with kavelija._root_fd(deadline) as juuri_fd:
            if omistajat is not None and os.fstat(juuri_fd).st_uid not in omistajat:
                return None
            with kavelija._run_fd(juuri_fd, str(tyo)) as hd:
                meta = _siivoa_meta(tyo, _lue_json(hd, "meta.json", omistajat, deadline))
                osat: dict[str, Any] = {}
                for nimi, siivoa in (("paatos.json", _siivoa_paatos),
                                     ("yhdistys.json", lambda v: _siivoa_vastaus(v, YHDISTYKSET, "tila")),
                                     ("kayttoonotto.json", lambda v: _siivoa_vastaus(v, KAYTTOONOTOT, "tulos"))):
                    try:
                        osat[nimi] = siivoa(_lue_json(hd, nimi, omistajat, deadline))
                    except ReadFailure as error:
                        virheet.append(f"{nimi}: {VIESTIT.get(error.code, error.message)}")
                        osat[nimi] = None
                tekstit_luettu: dict[str, str] = {}
                if tekstit:
                    for nimi in meta["tiedostot"]:
                        try:
                            raaka = (_lue(hd, nimi, None, deadline, RAJAT[nimi]) if omistajat is None
                                     else _lue_omistajista(hd, nimi, omistajat, deadline))
                            tekstit_luettu[nimi] = _teksti(raaka, RAJAT[nimi])
                        except ReadFailure as error:
                            virheet.append(f"{nimi}: {VIESTIT.get(error.code, error.message)}")
    except ReadFailure as error:
        if error.code == "not_found":
            return None
        return Kehitystyo(tyo, {"tyo": tyo, "toive": "", "tila": "failed", "tila_teksti": "ei luettavissa", "syy": "",
                                "tulos": None, "tiedostot": [], "jatka": None, "luotu": "", "paivitetty": "",
                                "jattaja": "", "kesto": "", "valmis": False},
                          virheet=(f"meta.json: {VIESTIT.get(error.code, error.message)}",))
    return Kehitystyo(tyo, meta, osat["paatos.json"], osat["yhdistys.json"], osat["kayttoonotto.json"], tekstit_luettu,
                      tuple(virheet))


def lue_kehitystyot(root: str | Path, *, omistajat: frozenset[int] | None = None,
                    timeout_seconds: float = 2.0) -> tuple[Kehitystyo, ...] | None:
    """Kehitystyöt uusin ensin (enintään TOITA_MAX) tai None, jos hakemistoa ei ole."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return None
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as juuri_fd:
            if omistajat is not None and os.fstat(juuri_fd).st_uid not in omistajat:
                return None
            nimet = os.listdir(juuri_fd)
    except (ReadFailure, OSError):
        return None
    numerot = sorted((int(n) for n in nimet if _TYO.fullmatch(n)), reverse=True)[:TOITA_MAX]
    tyot = []
    for tyo in numerot:
        t = lue_kehitystyo(root, tyo, omistajat=omistajat, timeout_seconds=max(0.2, deadline - time.monotonic()),
                           tekstit=False)
        if t is not None:
            tyot.append(t)
    return tuple(tyot)


def _tarkista_historia(meta: Any, data: bytes) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not isinstance(meta, dict) or set(meta) != META_KENTAT or meta["muoto"] != MUOTO_KAYTTOONOTOT:
        _virhe("meta.json:n kentät eivät vastaa muotoa.")
    if type(meta["commit"]) is not str or (meta["commit"] and _COMMIT.fullmatch(meta["commit"]) is None):
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
    sisalto = _json(data)
    if not isinstance(sisalto, dict) or set(sisalto) != HISTORIA_KENTAT or sisalto["muoto"] != MUOTO_KAYTTOONOTOT:
        _virhe("historia.json:n kentät eivät vastaa muotoa.")
    lista = sisalto["kayttoonotot"]
    if type(lista) is not list or len(lista) != meta["maara"] or len(lista) > 100:
        _virhe("Käyttöönottojen määrä ei vastaa julkaisua.")
    kirjaukset = []
    for k in lista:
        if type(k) is not dict or set(k) != KIRJAUS_KENTAT:
            _virhe("Kirjauksen kentät eivät vastaa muotoa.")
        if type(k["kesto_s"]) is not int or k["tulos"] not in KAYTTOONOTOT or type(k["commit"]) is not str:
            _virhe("Kirjauksen kenttä on väärää tyyppiä.")
        if _COMMIT.fullmatch(k["commit"]) is None or any(type(k[a]) is not str for a in ("aika", "edellinen", "vaihe", "viesti", "testit", "loki")):
            _virhe("Kirjauksen kenttä on väärää tyyppiä.")
        if not all(_kelpaa(k[a], False) for a in ("aika", "edellinen", "vaihe", "viesti", "testit")) or not _kelpaa(k["loki"], True):
            _virhe("Kirjaus sisältää kielletyn merkin.")
        kirjaukset.append({**k, "tulos_teksti": KAYTTOONOTOT[k["tulos"]], "loki": k["loki"][:16 * 1024],
                           "viesti": k["viesti"][:1000], "testit": k["testit"][:1000]})
    return meta, tuple(kirjaukset)


def lue_kayttoonotot(root: str | Path, *, omistaja: int | None = 0, timeout_seconds: float = 2.0) -> Kayttoonotot:
    """Käyttöönottojen historia (kääre julkaisee rootina). omistaja=None vain kehitys- ja esimerkkitilassa."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Kayttoonotot("error", "Käyttöönottojen polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    try:
        with kavelija._root_fd(deadline) as hd:
            if omistaja is not None and os.fstat(hd).st_uid != omistaja:
                raise ReadFailure("wrong_owner", VIESTIT["wrong_owner"])
            data = _lue(hd, "historia.json", omistaja, deadline, RAJA_HISTORIA)
            meta_raaka = _lue(hd, "meta.json", omistaja, deadline, RAJA_META)
        meta, kirjaukset = _tarkista_historia(_json(meta_raaka), data)
        return Kayttoonotot("ready", None, meta, kirjaukset)
    except ReadFailure as error:
        if error.code == "not_found":
            return Kayttoonotot("not_published", "Käyttöönottoja ei ole vielä tehty sovelluksesta.")
        return Kayttoonotot("error", VIESTIT.get(error.code, error.message))
