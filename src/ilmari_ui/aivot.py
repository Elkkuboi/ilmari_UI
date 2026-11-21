"""Aivojen koodi (aiops ADR-0033 pala 7): mitkä aivot ovat käytössä, lukko, asennusraja, vahti ja versiot.

Ilmari saa kirjoittaa omien aivojensa koodin ja pyytää sen käyttöön. Asentaja (aiops src/aiops/aivohuolto.py, root)
tarkistaa ehdokkaan, asentaa sen, käynnistää aivot uudelleen ja palaa edelliseen tai alkuperäiseen, jos uusi ei ole
terve. Se kirjoittaa tilansa tiedostoon /srv/aiops/ilmari/aivot/tila.json (muoto aiops-aivot-tila-v1, root:
ilmari-julkaisu 0640 setgid-hakemistossa 2750) jokaisen pyynnön jälkeen, ja vahti kirjoittaa sen uudelleen 2 min
välein. Tiedosto on enintään 512 KiB (aivohuolto.JULKAISU_MAX): asentaja karsii vanhimmat diffit ja tiedostolistat.

Puuttuva hakemisto tai tiedosto tarkoittaa, ettei itsepäivitys ole käytössä tällä koneella: se ei ole virhe, eikä
sivulla silloin ole lomakkeita. Hub ei kirjoita mitään: lukko ja palautukset ovat gatewayn lomakkeita
(POST /ilmari/aivot/lukko lukittu=1|0 ja POST /ilmari/aivot/palauta kohde=edellinen|tehdas, lukitse=1), paluu=hub.

Luku: yhteinen lukija (lukija.py: linkkejä seuraamatta, kokoraja, muuttumattomuus luvun aikana), tuotannossa vain
rootin omistama hakemisto ja tiedosto, tiukka JSON ja tarkat kenttäjoukot. Ylätason rakenne on koko tiedoston ehto;
muut osat tarkistetaan erikseen, joten rikkinäinen versiorivi piilottaa vain itsensä eikä lukkoa tai nappeja. Lukko
luetaan ensin, joten se näkyy myös, kun tiedosto on muuten rikki.

Kaikki teksti on dataa, ja suuri osa siitä tulee Ilmarin ehdokkaasta: tiedostonimet, syyt (asentaja liittää niihin
nimiä ja jäsentimen viestejä) ja diff. Pohja koodaa sen, eikä mitään piirretä Markdownina. Kielletty merkki
(ohjaus- ja muotoilumerkit, myös bidi, surrogaatit, rivin- ja kappaleenerottimet; yksirivisessä myös tyhjältä näyttävät
kirjaimet) piilottaa vain sen kentän ("ei voi näyttää"). Asentaja muuttaa nämä merkit näkyviksi koodeiksi (\\uXXXX),
joten kunnollisessa tiedostossa niitä ei ole.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lukija import Hakemisto, ReadFailure, _lue
from .toiminta import _TYHJAT_KIRJAIMET, VIESTIT, _aika, _jasenna, _nakyva_teksti, _stat, _virhe

OLETUS = Path("/srv/aiops/ilmari/aivot")
ESIMERKKI = Path(__file__).resolve().parent / "demo" / "aivot"
OMISTAJAT = frozenset({0})            # tuotannossa vain asentaja (root) kirjoittaa tilan
TIEDOSTO = "tila.json"
MUOTO = "aiops-aivot-tila-v1"
RAJA = 512 * 1024                     # = aiops aivohuolto.JULKAISU_MAX
TEHDAS = "tehdas"                     # alkuperäiset aivot (asennetusta commitista), ei Ilmarin versio

KENTAT = frozenset({"muoto", "aika", "aktiivinen", "edellinen", "lukittu", "lukko", "asennuksia_24h",
                    "asennuksia_max", "asennuksia_jaljella", "asennukset_24h", "seuraava_vapautuu", "kesken",
                    "versiot", "pyynnot", "vahti"})
AKTIIVINEN_KENTAT = frozenset({"versio", "aika", "kuka"})
LUKKO_KENTAT = frozenset({"aika", "kuka", "syy"})
KESKEN_KENTAT = frozenset({"toimi", "versio", "aika"})
VAHTI_KENTAT = frozenset({"aika", "syy", "versio", "toimi", "uudelleenkaynnistys"})
VERSIO_KENTAT = frozenset({"versio", "aika", "kuka", "tulos", "syy", "tiedostot", "diff", "diff_katkaistu",
                           "varastossa", "hylatty"})
TIEDOSTO_KENTAT = frozenset({"polku", "koko"})
PYYNTO_KENTAT = frozenset({"id", "toimi", "kuka", "pyydetty", "aika", "tulos", "syy", "versio"})

# Rajat: asentaja julkaisee 10 versiota ja 30 pyyntöä, versiossa on enintään 100 tiedostoa (256 KiB kukin) ja diff on
# enintään 64 KiB. Listoissa on väljyyttä, jotta rajan nosto asentajassa ei kaada sivua.
VERSIOITA_MAX = 20
PYYNTOJA_MAX = 60
TIEDOSTOJA_MAX = 200
KOKO_MAX = 2 * 1024 * 1024
ASENNUKSIA_MAX = 100
POLKU_MAX = 200
SYY_MAX = 4000
TOIMI_MAX = 300
DIFF_MAX = 64 * 1024
DIFF_RIVEJA_NAYTA = 2000              # pidempi diff leikataan sivulla (puhelin)

TEKIJAT = {"ilmari": "Ilmari", "elias": "Elias", "vahti": "vahti"}
PYYTAJAT = ("ilmari", "elias")
TOIMET = {"asenna": "asenna", "palauta_edellinen": "palauta edellinen", "palauta_tehdas": "palauta alkuperäinen",
          "lukitse": "lukitse", "avaa": "avaa lukko"}
KESKEN_TOIMET = {"asenna": "asennus", "palauta_edellinen": "edellisen palautus",
                 "palauta_tehdas": "alkuperäisen palautus", "vahti": "vahdin toimi"}
# Versiorivi on tapahtuma: mitä tehtiin ja kenen pyynnöstä. Tulos näytetään erikseen (käytössä, hylätty, palautettu,
# ei käytössä). virhe: asentaja vei keskeytyneen toimen, jota ei voinut lukea, turvaan alkuperäiseen.
TEOT = {"asennettu": "asennus", "peruttu": "asennus", "palautettu": "palautus", "vahti": "vahti poisti käytöstä",
        "virhe": "keskeytynyt toimi"}
PYYNTO_TULOKSET = {"asennettu": ("asennettu", "ok"), "palautettu": ("palautettu", "ok"), "lukittu": ("lukittu", ""),
                   "avattu": ("lukko avattu", ""), "peruttu": ("kokeiltu, peruttu", "stop"),
                   "hylatty": ("hylätty", "stop"), "virhe": ("virhe", "stop")}
VAHDIN_TOIMI = "tehdasversio, hylkäys ja lukitus"     # aivohuollon kiinteä kuvaus vahdin toimesta
VAHDIN_TOIMI_TEKSTI = "otti alkuperäisen käyttöön, hylkäsi version ja lukitsi"
_VERSIO = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PYYNTO_ID = re.compile(r"[0-9]{1,18}\Z", re.ASCII)
_HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", re.ASCII)


@dataclass(frozen=True)
class Aivot:
    """Luettu tila. tila "not_published": itsepäivitys ei ole käytössä (ei virhe). Osa on None, kun sitä ei voi
    näyttää; listan alkio on None, kun vain se rivi on kelvoton."""

    tila: str  # "ready" | "not_published" | "error"
    viesti: str | None = None
    aika: str | None = None
    lukittu: bool | None = None       # None: ei tiedossa (sivu tarjoaa sekä lukituksen että avauksen)
    lukko: dict[str, Any] | None = None
    aktiivinen: dict[str, Any] | None = None
    edellinen: str | None = None
    edellinen_virhe: bool = False
    asennukset: dict[str, Any] | None = None
    kesken: dict[str, Any] | None = None
    vahti: dict[str, Any] | None = None
    vahti_virhe: bool = False
    versiot: tuple[dict[str, Any] | None, ...] | None = ()
    pyynnot: tuple[dict[str, Any] | None, ...] | None = ()


# --- Kentät -----------------------------------------------------------------------------------------------------------

def _olio(data: Any, kentat: frozenset[str], nimi: str) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != kentat:
        _virhe(f"{nimi}: kentät eivät vastaa muotoa.")
    return data


def _versio(arvo: Any, *, tyhja: bool = False) -> str | None:
    """Version tunniste (64 heksaa) tai "tehdas"; None vain, jos sallittu."""
    if arvo is None and tyhja:
        return None
    if arvo == TEHDAS or (type(arvo) is str and _VERSIO.fullmatch(arvo)):
        return arvo
    _virhe("Version tunniste ei kelpaa.")


def _rivi(arvo: Any, raja: int) -> str | None:
    """Yksirivinen teksti (syy, nimi): väärä tyyppi tai pituus on rivin virhe; kielletty tai tyhjältä näyttävä merkki
    piilottaa vain tämän kentän (None)."""
    teksti = _nakyva_teksti(arvo, raja)
    return None if teksti is None or any(c in _TYHJAT_KIRJAIMET for c in teksti) else teksti


def _maara(arvo: Any, ylaraja: int) -> int:
    if type(arvo) is not int or not 0 <= arvo <= ylaraja:
        _virhe("Määrä ei kelpaa.")
    return arvo


def lyhyt(versio: str) -> str:
    """Version näkyvä nimi: 12 ensimmäistä heksaa (kuten asentajan viesteissä)."""
    return versio[:12]


def koko_teksti(tavua: int) -> str:
    if tavua < 1024:
        return f"{tavua} tavua"
    return f"{tavua / 1024:.1f}".replace(".", ",") + " kt"


# --- Osat -------------------------------------------------------------------------------------------------------------

def _aktiivinen(a: Any) -> dict[str, Any]:
    _olio(a, AKTIIVINEN_KENTAT, "aktiivinen")
    versio = _versio(a["versio"])
    if a["kuka"] is not None and a["kuka"] not in PYYTAJAT:
        _virhe("Käytössä olevan version pyytäjä on tuntematon.")
    return {"versio": versio, "tehdas": versio == TEHDAS, "lyhyt": lyhyt(versio),
            "aika": _aika(a["aika"], tyhja=True), "kuka": a["kuka"]}


def _lukko(lukittu: bool, lukko: Any) -> dict[str, Any] | None:
    """Lukon tiedot (aika, kuka, syy) tai None. Lukitulla tila on aina olemassa; avoimella sitä ei ole."""
    if not lukittu:
        if lukko is not None:
            _virhe("Lukon tiedot ilman lukkoa.")
        return None
    _olio(lukko, LUKKO_KENTAT, "lukko")
    kuka = lukko["kuka"]
    if kuka is not None and kuka not in TEKIJAT:
        _virhe("Lukitsija on tuntematon.")
    syy = None if lukko["syy"] is None else _rivi(lukko["syy"], SYY_MAX)
    return {"aika": _aika(lukko["aika"], tyhja=True), "kuka": kuka,
            "tekija": TEKIJAT.get(kuka, "tuntematon"), "syy": syy}


def _asennukset(data: dict[str, Any]) -> dict[str, Any]:
    """Käyttöönottojen raja 24 tunnissa: tehty, enimmäismäärä, jäljellä ja milloin seuraava vapautuu."""
    tehty = _maara(data["asennuksia_24h"], ASENNUKSIA_MAX)
    enint = _maara(data["asennuksia_max"], ASENNUKSIA_MAX)
    jaljella = _maara(data["asennuksia_jaljella"], ASENNUKSIA_MAX)
    ajat = data["asennukset_24h"]
    if enint == 0 or jaljella != max(0, enint - tehty) or type(ajat) is not list or len(ajat) != tehty:
        _virhe("Asennusraja ei vastaa muotoa.")
    for aika in ajat:
        _aika(aika)
    return {"tehty": tehty, "max": enint, "jaljella": jaljella,
            "seuraava": _aika(data["seuraava_vapautuu"], tyhja=True)}


KESKEN_TUNTEMATON = {"toimi": None, "teksti": "toimi", "versio": None, "lyhyt": None, "aika": None}


def _kesken(k: Any) -> dict[str, Any] | None:
    """Keskeneräinen toimi (asennus, palautus tai vahdin toimi) tai None. Kelvotonkin aie on aie: silloin
    KESKEN_TUNTEMATON, jotta sivu kertoo jonkin olevan kesken eikä piilota palautusta."""
    if k is None:
        return None
    try:
        _olio(k, KESKEN_KENTAT, "kesken")
        if k["toimi"] is not None and k["toimi"] not in KESKEN_TOIMET:
            _virhe("Keskeneräinen toimi on tuntematon.")
        versio = _versio(k["versio"], tyhja=True)
        return {"toimi": k["toimi"], "teksti": KESKEN_TOIMET.get(k["toimi"], "toimi"), "versio": versio,
                "lyhyt": None if versio is None else lyhyt(versio), "aika": _aika(k["aika"], tyhja=True)}
    except ReadFailure:
        return dict(KESKEN_TUNTEMATON)


def _vahti(v: Any) -> dict[str, Any] | None:
    """Vahdin viimeisin toimi tai None."""
    if v is None:
        return None
    _olio(v, VAHTI_KENTAT, "vahti")
    toimi = _rivi(v["toimi"], TOIMI_MAX)
    versio = _versio(v["versio"], tyhja=True)
    uudelleen = _rivi(v["uudelleenkaynnistys"], TOIMI_MAX)
    return {"aika": _aika(v["aika"]), "syy": _rivi(v["syy"], SYY_MAX), "versio": versio,
            "lyhyt": None if versio is None else lyhyt(versio),
            "toimi": VAHDIN_TOIMI_TEKSTI if toimi == VAHDIN_TOIMI else toimi,
            "uudelleenkaynnistys": uudelleen, "uudelleen_ok": uudelleen == "ok"}


def _diff(teksti: str) -> dict[str, Any]:
    """Unified diff alkuperäiseen riveittäin lajeineen (meta, hunk, add, del, ctx) sekä muuttuneet tiedostot.
    Hunkien rivimäärät luetaan otsakkeesta, joten sisältörivi, joka alkaa merkeillä --- tai +++, ei ole otsake."""
    rivit: list[tuple[str, str]] = []
    tiedostot: dict[str, dict[str, Any]] = {}
    vanha: str | None = None
    nykyinen: dict[str, Any] | None = None
    jaljella_vanha = jaljella_uusi = 0
    lisatty = poistettu = 0
    osat = teksti.split("\n")
    if osat and osat[-1] == "":
        osat.pop()
    for rivi in osat:
        if jaljella_vanha > 0 or jaljella_uusi > 0:
            if rivi.startswith("+"):
                laji, jaljella_uusi = "add", jaljella_uusi - 1
            elif rivi.startswith("-"):
                laji, jaljella_vanha = "del", jaljella_vanha - 1
            elif rivi.startswith(" ") or rivi == "":
                laji, jaljella_vanha, jaljella_uusi = "ctx", jaljella_vanha - 1, jaljella_uusi - 1
            else:   # katkaisumerkintä tai muu: hunkki päättyi
                laji, jaljella_vanha, jaljella_uusi = "hunk", 0, 0
        elif rivi.startswith("@@") and (m := _HUNK.match(rivi)):
            laji = "hunk"
            jaljella_vanha = int(m.group(1)) if m.group(1) is not None else 1
            jaljella_uusi = int(m.group(2)) if m.group(2) is not None else 1
        elif rivi.startswith("--- "):
            laji, vanha = "meta", rivi[4:]
        elif rivi.startswith("+++ ") and vanha is not None:
            laji, uusi = "meta", rivi[4:]
            polku = (uusi.removeprefix("uusi/") if uusi != "/dev/null" else vanha.removeprefix("tehdas/"))
            muutos = "poistettu" if uusi == "/dev/null" else ("uusi" if vanha == "/dev/null" else "muutettu")
            nykyinen = tiedostot.setdefault(polku, {"polku": polku, "laji": muutos, "lisatty": 0, "poistettu": 0})
            vanha = None
        elif rivi.startswith("[diff katkaistu"):
            laji = "hunk"
        else:
            laji = "meta"
        if laji == "add":
            lisatty += 1
            if nykyinen is not None:
                nykyinen["lisatty"] += 1
        elif laji == "del":
            poistettu += 1
            if nykyinen is not None:
                nykyinen["poistettu"] += 1
        rivit.append((laji, rivi))
    return {"rivit": tuple(rivit[:DIFF_RIVEJA_NAYTA]), "leikattu": len(rivit) > DIFF_RIVEJA_NAYTA,
            "lisatty": lisatty, "poistettu": poistettu, "tiedostot": list(tiedostot.values())}


def _tiedostot(arvo: Any) -> tuple[dict[str, Any], ...]:
    if type(arvo) is not list or len(arvo) > TIEDOSTOJA_MAX:
        _virhe("Tiedostolista ei kelpaa.")
    tulos = []
    for t in arvo:
        _olio(t, TIEDOSTO_KENTAT, "tiedosto")
        koko = _maara(t["koko"], KOKO_MAX)
        tulos.append({"polku": _rivi(t["polku"], POLKU_MAX), "koko": koko, "koko_teksti": koko_teksti(koko)})
    return tuple(tulos)


def _versiorivi(v: Any, kaytossa: str | None, nahty: set[str]) -> dict[str, Any]:
    """Yksi versiohistorian rivi. kaytossa on käytössä olevan version tunniste (tai None); vain uusin rivi, jolla se
    on, merkitään käytössä olevaksi (nahty: uudemmilla riveillä jo nähdyt versiot)."""
    _olio(v, VERSIO_KENTAT, "versio")
    versio = _versio(v["versio"])
    if v["kuka"] not in (*TEKIJAT, "?") or v["tulos"] not in TEOT:
        _virhe("Version tekijä tai tulos on tuntematon.")
    if any(type(v[k]) is not bool for k in ("diff_katkaistu", "varastossa", "hylatty")):
        _virhe("Version tiedot eivät ole totuusarvoja.")
    tiedostot = _tiedostot(v["tiedostot"])
    if type(v["diff"]) is not str or len(v["diff"]) > DIFF_MAX:
        _virhe("Diff ei kelpaa.")
    diff = _nakyva_teksti(v["diff"], DIFF_MAX, rivinvaihdot=True)
    on_kaytossa = versio == kaytossa and versio not in nahty
    nahty.add(versio)
    tulos, hylatty = v["tulos"], v["hylatty"]
    if on_kaytossa:
        tila, savy = "käytössä", "ok"
    elif tulos in ("peruttu", "vahti"):
        tila, savy = "hylätty", "stop"
    elif hylatty:                      # asennus onnistui, mutta vahti tai palautus hylkäsi version myöhemmin
        tila, savy = "hylätty myöhemmin", "stop"
    elif tulos == "virhe":
        tila, savy = "virhe", "stop"
    elif tulos == "palautettu":
        tila, savy = "palautettu", ""
    else:
        tila, savy = "ei käytössä", ""
    osat = _diff(diff) if diff else None
    koot = {t["polku"]: t for t in tiedostot if t["polku"] is not None}
    muutokset = [m | {"koko_teksti": koot[m["polku"]]["koko_teksti"] if m["polku"] in koot and m["laji"] != "poistettu"
                      else None} for m in (osat["tiedostot"] if osat else [])]
    return {"versio": versio, "tehdas": versio == TEHDAS, "lyhyt": lyhyt(versio), "aika": _aika(v["aika"]),
            "kuka": v["kuka"], "tekija": TEKIJAT.get(v["kuka"], "tuntematon"), "teko": TEOT[tulos], "tulos": tulos,
            "tila": tila, "savy": savy, "kaytossa": on_kaytossa, "hylatty": hylatty,
            "syy": _rivi(v["syy"], SYY_MAX), "syy_tarkea": tulos in ("peruttu", "vahti", "virhe"),
            "tiedostot": tiedostot, "diff": diff, "diff_katkaistu": v["diff_katkaistu"],
            "varastossa": v["varastossa"], "diff_rivit": osat["rivit"] if osat else (),
            "diff_leikattu": bool(osat and osat["leikattu"]), "lisatty": osat["lisatty"] if osat else 0,
            "poistettu": osat["poistettu"] if osat else 0, "muutokset": muutokset,
            "muutokset_taydet": diff is not None and not v["diff_katkaistu"]}


def _versiot(arvo: Any, aktiivinen: dict[str, Any] | None) -> tuple[dict[str, Any] | None, ...]:
    if type(arvo) is not list or len(arvo) > VERSIOITA_MAX:
        _virhe("Versiolista ei kelpaa.")
    kaytossa = aktiivinen["versio"] if aktiivinen is not None else None
    nahty: set[str] = set()
    tulos: list[dict[str, Any] | None] = []
    for v in arvo:
        try:
            tulos.append(_versiorivi(v, kaytossa, nahty))
        except ReadFailure:
            tulos.append(None)   # vain tämä rivi piiloon
    return tuple(tulos)


def _pyynto(p: Any) -> dict[str, Any]:
    _olio(p, PYYNTO_KENTAT, "pyyntö")
    if p["id"] is not None and (type(p["id"]) is not str or _PYYNTO_ID.fullmatch(p["id"]) is None):
        _virhe("Pyynnön tunniste ei kelpaa.")
    if (p["toimi"] is not None and p["toimi"] not in TOIMET) or (p["kuka"] is not None and p["kuka"] not in PYYTAJAT):
        _virhe("Pyynnön toimi tai pyytäjä on tuntematon.")
    if p["tulos"] not in PYYNTO_TULOKSET:
        _virhe("Pyynnön tulos on tuntematon.")
    versio = _versio(p["versio"], tyhja=True)
    tulos, savy = PYYNTO_TULOKSET[p["tulos"]]
    return {"id": p["id"], "toimi": p["toimi"], "toimi_teksti": TOIMET.get(p["toimi"], "tuntematon pyyntö"),
            "kuka": p["kuka"], "tekija": TEKIJAT.get(p["kuka"], "tuntematon"),
            "pyydetty": _aika(p["pyydetty"], tyhja=True), "aika": _aika(p["aika"]), "tulos": p["tulos"],
            "tulos_teksti": tulos, "savy": savy, "syy": _rivi(p["syy"], SYY_MAX), "versio": versio}


def _pyynnot(arvo: Any) -> tuple[dict[str, Any] | None, ...]:
    if type(arvo) is not list or len(arvo) > PYYNTOJA_MAX:
        _virhe("Pyyntölista ei kelpaa.")
    tulos: list[dict[str, Any] | None] = []
    for p in arvo:
        try:
            tulos.append(_pyynto(p))
        except ReadFailure:
            tulos.append(None)
    return tuple(tulos)


def tarkista(data: Any) -> Aivot:
    """tila.json tarkoilla kentillä. Ylätason kentät, muoto ja aika ovat koko tiedoston ehto (ReadFailure); muut osat
    tarkistetaan erikseen, ja kelvoton osa on None (tai virhelippu), muu tila näytetään."""
    _olio(data, KENTAT, TIEDOSTO)
    if data["muoto"] != MUOTO:
        _virhe("Tuntematon muoto.")
    aika = _aika(data["aika"])
    lukittu = data["lukittu"] if type(data["lukittu"]) is bool else None

    def osa(lue, oletus=None):
        try:
            return lue(), False
        except ReadFailure:
            return oletus, True

    lukko, _ = osa(lambda: _lukko(lukittu, data["lukko"])) if lukittu is not None else (None, True)
    aktiivinen, _ = osa(lambda: _aktiivinen(data["aktiivinen"]))
    edellinen, edellinen_virhe = osa(lambda: _versio(data["edellinen"], tyhja=True))
    if edellinen == TEHDAS:          # asentaja ei kirjoita alkuperäistä edelliseksi (linkki poistetaan)
        edellinen, edellinen_virhe = None, True
    asennukset, _ = osa(lambda: _asennukset(data))
    vahti, vahti_virhe = osa(lambda: _vahti(data["vahti"]))
    versiot, _ = osa(lambda: _versiot(data["versiot"], aktiivinen))
    pyynnot, _ = osa(lambda: _pyynnot(data["pyynnot"]))
    return Aivot("ready", None, aika, lukittu, lukko, aktiivinen, edellinen, edellinen_virhe, asennukset,
                 _kesken(data["kesken"]), vahti, vahti_virhe, versiot, pyynnot)


EI_KAYTOSSA = "Itsepäivitys ei ole käytössä tällä koneella."


def lue_aivot(root: str | Path, *, omistajat: frozenset[int] | None = None, timeout_seconds: float = 2.0) -> Aivot:
    """omistajat=None vain kehitys- ja esimerkkitilassa; tuotannossa OMISTAJAT (root)."""
    try:
        kavelija = Hakemisto(root, timeout_seconds=timeout_seconds)
    except ValueError:
        return Aivot("error", "Polku ei ole sallittu.")
    deadline = time.monotonic() + timeout_seconds
    lukittu = None   # luetaan ennen muuta: lukko näkyy, vaikka tiedosto olisi muuten rikki
    try:
        with kavelija.juuri(deadline) as hd:
            if omistajat is not None and os.fstat(hd).st_uid not in omistajat:
                raise ReadFailure("wrong_owner", "Hakemiston omistaja on väärä.")
            tiedot = _stat(hd, TIEDOSTO, omistajat)
            if tiedot is None:
                return Aivot("not_published", EI_KAYTOSSA)
            raaka = _lue(hd, TIEDOSTO, tiedot.st_uid if omistajat is not None else None, deadline, RAJA)
        data = _jasenna(raaka)
        if isinstance(data, dict) and type(data.get("lukittu")) is bool:
            lukittu = data["lukittu"]
        return tarkista(data)
    except ReadFailure as error:
        if error.code == "not_found":
            return Aivot("not_published", EI_KAYTOSSA)
        return Aivot("error", "Aivojen tilaa ei voi lukea: " + VIESTIT.get(error.code, error.message), lukittu=lukittu)
    except OSError as error:
        return Aivot("error", f"Aivojen tilaa ei voi lukea ({error.strerror}).", lukittu=lukittu)
