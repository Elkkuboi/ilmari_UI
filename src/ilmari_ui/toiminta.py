"""Ilmarin toiminta Hubissa (aiops ADR-0032, Pala 1 "Ilmari toimii itse", 18.11.2026).

Gateway (aiops-gw) kirjoittaa hakemistoon /srv/aiops/ilmari/toiminta (aiops-gw:ilmari-julkaisu 2750) Ilmarin tilan:

- asetukset.json  yöajo päällä/pois ja kellonaika (Elias muuttaa Hubista, gateway tallentaa)
- tila.json       Seis-kytkin, viimeisin yöajo, käynnissä oleva vuoro ja viimeisin rajatestin tulos
- ohjeet.json     pysyvät ohjeet (Eliaksen korjaukset, jotka Ilmari tallensi)
- tavoitteet.json Eliaksen tavoitteet riveinä
- teot.jsonl      tekoloki: rivi per teko, vain lisäys; yli 2 MiB:n jälkeen vanha nimetään teot.1.jsonl:ksi

JSON-tiedostot gateway vaihtaa atomisesti (tmp + rename), joten ne luetaan peruskirjan lukijalla (linkkejä seuraamatta,
omistaja, kokoraja, muuttumattomuus luvun aikana) ja tarkoilla kenttäjoukoilla. Puuttuva tiedosto tarkoittaa
oletusarvoja kuten gatewayssa; puuttuva hakemisto on "not_published". Tekoloki kasvaa lukemisen aikana, joten siitä
luetaan vain avaushetken koon loppu (enintään HANTA tavua): myöhemmät lisäykset eivät muuta luettua osaa, mutta
katkaisu, linkitys tai tiedoston vaihto kesken luvun on virhe. Rikkinäinen tekorivi ohitetaan ja lasketaan.

Jokaisen tiedoston virhe on oma: rikkinäinen tekoloki ei piilota Seis-tilaa. Kaikki teksti on mallin tai gatewayn
kirjoittamaa dataa: se siivotaan ohjausmerkeistä ja pohja koodaa sen (ei |safe-polkua, ei Markdownia). Hub ei kirjoita
mitään; Seis, Jatka, asetukset, tavoitteet, ohjeen poisto ja rajatesti ovat gatewayn lomakereittejä (paluu=hub).
"""

from __future__ import annotations

import os
import re
import stat
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .dokumentit import _json, _kelpaa
from .peruskirja import ReadFailure, RunReader, _lue
from .runs import _FILE_FLAGS, _fail_os, _identity

OLETUS = Path("/srv/aiops/ilmari/toiminta")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "toiminta"
HELSINKI = ZoneInfo("Europe/Helsinki")
VERSIO = 1

ASETUKSET = "asetukset.json"
TILA = "tila.json"
OHJEET = "ohjeet.json"
TAVOITTEET = "tavoitteet.json"
TEOT = "teot.jsonl"
TEOT_VANHA = "teot.1.jsonl"
RAJAT = {ASETUKSET: 4 * 1024, TILA: 64 * 1024, OHJEET: 256 * 1024, TAVOITTEET: 64 * 1024}
TEOT_RAJA = 4 * 1024 * 1024        # kierrätys 2 MiB:n kohdalla; tätä suurempi = kierrätys ei toimi
HANTA = 512 * 1024                 # tekolokista luettava loppuosa (100 riviä à 2000 tavua mahtuu moneen kertaan)
TEKO_RIVI_MAX = 2000
TEKOJA_MAX = 100

ASETUKSET_KENTAT = frozenset({"versio", "yoajo"})
YOAJO_KENTAT = frozenset({"paalla", "kello"})
TILA_KENTAT = frozenset({"versio", "seis", "seis_aika", "seis_kuka", "yoajo_viimeisin", "vuoro", "rajatesti"})
VUORO_KENTAT = frozenset({"laji", "saie", "istunto", "alkoi", "paattyy"})
RAJATESTI_KENTAT = frozenset({"aika", "tyo", "lapi", "kohdat"})
KOHTA_KENTAT = frozenset({"nimi", "odotus", "lapi", "havainto"})
OHJEET_KENTAT = frozenset({"versio", "ohjeet"})
OHJE_KENTAT = frozenset({"id", "aika", "teksti"})
TAVOITTEET_KENTAT = frozenset({"versio", "aika", "rivit"})
TEKO_KENTAT = frozenset({"aika", "lahde", "laji", "mita", "miksi", "peru", "tyo", "saie"})

OLETUS_ASETUKSET = {"paalla": True, "kello": "02:00"}
VUOROT = {"yoajo": "Yöajo"}
ODOTUKSET = {"estetty": "pitää estyä", "sallittu": "pitää toimia"}
TEKIJAT = {"gateway": "Gateway", "ilmari": "Ilmari"}
OHJEITA_MAX, OHJE_MAX = 40, 400
RIVEJA_MAX, RIVI_MAX = 20, 200
KOHTIA_MAX, HAVAINTO_MAX, KOHTA_NIMI_MAX = 40, 200, 120
TEKO_TEKSTI_MAX = 1000
_KELLO = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z", re.ASCII)
VIESTIT = {
    "wrong_owner": "Julkaisua ei ole tehnyt gateway (väärä omistaja).",
    "too_large": "Tiedosto ylittää lukurajan.",
    "changed": "Tiedosto muuttui lukemisen aikana. Päivitä sivu.",
    "unsafe_file": "Tiedostotyyppi tai linkitys ei ole sallittu.",
    "timeout": "Lukuaikaraja ylittyi.",
    "forbidden": "Lukemiseen ei ole käyttöoikeutta.",
}


@dataclass(frozen=True)
class Toiminta:
    """Luettu toiminta. Osa on None, kun sen tiedostoa ei voi lukea (syy listassa virheet); puuttuva tiedosto on
    oletusarvo (kuten gatewayssa), ei None."""

    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    asetukset: dict[str, Any] | None = None
    tilanne: dict[str, Any] | None = None
    ohjeet: tuple[dict[str, Any], ...] | None = ()
    tavoitteet: dict[str, Any] | None = None
    teot: tuple[dict[str, Any], ...] | None = ()
    teot_ohitettu: int = 0
    virheet: tuple[str, ...] = field(default_factory=tuple)


class _Ohitettava(Exception):
    """Tekorivi ei kelpaa: se ohitetaan ja lasketaan, muu loki näytetään."""


def _virhe(viesti: str) -> None:
    raise ReadFailure("invalid", viesti)


def _siisti(arvo: str, raja: int, rivinvaihdot: bool = False) -> str:
    """Näytettävä teksti: ohjaus- ja suunnanohjausmerkit pois, rivinvaihto välilyönniksi (ellei sallittu)."""
    arvo = arvo.replace("\r\n", "\n")
    if not rivinvaihdot:
        arvo = arvo.replace("\n", " ")
    return "".join(c for c in arvo if _kelpaa(c, rivinvaihdot))[:raja]


def _jasenna(raaka: bytes) -> Any:
    """Tiukka JSON (ei toistuvia kenttiä eikä vakioita); liian syvä sisäkkäisyys on virhe, ei kaatuminen."""
    try:
        return _json(raaka)
    except RecursionError:
        _virhe("JSON on liian syvästi sisäkkäinen.")


def _kokonaisluku(arvo: Any, *, tyhja: bool = False) -> int | None:
    if arvo is None and tyhja:
        return None
    if type(arvo) is not int or not 0 < arvo < 2**53:
        _virhe("Tunniste ei ole positiivinen kokonaisluku.")
    return arvo


def _teksti(arvo: Any, raja: int, *, tyhja: bool = True, rivinvaihdot: bool = False) -> str:
    """Tiukka teksti: merkkijono, enintään raja merkkiä, ei ohjausmerkkejä (rivinvaihto vain sallittaessa)."""
    if type(arvo) is not str or len(arvo) > raja or (not tyhja and not arvo.strip()):
        _virhe("Tekstikenttä puuttuu tai ylittää rajan.")
    if not _kelpaa(arvo.replace("\r\n", "\n"), rivinvaihdot):
        _virhe("Tekstikentässä on kielletty merkki.")
    return arvo


def _aika(arvo: Any, *, tyhja: bool = False) -> str | None:
    """Aikavyöhykkeellinen ISO-aika merkkijonona (näytetään format_timella) tai None, jos sallittu."""
    if arvo is None and tyhja:
        return None
    if type(arvo) is not str or len(arvo) > 40:
        _virhe("Aika ei ole ISO-aika.")
    try:
        aika = datetime.fromisoformat(arvo)
    except ValueError:
        _virhe("Aika ei ole ISO-aika.")
    if aika.tzinfo is None:
        _virhe("Ajasta puuttuu aikavyöhyke.")
    return arvo


def _paiva(arvo: Any) -> str | None:
    """Viimeisimmän yöajon päivä (YYYY-MM-DD tai ISO-aika, jonka alku on päivä) tai None."""
    if arvo is None:
        return None
    if type(arvo) is not str or len(arvo) > 40 or not _kelpaa(arvo, False):
        _virhe("Yöajon päivä ei kelpaa.")
    try:
        date.fromisoformat(arvo[:10])
    except ValueError:
        _virhe("Yöajon päivä ei kelpaa.")
    return arvo


def _kentat(data: Any, kentat: frozenset[str], nimi: str) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != kentat:
        _virhe(f"{nimi}: kentät eivät vastaa muotoa.")
    if "versio" in kentat and (type(data["versio"]) is not int or data["versio"] != VERSIO):
        _virhe(f"{nimi}: tuntematon versio.")
    return data


# --- Tiedostokohtaiset tarkistukset -----------------------------------------------------------------------------------

def tarkista_asetukset(data: Any) -> dict[str, Any]:
    _kentat(data, ASETUKSET_KENTAT, ASETUKSET)
    yoajo = data["yoajo"]
    if not isinstance(yoajo, dict) or set(yoajo) != YOAJO_KENTAT or type(yoajo["paalla"]) is not bool:
        _virhe("Yöajon asetus ei vastaa muotoa.")
    if type(yoajo["kello"]) is not str or _KELLO.fullmatch(yoajo["kello"]) is None:
        _virhe("Yöajon kellonaika ei ole muotoa HH:MM.")
    return {"paalla": yoajo["paalla"], "kello": yoajo["kello"], "oletus": False}


def _vuoro(v: Any) -> dict[str, Any] | None:
    if v is None:
        return None
    _kentat(v, VUORO_KENTAT, "vuoro")
    laji = _teksti(v["laji"], 20, tyhja=False)
    return {"laji": laji, "nimi": VUOROT.get(laji, laji), "saie": _kokonaisluku(v["saie"]),
            "istunto": _kokonaisluku(v["istunto"]), "alkoi": _aika(v["alkoi"]), "paattyy": _aika(v["paattyy"])}


def _rajatesti(r: Any) -> dict[str, Any] | None:
    if r is None:
        return None
    _kentat(r, RAJATESTI_KENTAT, "rajatesti")
    if type(r["lapi"]) is not bool or type(r["kohdat"]) is not list or len(r["kohdat"]) > KOHTIA_MAX:
        _virhe("Rajatestin tulos ei vastaa muotoa.")
    kohdat = []
    for k in r["kohdat"]:
        _kentat(k, KOHTA_KENTAT, "rajatestin kohta")
        if k["odotus"] not in ODOTUKSET or type(k["lapi"]) is not bool:
            _virhe("Rajatestin kohta ei vastaa muotoa.")
        kohdat.append({"nimi": _teksti(k["nimi"], KOHTA_NIMI_MAX, tyhja=False), "odotus": k["odotus"],
                       "odotus_teksti": ODOTUKSET[k["odotus"]], "lapi": k["lapi"],
                       "havainto": _teksti(k["havainto"], HAVAINTO_MAX)})
    return {"aika": _aika(r["aika"]), "tyo": _kokonaisluku(r["tyo"]), "lapi": r["lapi"], "kohdat": kohdat,
            "hylatyt": [k for k in kohdat if not k["lapi"]]}


def tarkista_tila(data: Any) -> tuple[dict[str, Any], list[str]]:
    """tila.json: Seis-kenttien on oltava kunnossa; rikkinäinen vuoro tai rajatesti näkyy virheenä, ei piilota Seisiä."""
    _kentat(data, TILA_KENTAT, TILA)
    if type(data["seis"]) is not bool:
        _virhe("Seis-kytkin ei ole totuusarvo.")
    tilanne = {"seis": data["seis"], "seis_aika": _aika(data["seis_aika"], tyhja=True),
               "seis_kuka": None if data["seis_kuka"] is None else _teksti(data["seis_kuka"], 64),
               "yoajo_viimeisin": _paiva(data["yoajo_viimeisin"]), "vuoro": None, "vuoro_virhe": False,
               "rajatesti": None, "rajatesti_virhe": False}
    virheet = []
    for avain, tarkista, nimi in (("vuoro", _vuoro, "vuoro"), ("rajatesti", _rajatesti, "rajatesti")):
        try:
            tilanne[avain] = tarkista(data[avain])
        except ReadFailure as error:
            tilanne[avain + "_virhe"] = True
            virheet.append(f"{TILA} ({nimi}): {error.message}")
    return tilanne, virheet


def tarkista_ohjeet(data: Any) -> tuple[dict[str, Any], ...]:
    _kentat(data, OHJEET_KENTAT, OHJEET)
    if type(data["ohjeet"]) is not list or len(data["ohjeet"]) > OHJEITA_MAX:
        _virhe("Ohjelista ei kelpaa.")
    ohjeet, tunnisteet = [], set()
    for o in data["ohjeet"]:
        _kentat(o, OHJE_KENTAT, "ohje")
        tunniste = _kokonaisluku(o["id"])
        if tunniste in tunnisteet:
            _virhe("Sama ohjeen tunniste kahdesti.")
        tunnisteet.add(tunniste)
        ohjeet.append({"id": tunniste, "aika": _aika(o["aika"]),
                       "teksti": _teksti(o["teksti"], OHJE_MAX, tyhja=False, rivinvaihdot=True)})
    return tuple(ohjeet)


def tarkista_tavoitteet(data: Any) -> dict[str, Any]:
    _kentat(data, TAVOITTEET_KENTAT, TAVOITTEET)
    if type(data["rivit"]) is not list or len(data["rivit"]) > RIVEJA_MAX:
        _virhe("Tavoitelista ei kelpaa.")
    return {"aika": _aika(data["aika"]), "rivit": [_teksti(r, RIVI_MAX, tyhja=False) for r in data["rivit"]]}


def tarkista_teko(raaka: bytes) -> dict[str, Any]:
    """Yksi tekolokin rivi. lahde on gatewayn asettama: "gateway" = havaittu tosiasia, "ilmari" = mallin kirjaus."""
    if len(raaka) > TEKO_RIVI_MAX:
        raise _Ohitettava
    try:
        t = _kentat(_jasenna(raaka), TEKO_KENTAT, "teko")
        if t["lahde"] not in TEKIJAT:
            raise _Ohitettava
        tekstit = [t[k] for k in ("mita", "miksi", "peru", "laji")]
        if any(type(v) is not str for v in tekstit) or not t["mita"].strip() or not t["laji"].strip():
            raise _Ohitettava
        return {"aika": _aika(t["aika"]), "lahde": t["lahde"], "tekija": TEKIJAT[t["lahde"]],
                "laji": _siisti(t["laji"], 40), "mita": _siisti(t["mita"], TEKO_TEKSTI_MAX),
                "miksi": _siisti(t["miksi"], TEKO_TEKSTI_MAX), "peru": _siisti(t["peru"], TEKO_TEKSTI_MAX),
                "tyo": _kokonaisluku(t["tyo"], tyhja=True), "saie": _kokonaisluku(t["saie"], tyhja=True)}
    except ReadFailure:
        raise _Ohitettava from None


def tarkista_teot(data: bytes, alusta: bool) -> tuple[list[dict[str, Any]], int]:
    """Rivit vanhimmasta uusimpaan ja ohitettujen määrä. Jos luku ei alkanut tiedoston alusta, ensimmäinen pala on
    katkennut rivi; päättämätön viimeinen pala on kesken kirjoitettu rivi. Kumpaakaan ei lasketa virheeksi."""
    palat = data.split(b"\n")
    palat.pop()  # viimeisen rivinvaihdon jälkeinen osa: tyhjä tai kesken
    if not alusta and palat:
        palat.pop(0)
    teot, ohitettu = [], 0
    for raaka in palat:
        try:
            teot.append(tarkista_teko(raaka))
        except _Ohitettava:
            ohitettu += 1
    return teot, ohitettu


# --- Luku -------------------------------------------------------------------------------------------------------------

def _stat(hd: int, nimi: str, omistajat: frozenset[int] | None) -> os.stat_result | None:
    """None, jos tiedostoa ei ole; väärä omistaja on virhe."""
    try:
        tiedot = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _fail_os(error) from None
    if omistajat is not None and tiedot.st_uid not in omistajat:
        raise ReadFailure("wrong_owner", VIESTIT["wrong_owner"])
    return tiedot


def _lue_json(hd: int, nimi: str, omistajat: frozenset[int] | None, deadline: float) -> Any | None:
    """Atomisesti vaihdettu JSON-tiedosto tai None, jos sitä ei ole."""
    tiedot = _stat(hd, nimi, omistajat)
    if tiedot is None:
        return None
    try:
        return _jasenna(_lue(hd, nimi, tiedot.st_uid if omistajat is not None else None, deadline, RAJAT[nimi]))
    except ReadFailure as error:
        if error.code == "not_found":  # vaihdettiin juuri: seuraava lataus näkee uuden
            raise ReadFailure("changed", VIESTIT["changed"]) from None
        raise


def _lue_hanta(hd: int, nimi: str, omistajat: frozenset[int] | None,
               deadline: float) -> tuple[bytes, bool, tuple[int, int, int]] | None:
    """Vain lisättävän lokin loppu avaushetken koosta: (tavut, alkaako tiedoston alusta, tiedoston identiteetti) tai
    None, jos tiedostoa ei ole. Lisäys luvun aikana ei haittaa, katkaisu tai linkitys on virhe."""
    ennen = _stat(hd, nimi, omistajat)
    if ennen is None:
        return None
    if not stat.S_ISREG(ennen.st_mode) or ennen.st_nlink != 1:
        raise ReadFailure("unsafe_file", VIESTIT["unsafe_file"])
    fd: int | None = None
    try:
        fd = os.open(nimi, _FILE_FLAGS, dir_fd=hd)
        avattu = os.fstat(fd)
        if _identity(avattu) != _identity(ennen) or avattu.st_uid != ennen.st_uid or avattu.st_nlink != 1:
            raise ReadFailure("changed", VIESTIT["changed"])
        koko = avattu.st_size
        if koko > TEOT_RAJA:
            raise ReadFailure("too_large", VIESTIT["too_large"])
        alku = max(0, koko - HANTA)
        sisalto = bytearray()
        while len(sisalto) < koko - alku:
            if time.monotonic() > deadline:
                raise ReadFailure("timeout", VIESTIT["timeout"])
            pala = os.pread(fd, min(64 * 1024, koko - alku - len(sisalto)), alku + len(sisalto))
            if not pala:
                raise ReadFailure("changed", VIESTIT["changed"])  # katkaistiin kesken luvun
            sisalto.extend(pala)
        jalkeen = os.fstat(fd)
        if jalkeen.st_size < koko or jalkeen.st_nlink != 1 or _identity(jalkeen) != _identity(avattu):
            raise ReadFailure("changed", VIESTIT["changed"])
        return bytes(sisalto), alku == 0, _identity(avattu)
    except FileNotFoundError:
        raise ReadFailure("changed", VIESTIT["changed"]) from None
    except OSError as error:
        raise _fail_os(error) from None
    finally:
        if fd is not None:
            os.close(fd)


def _lue_teot(hd: int, omistajat: frozenset[int] | None, deadline: float) -> tuple[tuple[dict[str, Any], ...], int]:
    """Uusin ensin, enintään TEKOJA_MAX. Kierrätyksen jälkeen loppu haetaan vanhasta tiedostosta (eri inode)."""
    uusi = _lue_hanta(hd, TEOT, omistajat, deadline)
    teot, ohitettu = tarkista_teot(uusi[0], uusi[1]) if uusi else ([], 0)
    if len(teot) < TEKOJA_MAX:
        vanha = _lue_hanta(hd, TEOT_VANHA, omistajat, deadline)
        if vanha is not None and (uusi is None or vanha[2] != uusi[2]):
            vanhat, ohitettu_vanhat = tarkista_teot(vanha[0], vanha[1])
            teot, ohitettu = vanhat + teot, ohitettu + ohitettu_vanhat
    return tuple(reversed(teot[-TEKOJA_MAX:])), ohitettu


def lue_toiminta(root: str | Path, *, omistajat: frozenset[int] | None = None,
                 timeout_seconds: float = 2.0) -> Toiminta:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa gateway (aiops-gw) ja root."""
    try:
        kavelija = RunReader(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Toiminta("error", "Toiminnan polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    virheet: list[str] = []
    osat: dict[str, Any] = {}

    def osa(nimi: str, lue, oletus: Any) -> None:
        try:
            osat[nimi] = lue()
            if osat[nimi] is None:
                osat[nimi] = oletus
        except ReadFailure as error:
            osat[nimi] = None
            virheet.append(f"{nimi}: {VIESTIT.get(error.code, error.message)}")

    try:
        with kavelija._root_fd(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Toiminnan hakemisto ei ole gatewayn (väärä omistaja).")

            def json_osa(nimi, tarkista):
                data = _lue_json(hd, nimi, omistajat, deadline)
                return None if data is None else tarkista(data)

            def tila():
                data = _lue_json(hd, TILA, omistajat, deadline)
                if data is None:
                    return None
                tilanne, osavirheet = tarkista_tila(data)
                virheet.extend(osavirheet)
                return tilanne

            osa(ASETUKSET, lambda: json_osa(ASETUKSET, tarkista_asetukset), {**OLETUS_ASETUKSET, "oletus": True})
            osa(TILA, tila, {"seis": False, "seis_aika": None, "seis_kuka": None, "yoajo_viimeisin": None,
                             "vuoro": None, "vuoro_virhe": False, "rajatesti": None, "rajatesti_virhe": False})
            osa(OHJEET, lambda: json_osa(OHJEET, tarkista_ohjeet), ())
            osa(TAVOITTEET, lambda: json_osa(TAVOITTEET, tarkista_tavoitteet), {"aika": None, "rivit": []})
            osa(TEOT, lambda: _lue_teot(hd, omistajat, deadline), ((), 0))
    except ReadFailure as error:
        if error.code == "not_found":
            return Toiminta("not_published", "Gateway ei ole vielä julkaissut Ilmarin toimintaa.")
        return Toiminta("error", VIESTIT.get(error.code, error.message))
    except OSError as error:
        return Toiminta("error", f"Toimintaa ei voi lukea ({error.strerror}).")
    teot, ohitettu = osat[TEOT] if osat[TEOT] is not None else (None, 0)
    return Toiminta("ready", None, osat[ASETUKSET], osat[TILA], osat[OHJEET], osat[TAVOITTEET], teot, ohitettu,
                    tuple(virheet))


# --- Näyttö -----------------------------------------------------------------------------------------------------------

def kello(arvo: str | None) -> str:
    """ISO-aika Helsingin kellonaikana (04.55) tai tyhjä."""
    try:
        return datetime.fromisoformat(arvo).astimezone(HELSINKI).strftime("%H.%M") if arvo else ""
    except (ValueError, TypeError, OverflowError):
        return ""


def tilarivi(toiminta: Toiminta | None, nyt: datetime) -> dict[str, Any] | None:
    """Sivun ylin rivi: {teksti, savy, selitys, seis}. seis: True = pysäytetty, False = ei, None = ei tiedossa (silloin
    sivu näyttää sekä Seis- että Jatka-napin)."""
    if toiminta is None:
        return None
    if toiminta.tila != "ready" or toiminta.tilanne is None:
        return {"teksti": "Tila ei tiedossa", "savy": "warning", "seis": None,
                "selitys": "Ilmarin tilaa ei voi lukea. Seis toimii silti: gateway tarkistaa tilan itse."}
    t = toiminta.tilanne
    if t["seis"]:
        kuka = f" ({t['seis_kuka']})" if t["seis_kuka"] else ""
        aika = kello(t["seis_aika"])
        return {"teksti": "Seis", "savy": "danger", "seis": True,
                "selitys": (f"Pysäytetty klo {aika}{kuka}. " if aika else "Pysäytetty. ")
                + "Ilmari ei aloita töitä eikä yöajoa, ennen kuin painat Jatka. Keskustelu ilman työkaluja toimii."}
    vuoro = t["vuoro"]
    if vuoro is not None:
        paattyy = datetime.fromisoformat(vuoro["paattyy"])
        if paattyy > nyt:
            return {"teksti": f"{vuoro['nimi']} käynnissä klo {kello(vuoro['paattyy'])} asti", "savy": "accent",
                    "seis": False, "selitys": f"Ilmari tekee yön työt säikeeseen {vuoro['saie']}. Seis pysäyttää sen heti."}
        return {"teksti": f"{vuoro['nimi']}n aika ylittyi", "savy": "warning", "seis": False,
                "selitys": f"Vuoron piti päättyä klo {kello(vuoro['paattyy'])}; gateway päättää sen seuraavalla kierroksella."}
    return {"teksti": "Käynnissä", "savy": "success", "seis": False,
            "selitys": "Ilmari vastaa viesteihin ja tekee työt itse loppuun. Seis pysäyttää työt ja estää uudet."}
