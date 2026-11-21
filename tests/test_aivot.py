"""Aivojen koodi (aiops ADR-0033 pala 7): asentajan julkaiseman tila.json:n lukija.

Riippumaton totuus on alla käsin kirjoitettu tila samassa muodossa, jonka aiopsin asentaja kirjoittaa
(src/aiops/aivohuolto.py: kokoa_julkaisu ja sovita, muoto aiops-aivot-tila-v1). Lisäksi tiedosto
aivot_aiops_tila.json on asentajan oman koodin kirjoittama (aiops c35afda, valesystemd ja valekello: asennus, vahti,
lukon avaus, kaatunut asennus, syntaksivirhe ja uusi asennus), joten muodon muutos aiopsissa näkyy täällä.

Kielletty suunta: puuttuva tiedosto ei ole virhe (itsepäivitys ei käytössä); väärä omistaja, linkki, liian suuri tai
rikkinäinen tiedosto ja vieras ylätason kenttä ovat koko tiedoston virheitä, mutta lukko näkyy silti. Kelvoton osa
(lukko, käytössä oleva versio, raja, vahti, versio- tai pyyntörivi) piilottaa vain itsensä. Kielletty merkki
tekstissä (tiedostonimi, syy, diff) piilottaa vain sen kentän. Näkymättömät merkit rakennetaan chr():llä.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ilmari_ui import aivot
from ilmari_ui.aivot import Aivot, lue_aivot, tarkista

AIKA = "2026-11-21T11:30:00+02:00"
A_ID, B_ID, C_ID = "a1" * 32, "b2" * 32, "c3" * 32
DIFF = ("--- tehdas/ceo.py\n+++ uusi/ceo.py\n@@ -1,3 +1,3 @@\n import sys\n-X = 1\n+X = 2\n \n"
        "--- /dev/null\n+++ uusi/kyvyt.py\n@@ -0,0 +1 @@\n+KYVYT = ()\n"
        "--- tehdas/vanha.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-# vanha\n")
VERSIO_A = {"versio": A_ID, "aika": "2026-11-21T11:24:00+02:00", "kuka": "ilmari", "tulos": "asennettu",
            "syy": "terve (syke käynnistyksen jälkeen, sama prosessi 60 s)",
            "tiedostot": [{"polku": "ceo.py", "koko": 110}, {"polku": "kyvyt.py", "koko": 2048}],
            "diff": DIFF, "diff_katkaistu": False, "varastossa": True, "hylatty": False}
VERSIO_B = {"versio": B_ID, "aika": "2026-11-21T10:51:00+02:00", "kuka": "ilmari", "tulos": "peruttu",
            "syy": "uusi versio ei ollut terve: palvelu kaatui (failed); tehdasversio käytössä",
            "tiedostot": [{"polku": "ceo.py", "koko": 123}],
            "diff": "--- tehdas/ceo.py\n+++ uusi/ceo.py\n@@ -1 +1,2 @@\n X = 1\n+RIKKI = True\n",
            "diff_katkaistu": False, "varastossa": True, "hylatty": True}
PYYNTO = {"id": "5", "toimi": "asenna", "kuka": "ilmari", "pyydetty": "2026-11-21T11:24:00+02:00",
          "aika": "2026-11-21T11:25:00+02:00", "tulos": "asennettu", "syy": "terve", "versio": A_ID}
HYLATTY_PYYNTO = PYYNTO | {"id": "4", "tulos": "hylatty", "versio": "tehdas",
                           "syy": "ehdokas hylätty: syntaksivirhe: ceo.py rivi 1: invalid syntax"}
VAHTI = {"aika": "2026-11-21T10:31:00+02:00", "syy": "palvelu on kaatunut (failed)", "versio": C_ID,
         "toimi": "tehdasversio, hylkäys ja lukitus", "uudelleenkaynnistys": "ok"}


def tila(**muutos) -> dict:
    """Asentajan julkaisu (kokoa_julkaisu): Ilmarin versio A käytössä, edellinen C, kolme asennusta 24 tunnissa."""
    data = {"muoto": "aiops-aivot-tila-v1", "aika": AIKA,
            "aktiivinen": {"versio": A_ID, "aika": "2026-11-21T11:24:00+02:00", "kuka": "ilmari"},
            "edellinen": C_ID, "lukittu": False, "lukko": None, "asennuksia_24h": 3, "asennuksia_max": 6,
            "asennuksia_jaljella": 3, "asennukset_24h": ["2026-11-21T10:00:00+02:00", "2026-11-21T10:51:00+02:00",
                                                         "2026-11-21T11:24:00+02:00"],
            "seuraava_vapautuu": None, "kesken": None, "versiot": [VERSIO_A, VERSIO_B],
            "pyynnot": [PYYNTO, HYLATTY_PYYNTO], "vahti": VAHTI}
    return copy.deepcopy(data | muutos)


def kirjoita(hak: Path, data) -> Path:
    hak.mkdir(parents=True, exist_ok=True)
    raaka = data if isinstance(data, bytes) else (data if isinstance(data, str) else json.dumps(data)).encode("utf-8")
    (hak / "tila.json").write_bytes(raaka)
    return hak


def lue(tmp_path, data) -> Aivot:
    return lue_aivot(kirjoita(tmp_path / "aivot", data))


# --- Sallittu suunta ---------------------------------------------------------------------------------------------

def test_kelvollinen_tila_luetaan(tmp_path):
    a = lue(tmp_path, tila())
    assert a.tila == "ready" and a.viesti is None and a.aika == AIKA
    assert a.lukittu is False and a.lukko is None
    assert a.aktiivinen == {"versio": A_ID, "tehdas": False, "lyhyt": "a1a1a1a1a1a1", "aika": "2026-11-21T11:24:00+02:00",
                            "kuka": "ilmari"}
    assert a.edellinen == C_ID and a.edellinen_virhe is False and a.kesken is None
    assert a.asennukset == {"tehty": 3, "max": 6, "jaljella": 3, "seuraava": None}
    assert a.vahti == {"aika": VAHTI["aika"], "syy": "palvelu on kaatunut (failed)", "versio": C_ID,
                       "lyhyt": "c3c3c3c3c3c3", "toimi": "otti alkuperäisen käyttöön, hylkäsi version ja lukitsi",
                       "uudelleenkaynnistys": "ok", "uudelleen_ok": True}
    v, b = a.versiot
    assert (v["tila"], v["savy"], v["kaytossa"], v["teko"], v["tekija"], v["syy_tarkea"]) == (
        "käytössä", "ok", True, "asennus", "Ilmari", False)
    assert [(m["polku"], m["laji"], m["koko_teksti"], m["lisatty"], m["poistettu"]) for m in v["muutokset"]] == [
        ("ceo.py", "muutettu", "110 tavua", 1, 1), ("kyvyt.py", "uusi", "2,0 kt", 1, 0),
        ("vanha.md", "poistettu", None, 0, 1)]
    assert v["muutokset_taydet"] is True and (v["lisatty"], v["poistettu"]) == (2, 2)
    assert [laji for laji, _ in v["diff_rivit"]] == ["meta", "meta", "hunk", "ctx", "del", "add", "ctx", "meta", "meta",
                                                    "hunk", "add", "meta", "meta", "hunk", "del"]
    assert (b["tila"], b["savy"], b["hylatty"], b["syy_tarkea"], b["kaytossa"]) == ("hylätty", "stop", True, True, False)
    assert [(p["tekija"], p["toimi_teksti"], p["tulos_teksti"], p["savy"]) for p in a.pyynnot] == [
        ("Ilmari", "asenna", "asennettu", "ok"), ("Ilmari", "asenna", "hylätty", "stop")]
    assert a.pyynnot[1]["syy"] == "ehdokas hylätty: syntaksivirhe: ceo.py rivi 1: invalid syntax"


def test_asentajan_kirjoittama_tiedosto_kelpaa(tmp_path):
    """aivot_aiops_tila.json on aiopsin asentajan kirjoittama (tavut sellaisinaan)."""
    a = lue(tmp_path, (Path(__file__).parent / "aivot_aiops_tila.json").read_bytes())
    assert a.tila == "ready" and a.lukittu is False and a.lukko is None and a.kesken is None
    assert not a.aktiivinen["tehdas"] and a.edellinen and a.asennukset["jaljella"] == 3
    assert a.vahti["syy"] == "palvelu on kaatunut (failed)" and a.vahti["uudelleen_ok"]
    assert None not in a.versiot and None not in a.pyynnot
    assert [(v["tila"], v["teko"]) for v in a.versiot] == [
        ("käytössä", "asennus"), ("hylätty", "asennus"), ("edellinen", "asennus"), ("hylätty", "vahti poisti käytöstä"),
        ("hylätty myöhemmin", "asennus")]
    assert all(v["syy"] and v["diff"] and v["muutokset_taydet"] and v["muutokset"] for v in a.versiot)
    assert [p["tulos"] for p in a.pyynnot] == ["asennettu", "hylatty", "peruttu", "asennettu", "avattu", "asennettu"]


def test_esimerkkiaineisto_kelpaa():
    a = lue_aivot(aivot.ESIMERKKI)
    assert a.tila == "ready" and a.lukittu is False and a.edellinen and a.kesken is None and a.vahti
    assert None not in a.versiot and None not in a.pyynnot
    asennettu, hylatty = a.versiot[0], a.versiot[1]
    assert asennettu["kaytossa"] and asennettu["diff_katkaistu"] and not asennettu["muutokset_taydet"]
    assert asennettu["diff_rivit"][-1] == ("hunk", "[diff katkaistu: yli 64 KiB]")
    assert hylatty["tila"] == "hylätty" and hylatty["syy"].startswith("uusi versio ei ollut terve")
    assert any(p["tulos"] == "hylatty" and "syntaksivirhe" in p["syy"] for p in a.pyynnot)


def test_puuttuva_tiedosto_tai_hakemisto_ei_ole_virhe(tmp_path):
    (tmp_path / "tyhja").mkdir()
    for hak in (tmp_path / "tyhja", tmp_path / "eiole"):
        assert lue_aivot(hak) == Aivot("not_published", "Itsepäivitys ei ole käytössä tällä koneella.")
    assert lue_aivot("suhteellinen/polku").tila == "error"


def test_omistaja_kelpaa_tuotannossa(tmp_path, oletuspolut):
    assert lue_aivot(kirjoita(tmp_path / "a", tila()), omistajat=frozenset({os.getuid()})).tila == "ready"
    assert aivot.OMISTAJAT == frozenset({0}) and str(oletuspolut["aivot.OLETUS"]) == "/srv/aiops/ilmari/aivot"


def test_alkuperainen_kaytossa_lukittuna_ja_kesken(tmp_path):
    lukko = {"aika": "2026-11-21T10:31:00+02:00", "kuka": "vahti", "syy": "palvelu on kaatunut (failed)"}
    a = lue(tmp_path, tila(aktiivinen={"versio": "tehdas", "aika": None, "kuka": None}, edellinen=None, lukittu=True,
                           lukko=lukko, kesken={"toimi": "asenna", "versio": B_ID, "aika": AIKA},
                           asennuksia_24h=6, asennuksia_jaljella=0, seuraava_vapautuu="2026-11-22T10:00:00+02:00",
                           asennukset_24h=[AIKA] * 6))
    assert a.aktiivinen["tehdas"] and a.aktiivinen["lyhyt"] == "tehdas" and a.edellinen is None
    assert a.lukittu is True and a.lukko == lukko | {"tekija": "vahti"}
    assert a.kesken == {"toimi": "asenna", "teksti": "asennus", "versio": B_ID, "lyhyt": "b2b2b2b2b2b2", "aika": AIKA}
    assert a.asennukset == {"tehty": 6, "max": 6, "jaljella": 0, "seuraava": "2026-11-22T10:00:00+02:00"}
    assert [v["kaytossa"] for v in a.versiot] == [False, False]   # alkuperäinen käytössä: mikään versio ei ole


def test_vain_uusin_rivi_samasta_versiosta_on_kaytossa(tmp_path):
    palautus = VERSIO_A | {"aika": "2026-11-21T12:00:00+02:00", "kuka": "elias", "tulos": "palautettu"}
    tehdas = {"versio": "tehdas", "aika": "2026-11-21T09:00:00+02:00", "kuka": "elias", "tulos": "palautettu",
              "syy": "tehdasversio käytössä", "tiedostot": [], "diff": "", "diff_katkaistu": False,
              "varastossa": False, "hylatty": False}
    a = lue(tmp_path, tila(versiot=[palautus, VERSIO_A, tehdas]))
    assert [(v["tila"], v["tekija"], v["teko"]) for v in a.versiot] == [
        ("käytössä", "Elias", "palautus"), ("ei käytössä", "Ilmari", "asennus"), ("palautettu", "Elias", "palautus")]
    assert a.versiot[2]["tehdas"] and a.versiot[2]["diff_rivit"] == () and a.versiot[2]["muutokset"] == []


def test_edellinen_merkitaan_vain_uusimmalle_rivilleen(tmp_path):
    """Versio, jonka Palauta edellinen toisi takaisin, on "edellinen" uusimmalla rivillään; hylättyä ei merkitä."""
    vanhempi = VERSIO_A | {"versio": C_ID, "aika": "2026-11-21T09:00:00+02:00"}
    uudempi = vanhempi | {"aika": "2026-11-21T10:00:00+02:00", "kuka": "elias", "tulos": "palautettu"}
    a = lue(tmp_path, tila(versiot=[VERSIO_A, uudempi, vanhempi]))
    assert [v["tila"] for v in a.versiot] == ["käytössä", "edellinen", "ei käytössä"]
    a = lue(tmp_path, tila(edellinen=B_ID, versiot=[VERSIO_A, VERSIO_B, vanhempi]))
    assert [v["tila"] for v in a.versiot] == ["käytössä", "hylätty", "ei käytössä"]
    a = lue(tmp_path, tila(edellinen=None, versiot=[VERSIO_A, vanhempi]))
    assert [v["tila"] for v in a.versiot] == ["käytössä", "ei käytössä"]


def test_kelvoton_uusin_rivi_ei_vie_merkintaa(tmp_path):
    """Käytössä olevan version uusin rivi on kelvoton (aika): se piilotetaan, ja seuraava rivi on käytössä."""
    a = lue(tmp_path, tila(versiot=[VERSIO_A | {"aika": "eilen"}, VERSIO_A | {"syy": 5}, VERSIO_A]))
    assert a.versiot[:2] == (None, None) and a.versiot[2]["tila"] == "käytössä"


def test_katkaistu_ja_karsittu_diff(tmp_path):
    katkaistu = VERSIO_A | {"diff": DIFF[:60] + "\n[diff katkaistu: yli 64 KiB]\n", "diff_katkaistu": True}
    karsittu = VERSIO_A | {"versio": B_ID, "diff": "", "diff_katkaistu": True}     # julkaisu ei mahtunut 512 KiB:hen
    a = lue(tmp_path, tila(versiot=[katkaistu, karsittu]))
    k, r = a.versiot
    assert k["muutokset_taydet"] is False and k["diff_rivit"][-1] == ("hunk", "[diff katkaistu: yli 64 KiB]")
    assert [m["polku"] for m in k["muutokset"]] == ["ceo.py"]
    assert r["diff_rivit"] == () and r["muutokset"] == [] and r["muutokset_taydet"] is False and len(r["tiedostot"]) == 2


def test_diffin_sisaltorivi_ei_ole_otsake(tmp_path):
    """Poistettu rivi "-- x" ja lisätty "++ y" näyttävät otsakkeilta, mutta hunkin rivimäärä ratkaisee."""
    diff = "--- tehdas/a.md\n+++ uusi/a.md\n@@ -1,2 +1,2 @@\n--- x\n+++ y\n ok\n"
    v = lue(tmp_path, tila(versiot=[VERSIO_A | {"diff": diff}])).versiot[0]
    assert [laji for laji, _ in v["diff_rivit"]] == ["meta", "meta", "hunk", "del", "add", "ctx"]
    assert [(m["polku"], m["lisatty"], m["poistettu"]) for m in v["muutokset"]] == [("a.md", 1, 1)]


def test_pitka_diff_leikataan_sivulla(tmp_path, monkeypatch):
    monkeypatch.setattr(aivot, "DIFF_RIVEJA_NAYTA", 5)
    v = lue(tmp_path, tila()).versiot[0]
    assert len(v["diff_rivit"]) == 5 and v["diff_leikattu"] is True and v["lisatty"] == 2   # luvut koko diffistä


def test_hylatty_edellinen_merkitaan(tmp_path):
    """Asentaja ei palauta hylättyyn versioon, joten sivu ei tarjoa sitä: edellinen_hylatty, kun versiolistassa sama
    versio on hylätty. Tuntematon (lista ei ulotu) tai hylkäämätön edellinen ei ole hylätty."""
    assert lue(tmp_path, tila(edellinen=B_ID)).edellinen_hylatty is True
    for edellinen, versiot in ((C_ID, [VERSIO_A, VERSIO_B]), (A_ID, [VERSIO_A]), (None, [VERSIO_B]),
                               (B_ID, {}), (B_ID, [VERSIO_B | {"tulos": "?"}])):
        a = lue(tmp_path, tila(edellinen=edellinen, versiot=versiot))
        assert a.tila == "ready" and a.edellinen == edellinen and a.edellinen_hylatty is False


def test_diffin_tyhjat_kirjaimet_naytetaan_koodeina(tmp_path):
    """Näkymätön nimi (hangulin täytemerkki kelpaa Pythonissa nimeksi) näkyy diffissä koodina eikä tyhjänä."""
    tyhja = chr(0x3164)
    diff = DIFF.replace("+X = 2\n", f"+{tyhja} = __import__('os')\n+X = {tyhja}{chr(0x2800)}\n")
    v = lue(tmp_path, tila(versiot=[VERSIO_A | {"diff": diff}])).versiot[0]
    assert tyhja not in v["diff"] and chr(0x2800) not in v["diff"]
    assert "+\\u3164 = __import__('os')\n+X = \\u3164\\u2800\n" in v["diff"]
    assert ("add", "+\\u3164 = __import__('os')") in v["diff_rivit"] and v["lisatty"] == 3
    assert aivot.nakyviksi("ääkköset ja " + "\U0001F469" + chr(0x200D) + "\U0001F4BB") == (
        "ääkköset ja " + "\U0001F469" + chr(0x200D) + "\U0001F4BB")


def test_vanha_tila():
    """Yli 10 min vanha julkaisu: huolto ei ole käynnissä. Raja molempiin suuntiin; luku ilman aikaa ei ole vanha."""
    a = tarkista(tila())
    nyt = datetime.fromisoformat(AIKA)
    assert not aivot.vanha(a, nyt) and not aivot.vanha(a, nyt + timedelta(minutes=10))
    assert aivot.vanha(a, nyt + timedelta(minutes=10, seconds=1)) and aivot.vanha(a, nyt + timedelta(days=3))
    assert not aivot.vanha(a, nyt - timedelta(days=1))            # kello jäljessä: ei hälytystä
    for muu in (Aivot("not_published", aivot.EI_KAYTOSSA), Aivot("error", "x", lukittu=True)):
        assert not aivot.vanha(muu, nyt + timedelta(days=3))


def test_koko_teksti():
    assert [aivot.koko_teksti(n) for n in (0, 1023, 1024, 94100)] == ["0 tavua", "1023 tavua", "1,0 kt", "91,9 kt"]


# --- Kielletty suunta: koko tiedosto -----------------------------------------------------------------------------

def ilman(kentta: str) -> dict:
    return {k: v for k, v in tila().items() if k != kentta}


HUONOT_TIEDOSTOT = [
    tila(muoto="aiops-aivot-tila-v2"), tila(muoto=None), tila(vieras=1), ilman("versiot"), ilman("muoto"),
    tila(aika="2026-11-21T11:30:00"), tila(aika=None), tila(aika="0001-01-01T00:30:00+01:00"), [tila()], "tila",
]


@pytest.mark.parametrize("data", HUONOT_TIEDOSTOT)
def test_kelvoton_tiedosto_hylataan(tmp_path, data):
    a = lue(tmp_path, data)
    assert a.tila == "error" and a.viesti.startswith("Aivojen tilaa ei voi lukea: ")
    assert a.versiot == () and a.aktiivinen is None and "/" not in a.viesti


@pytest.mark.parametrize("raaka", [b"{rikki", b"[]", b'{"muoto": 1, "muoto": 1}', b'{"lukittu": NaN}', b"\xff",
                                   b"[" * 100_000])
def test_rikkinainen_json_hylataan(tmp_path, raaka):
    assert lue(tmp_path, raaka).tila == "error"


def test_lukko_nakyy_vaikka_tiedosto_on_rikki(tmp_path):
    a = lue(tmp_path, tila(vieras=1, lukittu=True))
    assert a.tila == "error" and a.lukittu is True
    assert lue(tmp_path, tila(muoto="x", lukittu=False)).lukittu is False
    assert lue(tmp_path, tila(muoto="x", lukittu="true")).lukittu is None


def test_vaara_omistaja_linkki_ja_liian_suuri_hylataan(tmp_path, monkeypatch):
    hak = kirjoita(tmp_path / "a", tila())
    a = lue_aivot(hak, omistajat=frozenset({os.getuid() + 1}))
    assert a.tila == "error" and "omistaja" in a.viesti
    linkki = tmp_path / "linkki"
    linkki.mkdir()
    (linkki / "tila.json").symlink_to(hak / "tila.json")
    assert lue_aivot(linkki).tila == "error"
    (tmp_path / "hakemistolinkki").symlink_to(hak)
    assert lue_aivot(tmp_path / "hakemistolinkki").tila == "error"
    assert aivot.RAJA == 512 * 1024
    monkeypatch.setattr(aivot, "RAJA", 100)
    a = lue_aivot(hak)
    assert a.tila == "error" and "lukurajan" in a.viesti
    monkeypatch.setattr(aivot, "RAJA", 512 * 1024)
    kova = tmp_path / "kova"
    kova.mkdir()
    os.link(hak / "tila.json", kova / "tila.json")                        # kaksi nimeä samalle tiedostolle
    assert lue_aivot(kova).tila == "error"


# --- Kielletty suunta: osa piilottaa vain itsensä ----------------------------------------------------------------

OSAT = [
    ("aktiivinen", {"versio": "x" * 64, "aika": None, "kuka": None}, lambda a: a.aktiivinen is None),
    ("aktiivinen", {"versio": A_ID, "aika": None, "kuka": "joku"}, lambda a: a.aktiivinen is None),
    ("aktiivinen", {"versio": A_ID.upper(), "aika": None, "kuka": None}, lambda a: a.aktiivinen is None),
    ("aktiivinen", {"versio": A_ID, "aika": None}, lambda a: a.aktiivinen is None),
    ("edellinen", "versiot/" + A_ID, lambda a: a.edellinen is None and a.edellinen_virhe),
    ("edellinen", "tehdas", lambda a: a.edellinen is None and a.edellinen_virhe),
    ("lukko", {"aika": AIKA, "kuka": "elias", "syy": "x"}, lambda a: a.lukittu is False and a.lukko is None),
    ("asennuksia_jaljella", 4, lambda a: a.asennukset is None),
    ("asennuksia_24h", -1, lambda a: a.asennukset is None),
    ("asennuksia_max", 0, lambda a: a.asennukset is None),
    ("asennukset_24h", ["eilen", AIKA, AIKA], lambda a: a.asennukset is None),
    ("asennukset_24h", [AIKA], lambda a: a.asennukset is None),
    ("seuraava_vapautuu", "huomenna", lambda a: a.asennukset is None),
    ("vahti", {"aika": AIKA, "syy": "x"}, lambda a: a.vahti is None and a.vahti_virhe),
    ("vahti", VAHTI | {"aika": None}, lambda a: a.vahti is None and a.vahti_virhe),
    ("vahti", VAHTI | {"versio": "abc"}, lambda a: a.vahti is None and a.vahti_virhe),
    ("versiot", {}, lambda a: a.versiot is None),
    ("versiot", [VERSIO_A] * (aivot.VERSIOITA_MAX + 1), lambda a: a.versiot is None),
    ("pyynnot", None, lambda a: a.pyynnot is None),
    ("pyynnot", [PYYNTO] * (aivot.PYYNTOJA_MAX + 1), lambda a: a.pyynnot is None),
]


@pytest.mark.parametrize("kentta,arvo,ehto", OSAT, ids=[f"{k}-{i}" for i, (k, _, _) in enumerate(OSAT)])
def test_kelvoton_osa_piilottaa_vain_itsensa(tmp_path, kentta, arvo, ehto):
    a = lue(tmp_path, tila(**{kentta: arvo}))
    assert a.tila == "ready" and ehto(a)
    if kentta != "versiot":
        assert a.versiot[0]["versio"] == A_ID and a.versiot[1]["hylatty"]
    if kentta != "lukko":
        assert a.lukittu is False


def test_kelvoton_kesken_on_silti_kesken(tmp_path):
    for k in ({"toimi": "poista_kaikki", "versio": None, "aika": None}, {"toimi": "asenna"}, "kyllä", [],
              {"toimi": "asenna", "versio": "x", "aika": AIKA}):
        a = lue(tmp_path, tila(kesken=k))
        assert a.tila == "ready" and a.kesken == aivot.KESKEN_TUNTEMATON


HUONOT_VERSIOT = [
    VERSIO_A | {"vieras": 1}, {k: v for k, v in VERSIO_A.items() if k != "diff"}, VERSIO_A | {"versio": "x"},
    VERSIO_A | {"versio": None}, VERSIO_A | {"kuka": "root"}, VERSIO_A | {"tulos": "hylatty"},
    VERSIO_A | {"tulos": None}, VERSIO_A | {"hylatty": 1}, VERSIO_A | {"varastossa": None},
    VERSIO_A | {"diff_katkaistu": "false"}, VERSIO_A | {"aika": "eilen"}, VERSIO_A | {"syy": None},
    VERSIO_A | {"syy": "x" * (aivot.SYY_MAX + 1)}, VERSIO_A | {"diff": None},
    VERSIO_A | {"diff": "x" * (aivot.DIFF_MAX + 1)}, VERSIO_A | {"tiedostot": {}},
    VERSIO_A | {"tiedostot": [{"polku": "ceo.py"}]}, VERSIO_A | {"tiedostot": [{"polku": "ceo.py", "koko": -1}]},
    VERSIO_A | {"tiedostot": [{"polku": "ceo.py", "koko": True}]}, VERSIO_A | {"tiedostot": [{"polku": None, "koko": 1}]},
    VERSIO_A | {"tiedostot": [{"polku": "x", "koko": aivot.KOKO_MAX + 1}]},
    VERSIO_A | {"tiedostot": [{"polku": "x", "koko": 1}] * (aivot.TIEDOSTOJA_MAX + 1)}, "versio", None,
]


@pytest.mark.parametrize("huono", HUONOT_VERSIOT, ids=range(len(HUONOT_VERSIOT)))
def test_kelvoton_versiorivi_piilottaa_vain_itsensa(tmp_path, huono):
    a = lue(tmp_path, tila(versiot=[huono, VERSIO_B]))
    assert a.tila == "ready" and a.versiot[0] is None and a.versiot[1]["versio"] == B_ID
    assert a.aktiivinen["versio"] == A_ID and a.lukittu is False and len(a.pyynnot) == 2


HUONOT_PYYNNOT = [
    PYYNTO | {"vieras": 1}, PYYNTO | {"id": 5}, PYYNTO | {"id": "5a"}, PYYNTO | {"id": "1" * 19},
    PYYNTO | {"toimi": "rm"}, PYYNTO | {"kuka": "root"}, PYYNTO | {"tulos": "ok"}, PYYNTO | {"aika": None},
    PYYNTO | {"pyydetty": "eilen"}, PYYNTO | {"versio": "abc"}, PYYNTO | {"syy": None}, [],
]


@pytest.mark.parametrize("huono", HUONOT_PYYNNOT, ids=range(len(HUONOT_PYYNNOT)))
def test_kelvoton_pyynto_piilottaa_vain_itsensa(tmp_path, huono):
    a = lue(tmp_path, tila(pyynnot=[huono, HYLATTY_PYYNTO]))
    assert a.tila == "ready" and a.pyynnot[0] is None and a.pyynnot[1]["tulos"] == "hylatty"


def test_vahdin_kirjaama_pyynto_kelpaa():
    """Keskeytyneen toimen loppuunvienti voi kirjata pyytäjäksi vahdin."""
    p = tarkista(tila(pyynnot=[PYYNTO | {"kuka": "vahti", "tulos": "palautettu"}])).pyynnot[0]
    assert (p["tekija"], p["tulos_teksti"]) == ("vahti", "palautettu")


def test_tuntematon_pyynto_kelpaa():
    """Asentaja vastaa myös kelvottomaan pyyntöön: id, toimi ja kuka voivat puuttua."""
    rivi = PYYNTO | {"id": None, "toimi": None, "kuka": None, "pyydetty": None, "tulos": "virhe",
                     "syy": "tuntematon pyyntö abc.json poistettu"}
    p = tarkista(tila(pyynnot=[rivi])).pyynnot[0]
    assert (p["tekija"], p["toimi_teksti"], p["tulos_teksti"], p["savy"]) == ("tuntematon", "tuntematon pyyntö", "virhe",
                                                                                "stop")


# --- Kielletty merkki piilottaa vain kentän ----------------------------------------------------------------------

YKSIRIVISET_HUONOT = ["kaksi\nriviä", "suunta" + chr(0x202E) + "käännetty", "a" + chr(0x2067) + "b",
                      "merkki" + chr(0x200F), "a" + chr(0x1B) + "[31m", "a" + chr(9) + "b", "a" + chr(0x7F),
                      "a" + chr(0x9B) + "b", "a" + chr(0x200B) + "b", "a" + chr(0x2028) + "b", "a" + chr(0xDC00),
                      chr(0x3164) * 3, "a" + chr(0x2800) + "b", "a" + chr(0xFEFF), "a" + chr(0xAD) + "b"]
MONIRIVISET_HUONOT = ["+a" + chr(0x202E) + "b\n", "+a" + chr(0x0) + "\n", "+" + chr(0x2029) + "\n", "+x" + chr(0x200B) + "\n",
                      "+" + chr(0xD800) + "\n", "+a" + chr(0x1B) + "]8;;http://x" + chr(0x7) + "\n"]


def merkki_id(teksti: str) -> str:
    return "-".join(f"{ord(c):04X}" for c in teksti if not c.isalnum()) or "x"


@pytest.mark.parametrize("huono", YKSIRIVISET_HUONOT, ids=merkki_id)
def test_kielletty_merkki_piilottaa_vain_kentan(tmp_path, huono):
    tiedostot = [{"polku": "ok.py", "koko": 1}, {"polku": "x" + huono, "koko": 2}]
    a = lue(tmp_path, tila(versiot=[VERSIO_A | {"syy": huono, "tiedostot": tiedostot}, VERSIO_B],
                           pyynnot=[PYYNTO | {"syy": huono}], vahti=VAHTI | {"syy": huono, "toimi": huono},
                           lukittu=True, lukko={"aika": AIKA, "kuka": "vahti", "syy": huono}))
    assert a.tila == "ready"
    v = a.versiot[0]
    assert v["syy"] is None and [t["polku"] for t in v["tiedostot"]] == ["ok.py", None] and v["diff"] == DIFF
    assert v["kaytossa"] and v["muutokset"] and a.versiot[1]["syy"] == VERSIO_B["syy"]
    assert a.pyynnot[0]["syy"] is None and a.pyynnot[0]["tulos"] == "asennettu"
    assert a.vahti["syy"] is None and a.vahti["toimi"] is None and a.vahti["aika"] == VAHTI["aika"]
    assert a.lukittu is True and a.lukko["syy"] is None and a.lukko["kuka"] == "vahti"


@pytest.mark.parametrize("huono", MONIRIVISET_HUONOT, ids=merkki_id)
def test_kielletty_merkki_diffissa_piilottaa_vain_diffin(tmp_path, huono):
    diff = DIFF.replace("+X = 2\n", huono)
    v = lue(tmp_path, tila(versiot=[VERSIO_A | {"diff": diff}])).versiot[0]
    assert v["diff"] is None and v["diff_rivit"] == () and v["muutokset"] == [] and v["muutokset_taydet"] is False
    assert v["kaytossa"] and v["syy"] == VERSIO_A["syy"] and [t["polku"] for t in v["tiedostot"]] == ["ceo.py", "kyvyt.py"]


def test_sallitut_merkit_kelpaavat(tmp_path):
    """Sarkain ja rivinvaihto diffissä, emojin ZWJ, ääkköset ja asentajan näkyviksi muuttamat koodit kelpaavat."""
    diff = DIFF.replace("+X = 2\n", "+X = 2\t# ok " + "\U0001F469" + chr(0x200D) + "\U0001F4BB" + " \\u202e\n")
    syy = "ehdokas hylätty: nimi ei kelpaa: x\\u202e.py (sallittu [a-z_]) " + "\U0001F469" + chr(0x200D) + "\U0001F4BB"
    a = lue(tmp_path, tila(versiot=[VERSIO_A | {"diff": diff, "syy": syy}]))
    assert a.versiot[0]["diff"] == diff and a.versiot[0]["syy"] == syy


def test_tarkistus_ei_paasta_lapi_vierasta():
    a = tarkista(tila())
    assert set(a.aktiivinen) == {"versio", "tehdas", "lyhyt", "aika", "kuka"}
    assert set(a.versiot[0]["tiedostot"][0]) == {"polku", "koko", "koko_teksti"}
    with pytest.raises(aivot.ReadFailure):
        tarkista(tila(ylimaarainen={"x": 1}))
