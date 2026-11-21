"""Promptit ja säännöt (aiops 21.11.2026): jokainen teksti, jonka aiops antaa kielimalleille ohjeeksi.

Gateway (aiops-gw) kirjoittaa luettelon tiedostoon toiminta/kehotteet.json (aiops: src/aiops/gateway/kehotteet.py)
käynnistyessään ja aina, kun Elias muokkaa kehotetta. Luettelo kootaan samoista vakioista ja tiedostoista, joita
aiopsin koodi käyttää, joten teksti on se, minkä malli saa. Hub vain näyttää sen: muokkaus on gatewayn lomake
(POST /ilmari/kehote/{tunniste}, paluu=hub) ja palautus /ilmari/kehote/{tunniste}/oletus. Muokattavia ovat ne rivit,
joilla muokattava on tosi (järjestelmäkehote ja vuoron ohje); muut ovat aiopsin koodin vakioita.

Käsikirjan versiot (aiops ADR-0033 pala 6): Ilmari saa muokata itse käsikirjaansa (systemprompti) ja vuoron
ohjettaan. Uusi gateway lisää tiedostoon kentän lukittu (Elias on estänyt Ilmarin muokkaukset) ja jokaiselle riville
kentän versiot: enintään 10 uusinta versiota (numero, aika, kuka, miksi ja teksti; muilla kuin muokattavilla riveillä tyhjä lista). Vanha
muoto ilman näitä kenttiä kelpaa yhä, koska Hub asennetaan ennen gatewayta; silloin versioita ja lukkoa ei näytetä.
Palautus on gatewayn lomake /ilmari/kehote/{tunniste}/versio (n) ja lukko /ilmari/kehote/lukko (lukittu=1|0).
Gateway säilyttää 30 versiota mutta julkaisee vain uusimmat; vanhemman voi palauttaa numerolla (sama lomake).
Rikkinäinen versiolista ei piilota riviä: rivin teksti näkyy, ja versioiden kohdalla lukee, ettei niitä voi näyttää.
Uudessa muodossa muokattavan rivin voimassa oleva teksti on Ilmarin kirjoittamaa, joten se tarkistetaan kuten versiot.
Kielletty merkki Ilmarin tekstissä piilottaa vain sen tekstin (voimassa oleva teksti, version teksti tai perustelu),
ei riviä, lukkoa eikä palautusnappeja: juuri silloin Elias tarvitsee niitä. Lukko näkyy myös, kun luettelo on rikki.

Tiedosto luetaan yhteisellä lukijalla (lukija.py: linkkejä seuraamatta, omistaja, kokoraja, muuttumattomuus luvun
aikana) ja tarkoilla kenttäjoukoilla. Teksti on dataa: pohja koodaa sen, eikä sitä piirretä Markdownina. Ilmarin
kirjoittamassa tekstissä (versio ja perustelu) ei hyväksytä yhtään näkymätöntä muotoilu- tai ohjausmerkkiä.
Ryhmän nimi tulee gatewaylta (rivit ovat ryhmittäin peräkkäin), joten uusi ryhmä ei vaadi muutosta Hubiin.
"""

from __future__ import annotations

import difflib
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .lukija import Hakemisto, ReadFailure, _lue
from .toiminta import VIESTIT, _aika, _jasenna, _kentat, _nakyva_teksti, _perustelu, _stat, _teksti, _virhe

TIEDOSTO = "kehotteet.json"
RAJA = 1024 * 1024
KENTAT = frozenset({"versio", "aika", "kehotteet"})
RIVI_KENTAT = frozenset({"tunniste", "ryhma", "otsikko", "kuvaus", "lahde", "teksti", "oletus", "muokattu",
                         "muokattava", "enint"})
# Uusi muoto (ADR-0033 pala 6): lukko tiedoston tasolla ja versiot jokaisella rivillä, aina yhdessä.
KENTAT_LUKKO = KENTAT | {"lukittu"}
RIVI_KENTAT_VERSIOT = RIVI_KENTAT | {"versiot"}
VERSIO_KENTAT = frozenset({"n", "aika", "kuka", "miksi", "teksti"})
VERSIOITA_MAX = 10
TEKIJAT = {"elias": "Elias", "ilmari": "Ilmari", "tehdas": "alkuperäinen"}   # tehdas: paketin oma teksti palautettu
VANHA_TEHDAS = "aiempi alkuperäinen"   # tehdas-versio, jonka teksti ei ole enää paketin nykyinen alkuperäinen
VERSION_VARA = timedelta(minutes=10)   # versio on kirjoitettu ennen tiedostoa; vara vain kellon heitolle
MUUTOS_RIVIT_MAX = 1000                # pidemmistä teksteistä ei lasketa muutoksia (sivu pysyy nopeana)
MUUTOKSIA_NAYTA = 60                   # näytettävät muuttuneet rivit versiota kohti
MAARA_MAX = 60
TEKSTI_MAX = 32_000
ENINT_MAX = 20_000                 # muokattavan tekstin yläraja, jonka gateway ilmoittaa (nyt 12 000)
OTSIKKO_MAX, KUVAUS_MAX, LAHDE_MAX, RYHMA_MAX = 80, 400, 200, 60
RIVEJA_MIN, RIVEJA_MAX, RIVIN_LEVEYS = 10, 40, 60   # muokkauskentän korkeus tekstin mukaan (puhelimen rivinleveys)
# Säännöt julkaisee aiopsin asennus dokumentteina; nämä näytetään samalla sivulla, jos ne ovat asennetussa versiossa.
SAANTODOKUMENTIT = ("saannot", "agents")
_TUNNISTE = re.compile(r"[a-z][a-z0-9_]{0,39}\Z", re.ASCII)


@dataclass(frozen=True)
class Kehotteet:
    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    aika: str | None = None
    kehotteet: tuple[dict[str, Any], ...] = ()
    lukittu: bool | None = None   # None: vanha gateway, jolla Ilmari ei voi muokata eikä lukkoa ole


def _muutokset(vanha: str, uusi: str, verrattu: int) -> dict[str, Any] | None:
    """Rivit, jotka muuttuivat edellisestä näkyvästä versiosta: lisätyt ja poistetut (enintään MUUTOKSIA_NAYTA
    näytetään). Hyvin monirivisestä tekstistä ei lasketa mitään (None)."""
    a, b = vanha.split("\n"), uusi.split("\n")
    if len(a) > MUUTOS_RIVIT_MAX or len(b) > MUUTOS_RIVIT_MAX:
        return None
    rivit = []
    for laji, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if laji != "equal":
            rivit += [("del", r) for r in a[i1:i2]] + [("add", r) for r in b[j1:j2]]
    return {"verrattu": verrattu, "lisatty": sum(laji == "add" for laji, _ in rivit),
            "poistettu": sum(laji == "del" for laji, _ in rivit), "rivit": tuple(rivit[:MUUTOKSIA_NAYTA]),
            "leikattu": len(rivit) > MUUTOKSIA_NAYTA}


def _versiot(arvo: Any, muokattava: bool, teksti: str | None, perus: str | None,
             tiedoston_aika: datetime) -> tuple[tuple[dict[str, Any], ...], dict[str, Any] | None]:
    """Rivin versiot uusin ensin ja voimassa oleva versio (uusin, jonka teksti on se, minkä malli nyt saa) tai None.
    Versiolla sama=True, kun sen teksti on sama kuin voimassa oleva: sen palauttaminen ei muuttaisi mitään.
    Kielletty merkki version tekstissä tai perustelussa tekee siitä None (ei näytetä; tekstitöntä ei palauteta).
    perus on paketin nykyinen alkuperäinen teksti: tehdas-versio, jonka teksti on muu, on "aiempi alkuperäinen"."""
    if type(arvo) is not list or len(arvo) > VERSIOITA_MAX or (arvo and not muokattava):
        _virhe("Versiolista ei kelpaa.")
    versiot, nahty = [], set()
    for v in arvo:
        _kentat(v, VERSIO_KENTAT, "versio")
        n = v["n"]
        if type(n) is not int or not 0 < n < 2**53 or n in nahty:
            _virhe("Version numero ei kelpaa tai toistuu.")
        nahty.add(n)
        if type(v["kuka"]) is not str or v["kuka"] not in TEKIJAT:
            _virhe("Version kirjoittaja on tuntematon.")
        aika = _aika(v["aika"])
        if datetime.fromisoformat(aika) - tiedoston_aika > VERSION_VARA:   # erotus ei ylitä aikarajoja
            _virhe("Version aika on tiedostoa uudempi.")
        oma = _nakyva_teksti(v["teksti"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True)
        tekija = TEKIJAT[v["kuka"]]
        if v["kuka"] == "tehdas" and perus is not None and oma != perus:
            tekija = VANHA_TEHDAS
        versiot.append({"n": n, "aika": aika, "kuka": v["kuka"], "tekija": tekija, "miksi": _perustelu(v["miksi"]),
                        "teksti": oma, "sama": oma is not None and oma == teksti})
    versiot.sort(key=lambda v: v["n"], reverse=True)
    uusin_sama = next((v["n"] for v in versiot if v["sama"]), None)
    tulos = []
    for i, v in enumerate(versiot):
        edellinen = next((e for e in versiot[i + 1:] if e["teksti"] is not None), None)
        muutokset = None
        if v["teksti"] is not None and edellinen is not None:
            muutokset = _muutokset(edellinen["teksti"], v["teksti"], edellinen["n"])
        tulos.append(v | {"voimassa": v["n"] == uusin_sama, "muutokset": muutokset})
    return tuple(tulos), next((v for v in tulos if v["voimassa"]), None)


def tarkista(data: Any) -> tuple[str, tuple[dict[str, Any], ...], bool | None]:
    """kehotteet.json tarkoilla kentillä: (aika, rivit, lukittu). Muokkauksen tiedot (oletus ja muokattu) ovat joko
    molemmat tai eivät kumpikaan, ja vain muokattavalla rivillä: kiinteää tekstiä ei voi esittää muokattuna.
    Uudessa muodossa (lukittu) jokaisella rivillä on versiot; kelvoton versiolista ei kaada luetteloa, vaan rivin
    versiot ovat None ja versiot_virhe tosi. Vanhassa muodossa versiot ovat None ilman virhettä.
    Uudessa muodossa muokattavan rivin teksti on None ja teksti_virhe tosi, jos siinä on kielletty merkki."""
    uusi = isinstance(data, dict) and "lukittu" in data
    _kentat(data, KENTAT_LUKKO if uusi else KENTAT, TIEDOSTO)
    aika = _aika(data["aika"])
    tiedoston_aika = datetime.fromisoformat(aika)
    if uusi and type(data["lukittu"]) is not bool:
        _virhe("Lukko ei ole totuusarvo.")
    lista = data["kehotteet"]
    if type(lista) is not list or not 0 < len(lista) <= MAARA_MAX:
        _virhe("Luettelo ei kelpaa.")
    rivit, nahty = [], set()
    for r in lista:
        _kentat(r, RIVI_KENTAT_VERSIOT if uusi else RIVI_KENTAT, "kehote")
        tunniste = r["tunniste"]
        if type(tunniste) is not str or _TUNNISTE.fullmatch(tunniste) is None or tunniste in nahty:
            _virhe("Kehotteen tunniste ei kelpaa tai toistuu.")
        nahty.add(tunniste)
        if type(r["muokattava"]) is not bool or type(r["enint"]) is not int or not 0 < r["enint"] <= ENINT_MAX:
            _virhe("Kehotteen muokkaustiedot eivät kelpaa.")
        oletus = None if r["oletus"] is None else _teksti(r["oletus"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True)
        muokattu = _aika(r["muokattu"], tyhja=True)
        if (oletus is None) != (muokattu is None) or (oletus is not None and not r["muokattava"]):
            _virhe("Kehotteen muokkaustiedot ovat ristiriitaiset.")
        if uusi and r["muokattava"]:   # Ilmari voi kirjoittaa tämän tekstin (kehote_muuta)
            teksti = _nakyva_teksti(r["teksti"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True)
        else:
            teksti = _teksti(r["teksti"], TEKSTI_MAX, tyhja=False, rivinvaihdot=True)
        versiot, voimassa, versiot_virhe = None, None, False
        if uusi:
            try:
                versiot, voimassa = _versiot(r["versiot"], r["muokattava"], teksti,
                                             teksti if oletus is None else oletus, tiedoston_aika)
            except ReadFailure:
                versiot_virhe = True
        rivit.append({
            "tunniste": tunniste, "ryhma": _teksti(r["ryhma"], RYHMA_MAX, tyhja=False),
            "otsikko": _teksti(r["otsikko"], OTSIKKO_MAX, tyhja=False),
            "kuvaus": _teksti(r["kuvaus"], KUVAUS_MAX, tyhja=False), "lahde": _teksti(r["lahde"], LAHDE_MAX, tyhja=False),
            "teksti": teksti, "teksti_virhe": teksti is None, "oletus": oletus, "muokattu": muokattu,
            "muokattava": r["muokattava"], "enint": r["enint"], "versiot": versiot, "voimassa": voimassa,
            "versiot_virhe": versiot_virhe})
    return aika, tuple(rivit), data["lukittu"] if uusi else None


def lue_kehotteet(root: str | Path, *, omistajat: frozenset[int] | None = None,
                  timeout_seconds: float = 2.0) -> Kehotteet:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa gateway (aiops-gw) ja root."""
    try:
        kavelija = Hakemisto(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Kehotteet("error", "Polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    lukittu = None   # luetaan ennen rivejä: lukko näkyy, vaikka luettelo olisi rikki
    try:
        with kavelija.juuri(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Hakemiston omistaja on väärä.")
            tiedot = _stat(hd, TIEDOSTO, omistajat)
            if tiedot is None:
                return Kehotteet("not_published", "Prompteja ei ole vielä tallennettu.")
            raaka = _lue(hd, TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
        data = _jasenna(raaka)
        if isinstance(data, dict) and type(data.get("lukittu")) is bool:
            lukittu = data["lukittu"]
        aika, rivit, lukittu = tarkista(data)
        return Kehotteet("ready", None, aika, rivit, lukittu)
    except ReadFailure as error:
        if error.code == "not_found":
            return Kehotteet("not_published", "Prompteja ei ole vielä tallennettu.")
        return Kehotteet("error", VIESTIT.get(error.code, error.message), lukittu=lukittu)
    except OSError as error:
        return Kehotteet("error", f"Prompteja ei voi lukea ({error.strerror}).")


def ryhmittain(luettelo: Kehotteet) -> list[tuple[str, list[dict[str, Any]]]]:
    """Ryhmät ensimmäisen esiintymän järjestyksessä; rivit ryhmän sisällä luettelon järjestyksessä."""
    ryhmat: dict[str, list[dict[str, Any]]] = {}
    for rivi in luettelo.kehotteet:
        ryhmat.setdefault(rivi["ryhma"], []).append(rivi)
    return list(ryhmat.items())


def etsi(luettelo: Kehotteet, tunniste: str) -> dict[str, Any] | None:
    if _TUNNISTE.fullmatch(tunniste) is None:
        return None
    return next((r for r in luettelo.kehotteet if r["tunniste"] == tunniste), None)


def korkeus(teksti: str) -> int:
    """Muokkauskentän rivimäärä: pitkät rivit rivittyvät puhelimella, joten ne lasketaan useana."""
    riveja = sum(max(1, math.ceil(len(rivi) / RIVIN_LEVEYS)) for rivi in teksti.split("\n"))
    return max(RIVEJA_MIN, min(RIVEJA_MAX, riveja + 2))
