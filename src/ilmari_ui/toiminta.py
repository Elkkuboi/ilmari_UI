"""Ilmarin toiminta Hubissa (aiops ADR-0032, Pala 1 "Ilmari toimii itse", 18.11.2026; Pala 1b työvuoro ja raportti).

Gateway (aiops-gw) kirjoittaa hakemistoon /srv/aiops/ilmari/toiminta (aiops-gw:ilmari-julkaisu 2750) Ilmarin tilan:

- asetukset.json  yöajo päällä/pois ja kellonaika (Elias muuttaa Hubista, gateway tallentaa)
- tila.json       Seis-kytkin, viimeisin yöajo, käynnissä oleva vuoro (yöajo tai Eliaksen napista käynnistämä
                  työvuoro) ja viimeisin rajatestin tulos
- ohjeet.json     pysyvät ohjeet (Eliaksen korjaukset, jotka Ilmari tallensi)
- tavoitteet.json Eliaksen tavoitteet riveinä
- teot.jsonl      tekoloki: rivi per teko, vain lisäys; yli 2 MiB:n jälkeen vanha nimetään teot.1.jsonl:ksi
- raportti.json   viimeisimmän päättyneen vuoron raportti (vuoron säikeen viimeisin Ilmarin viesti); puuttuu, kunnes
                  ensimmäinen vuoro on päättynyt raporttiin (aikakatko ja Seis eivät kirjoita sitä)
- varaukset.json  Ilmarin itse varaamat työvuorot, jotka eivät ole vielä alkaneet (aiops ADR-0033 pala 6); puuttuu
                  vanhalta gatewaylta, mikä tarkoittaa, ettei varauksia ole

JSON-tiedostot gateway vaihtaa atomisesti (tmp + rename), joten ne luetaan yhteisellä lukijalla (lukija.py: linkkejä seuraamatta,
omistaja, kokoraja, muuttumattomuus luvun aikana) ja tarkoilla kenttäjoukoilla. Puuttuva tiedosto tarkoittaa
oletusarvoja kuten gatewayssa; puuttuva hakemisto on "not_published". Tekoloki kasvaa lukemisen aikana, joten siitä
luetaan vain avaushetken koon loppu (enintään HANTA tavua): myöhemmät lisäykset eivät muuta luettua osaa, mutta
katkaisu, linkitys tai tiedoston vaihto kesken luvun on virhe. Rikkinäinen tekorivi ohitetaan ja lasketaan.

Jokaisen tiedoston virhe on oma: rikkinäinen tekoloki ei piilota Seis-tilaa. Kaikki teksti on mallin tai gatewayn
kirjoittamaa dataa: se siivotaan ohjausmerkeistä ja pohja koodaa sen (ei |safe-polkua, ei Markdownia). Hub ei kirjoita
mitään; Seis, Jatka, Töihin nyt, asetukset, tavoitteet, ohjeen poisto, rajatesti ja varauksen peruminen ovat
gatewayn lomakereittejä (paluu=hub).
"""

from __future__ import annotations

import os
import re
import stat
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .dokumentit import _json, _kelpaa
from .lukija import _FILE_FLAGS, Hakemisto, ReadFailure, _fail_os, _identity, _lue

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
RAPORTTI = "raportti.json"
VARAUKSET = "varaukset.json"
RAJAT = {ASETUKSET: 4 * 1024, TILA: 64 * 1024, OHJEET: 256 * 1024, TAVOITTEET: 64 * 1024, RAPORTTI: 64 * 1024,
         VARAUKSET: 16 * 1024}
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
RAPORTTI_KENTAT = frozenset({"versio", "aika", "saie", "laji", "teksti"})
VARAUKSET_KENTAT = frozenset({"versio", "aika", "varaukset"})
VARAUS_KENTAT = frozenset({"id", "alkaa", "minuutit", "miksi"})

OLETUS_ASETUKSET = {"paalla": True, "kello": "02:00"}
VUOROT = {"yoajo": "Yöajo", "tyovuoro": "Työvuoro"}   # vuoron ja raportin laji (gateway: yöajo tai Töihin nyt)
VUORON_TYOT = {"yoajo": "yön työt", "tyovuoro": "työvuoron työt"}
# Tekolokin "työ N" on linkki Kehitä-sivulle vain työriveillä, joiden työ julkaistaan siellä: muiden rivien työtä
# (esim. rajatesti) ei julkaista, joten linkki veisi 404-sivulle. Gateway kirjoittaa näiden rivien työn numeron aina
# itse; tyo_alkoi-rivin lähde on silti "ilmari", koska sen teksti on mallin (tehtävän ensimmäinen rivi). Ilmarin omat
# kirjaukset ovat lajia "kirjaus", eivätkä ne voi olla näitä lajeja.
TYO_LINKIT = frozenset({"tyo_alkoi", "tyo_paattyi", "tyo_peruttu"})
ODOTUKSET = {"estetty": "pitää estyä", "sallittu": "pitää toimia"}
TEKIJAT = {"gateway": "kone", "ilmari": "Ilmari"}   # kone = gatewayn havaitsema tosiasia
OHJEITA_MAX, OHJE_MAX = 40, 400
RIVEJA_MAX, RIVI_MAX = 20, 200
KOHTIA_MAX, HAVAINTO_MAX, KOHTA_NIMI_MAX = 40, 200, 120
TEKO_TEKSTI_MAX = 1000
RAPORTTI_MAX = 8000                # = Ilmarin viestin enimmäispituus gatewayssa
# Varaukset: gateway pitää enintään 3 odottamassa ja vuoron pituuden 30–240 min; lista saa olla vähän pidempi, jotta
# rajan nosto gatewayssa ei kaada Hubia.
VARAUKSIA_MAX = 10
MINUUTIT_MIN, MINUUTIT_MAX = 30, 240
MIKSI_MAX = 300                    # Ilmarin perustelu: yksi rivi (varaus, käsikirjan versio)
# Ilmarin kirjoittamassa tekstissä kielletyt merkit kuten gatewayssa (aiops merkit.forbidden_char): ohjausmerkit,
# näkymättömät muotoilumerkit (myös bidi-merkit), surrogaatit sekä rivin- ja kappaleenerottimet. Emojien ZWJ sallitaan.
_KIELLETYT_LUOKAT = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
_ZWJ = chr(0x200D)
# Perustelussa lisäksi tyhjiltä näyttävät kirjaimet, joita gateway ei vielä hylkää (hangulin täytemerkit, tyhjä
# pistekirjoitusmerkki, yhdistävä CGJ): niillä perustelu näyttäisi tyhjältä tai tekstissä olisi näkymätöntä täytettä.
_TYHJAT_KIRJAIMET = frozenset(chr(o) for o in (0x034F, 0x115F, 0x1160, 0x2800, 0x3164, 0xFFA0))
_KELLO = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z", re.ASCII)
VIESTIT = {
    "wrong_owner": "Tiedoston omistaja on väärä.",
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
    raportti: dict[str, Any] | None = None   # None: ei julkaistu (paneelia ei näytetä) tai ei luettavissa
    raportti_virhe: bool = False
    varaukset: tuple[dict[str, Any], ...] | None = ()   # None: tiedostoa ei voi lukea (syy listassa virheet)


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


def _tarkka_teksti(arvo: Any, raja: int, *, tyhja: bool = True, rivinvaihdot: bool = False) -> str:
    """Ilmarin kirjoittama teksti (perustelu, käsikirjan versio): kuten _teksti, ja lisäksi ei yhtään näkymätöntä
    muotoilu- tai ohjausmerkkiä. Gateway hylkää samat merkit tallentaessaan, joten tällainen merkki tiedostossa on
    virhe, ei Ilmarin tekstiä. Monirivisessä sallitaan rivinvaihto ja sarkain."""
    teksti = _teksti(arvo, raja, tyhja=tyhja, rivinvaihdot=rivinvaihdot)
    sallitut = "\n\r\t" if rivinvaihdot else ""
    if any(c not in sallitut and c != _ZWJ and unicodedata.category(c) in _KIELLETYT_LUOKAT for c in teksti):
        _virhe("Tekstikentässä on kielletty merkki.")
    return teksti


def _nakyva_teksti(arvo: Any, raja: int, *, tyhja: bool = True, rivinvaihdot: bool = False) -> str | None:
    """Ilmarin teksti tarkalla säännöllä, mutta kielletty merkki ei ole koko tiedoston virhe: tulos on None, ja sivu
    kertoo, ettei tekstiä voi näyttää (varaus, versio ja palautusnapit jäävät näkyviin). Väärä tyyppi tai pituus on
    virhe kuten ennenkin."""
    if type(arvo) is not str or len(arvo) > raja or (not tyhja and not arvo.strip()):
        _virhe("Tekstikenttä puuttuu tai ylittää rajan.")
    try:
        return _tarkka_teksti(arvo, raja, tyhja=tyhja, rivinvaihdot=rivinvaihdot)
    except ReadFailure:
        return None


def _perustelu(arvo: Any) -> str | None:
    """Ilmarin perustelu (yksi rivi, enintään MIKSI_MAX): None, jos siinä on kielletty tai tyhjältä näyttävä merkki."""
    teksti = _nakyva_teksti(arvo, MIKSI_MAX)
    return None if teksti is None or any(c in _TYHJAT_KIRJAIMET for c in teksti) else teksti


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
    try:
        aika.astimezone(HELSINKI)   # vuosi 1 tai 9999 ei mahdu Suomen aikaan: sivu ei saa kaatua sen näyttämiseen
    except (OverflowError, ValueError):
        _virhe("Aika ei kelpaa.")
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


def tarkista_raportti(data: Any) -> dict[str, Any]:
    """raportti.json: viimeisimmän vuoron raportti. Teksti on mallin kirjoittamaa: rivinvaihdot sallitaan, ohjausmerkit
    eivät; tuntematon laji on kelvoton tiedosto."""
    _kentat(data, RAPORTTI_KENTAT, RAPORTTI)
    if type(data["laji"]) is not str or data["laji"] not in VUOROT:
        _virhe("Raportin laji on tuntematon.")
    return {"aika": _aika(data["aika"]), "saie": _kokonaisluku(data["saie"]), "laji": data["laji"],
            "nimi": VUOROT[data["laji"]], "teksti": _teksti(data["teksti"], RAPORTTI_MAX, tyhja=False, rivinvaihdot=True)}


def tarkista_varaukset(data: Any) -> tuple[dict[str, Any], ...]:
    """varaukset.json: Ilmarin varaamat työvuorot, jotka eivät ole vielä alkaneet, aikaisin ensin, ja kunkin loppuaika.
    Perustelu on mallin kirjoittamaa (yksi rivi): kielletty tai tyhjältä näyttävä merkki piilottaa vain perustelun
    (miksi None), ei varausta eikä sen Peru-nappia."""
    _kentat(data, VARAUKSET_KENTAT, VARAUKSET)
    _aika(data["aika"])
    if type(data["varaukset"]) is not list or len(data["varaukset"]) > VARAUKSIA_MAX:
        _virhe("Varauslista ei kelpaa.")
    varaukset, tunnisteet = [], set()
    for v in data["varaukset"]:
        _kentat(v, VARAUS_KENTAT, "varaus")
        tunniste = _kokonaisluku(v["id"])
        if tunniste in tunnisteet:
            _virhe("Sama varauksen tunniste kahdesti.")
        tunnisteet.add(tunniste)
        if type(v["minuutit"]) is not int or not MINUUTIT_MIN <= v["minuutit"] <= MINUUTIT_MAX:
            _virhe("Varauksen kesto ei kelpaa.")
        alkaa = _aika(v["alkaa"])
        try:
            loppuu = _aika((datetime.fromisoformat(alkaa) + timedelta(minutes=v["minuutit"])).isoformat())
        except OverflowError:
            _virhe("Varauksen aika ei kelpaa.")
        varaukset.append({"id": tunniste, "alkaa": alkaa, "loppuu": loppuu, "minuutit": v["minuutit"],
                          "miksi": _perustelu(v["miksi"])})
    return tuple(sorted(varaukset, key=lambda v: datetime.fromisoformat(v["alkaa"])))


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
        tyo = _kokonaisluku(t["tyo"], tyhja=True)
        return {"aika": _aika(t["aika"]), "lahde": t["lahde"], "tekija": TEKIJAT[t["lahde"]],
                "laji": _siisti(t["laji"], 40), "mita": _siisti(t["mita"], TEKO_TEKSTI_MAX),
                "miksi": _siisti(t["miksi"], TEKO_TEKSTI_MAX), "peru": _siisti(t["peru"], TEKO_TEKSTI_MAX),
                "tyo": tyo, "saie": _kokonaisluku(t["saie"], tyhja=True),
                "tyo_linkki": tyo is not None and t["laji"] in TYO_LINKIT}
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
        kavelija = Hakemisto(root, timeout_seconds=timeout_seconds)
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
        with kavelija.juuri(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Tilan hakemiston omistaja on väärä.")

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
            osa(RAPORTTI, lambda: json_osa(RAPORTTI, tarkista_raportti), False)  # False: ei julkaistu
            osa(VARAUKSET, lambda: json_osa(VARAUKSET, tarkista_varaukset), ())   # puuttuu: ei varauksia
    except ReadFailure as error:
        if error.code == "not_found":
            return Toiminta("not_published", "Ilmarin tilaa ei ole vielä tallennettu.")
        return Toiminta("error", VIESTIT.get(error.code, error.message))
    except OSError as error:
        return Toiminta("error", f"Toimintaa ei voi lukea ({error.strerror}).")
    teot, ohitettu = osat[TEOT] if osat[TEOT] is not None else (None, 0)
    return Toiminta("ready", None, osat[ASETUKSET], osat[TILA], osat[OHJEET], osat[TAVOITTEET], teot, ohitettu,
                    tuple(virheet), raportti=osat[RAPORTTI] or None, raportti_virhe=osat[RAPORTTI] is None,
                    varaukset=osat[VARAUKSET])


# --- Näyttö -----------------------------------------------------------------------------------------------------------

def kello(arvo: str | None) -> str:
    """ISO-aika Helsingin kellonaikana (04.55) tai tyhjä."""
    try:
        return datetime.fromisoformat(arvo).astimezone(HELSINKI).strftime("%H.%M") if arvo else ""
    except (ValueError, TypeError, OverflowError):
        return ""


def rajatesti_kaynnissa(toiminta: Toiminta | None, dsh_tyo: int | None) -> bool:
    """Onko käynnissä oleva dsh-työ rajatesti? Gateway kirjaa jonoon jätetyn rajatestin tekolokiin (laji rajatesti,
    lähde gateway, työn numero); uusin tällainen rivi kertoo saman työn. Rajatestiä ei julkaista Kehitä-sivulle, joten
    sille ei tehdä linkkiä, ja Töihin nyt -pyyntö odottaa sen tulosta."""
    if toiminta is None or dsh_tyo is None or not toiminta.teot:
        return False
    rivi = next((t for t in reversed(toiminta.teot) if t["laji"] == "rajatesti" and t["lahde"] == "gateway"), None)
    return rivi is not None and rivi["tyo"] == dsh_tyo


def tilarivi(toiminta: Toiminta | None, nyt: datetime) -> dict[str, Any] | None:
    """Hubin etusivun tila: {teksti, savy, selitys, seis, toihin, kaynnissa}. seis: True = pysäytetty, False = ei,
    None = ei tiedossa (silloin sivu näyttää sekä Seis- että Jatka-napin). toihin: Töihin nyt -nappi näytetään vain,
    kun tila on luettu, Seis ei ole päällä eikä vuoroa ole (myös rikkinäinen vuoro piilottaa sen); gateway tarkistaa
    saman itse. kaynnissa: vuoro on käynnissä (sivu päivittyy itsestään). Selitys on lyhyt ja ilman jargonia; sivu
    lisää siihen mallin tilan ja yöajon ajan."""
    if toiminta is None:
        return None
    if toiminta.tila != "ready" or toiminta.tilanne is None:
        return {"teksti": "Tila ei tiedossa", "savy": "warning", "seis": None, "toihin": False, "kaynnissa": False,
                "selitys": "Ilmarin tilaa ei voi lukea. Seis ja Jatka toimivat silti."}
    t = toiminta.tilanne
    if t["seis"]:
        kuka = f" ({t['seis_kuka']})" if t["seis_kuka"] else ""
        aika = kello(t["seis_aika"])
        return {"teksti": "Seis", "savy": "danger", "seis": True, "toihin": False, "kaynnissa": False,
                "selitys": (f"Pysäytetty klo {aika}{kuka}. " if aika else "Pysäytetty. ")
                + "Ilmari ei aloita töitä eikä yöajoa ennen kuin painat Jatka."}
    vuoro = t["vuoro"]
    if vuoro is not None:
        paattyy = datetime.fromisoformat(vuoro["paattyy"])
        tyot = VUORON_TYOT.get(vuoro["laji"], "vuoron työt")
        if paattyy > nyt:
            return {"teksti": f"{vuoro['nimi']} klo {kello(vuoro['paattyy'])} asti", "savy": "accent",
                    "seis": False, "toihin": False, "kaynnissa": True,
                    "selitys": f"Ilmari tekee {tyot} säikeeseen {vuoro['saie']}."}
        return {"teksti": f"{vuoro['nimi']}n aika ylittyi", "savy": "warning", "seis": False, "toihin": False,
                "kaynnissa": True,
                "selitys": f"Vuoron piti päättyä klo {kello(vuoro['paattyy'])}; se päättyy hetken kuluttua."}
    return {"teksti": "Vapaa", "savy": "success", "seis": False, "toihin": t.get("vuoro_virhe") is False,
            "kaynnissa": False, "selitys": ""}
