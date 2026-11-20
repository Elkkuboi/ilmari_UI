"""Promptit ja säännöt (aiops 21.11.2026): gatewayn julkaiseman luettelon lukija.

Riippumaton totuus on alla käsin kirjoitettu luettelo samassa muodossa, jossa aiopsin gateway sen kirjoittaa
(src/aiops/gateway/kehotteet.py: KENTAT). Kielletty suunta: vieras tai puuttuva kenttä, väärä tyyppi, liian pitkä
tai ohjausmerkkejä sisältävä teksti, toistuva tunniste, kiinteä teksti muokattuna esitettynä, väärä omistaja, linkki
ja liian suuri tiedosto.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from ilmari_ui import kehotteet, toiminta
from ilmari_ui.kehotteet import Kehotteet, etsi, korkeus, lue_kehotteet, ryhmittain, tarkista

AIKA = "2026-11-21T01:10:00+02:00"
RIVI = {"tunniste": "jarjestelma", "ryhma": "Ilmari", "otsikko": "Systemprompti", "kuvaus": "Ilmarin perusohje.",
        "lahde": "src/aiops/ceo_masterprompt.md", "teksti": "Olet Ilmari.\nTee työt itse.", "oletus": None,
        "muokattu": None, "muokattava": True, "enint": 6000}
KIINTEA = RIVI | {"tunniste": "tyokalut", "otsikko": "Työkalut", "teksti": "aja\nTee työ.", "muokattava": False}
KADET = RIVI | {"tunniste": "tyon_alku", "ryhma": "Ilmarin kädet", "otsikko": "Työn alku", "muokattava": False}
MUOKATTU = RIVI | {"teksti": "Olet Ilmari. Vastaa lyhyesti.", "oletus": "Olet Ilmari.\nTee työt itse.", "muokattu": AIKA}


def luettelo(*rivit: dict, **muutos) -> dict:
    return {"versio": 1, "aika": AIKA, "kehotteet": [copy.deepcopy(r) for r in (rivit or (RIVI, KIINTEA, KADET))]} | muutos


def kirjoita(hak: Path, data) -> Path:
    hak.mkdir(parents=True, exist_ok=True)
    (hak / "kehotteet.json").write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
                                        encoding="utf-8")
    return hak


# --- Sallittu suunta ---------------------------------------------------------------------------------------------

def test_luettelo_luetaan_ja_ryhmitellaan(tmp_path):
    k = lue_kehotteet(kirjoita(tmp_path / "t", luettelo(MUOKATTU, KIINTEA, KADET)))
    assert k.tila == "ready" and k.aika == AIKA and [r["tunniste"] for r in k.kehotteet] == ["jarjestelma", "tyokalut",
                                                                                           "tyon_alku"]
    assert k.kehotteet[0] == MUOKATTU and k.kehotteet[1] == KIINTEA
    assert [(nimi, [r["tunniste"] for r in rivit]) for nimi, rivit in ryhmittain(k)] == [
        ("Ilmari", ["jarjestelma", "tyokalut"]), ("Ilmarin kädet", ["tyon_alku"])]
    assert etsi(k, "tyon_alku")["otsikko"] == "Työn alku"
    assert etsi(k, "eiole") is None and etsi(k, "ISO") is None and etsi(k, "../x") is None


def test_esimerkkiaineisto_kelpaa():
    k = lue_kehotteet(toiminta.ESIMERKKI)
    assert k.tila == "ready" and [r["tunniste"] for r in k.kehotteet] == ["jarjestelma", "vuoro", "tyokalut", "tyon_alku"]
    assert k.kehotteet[0]["muokattu"] and k.kehotteet[0]["oletus"] and not k.kehotteet[1]["muokattu"]


def test_omistaja_kelpaa_tuotannossa(tmp_path):
    hak = kirjoita(tmp_path / "t", luettelo())
    assert lue_kehotteet(hak, omistajat=frozenset({os.getuid()})).tila == "ready"


def test_muokkauskentan_korkeus():
    assert korkeus("lyhyt") == kehotteet.RIVEJA_MIN
    assert korkeus("\n".join("x" * 10 for _ in range(15))) == 17          # 15 riviä + 2
    assert korkeus("x" * 600) == 12                                       # yksi pitkä rivi rivittyy kymmeneksi
    assert korkeus("\n" * 500) == kehotteet.RIVEJA_MAX


# --- Kielletty suunta --------------------------------------------------------------------------------------------

def rivi(**muutos) -> dict:
    return luettelo(RIVI | muutos)


HUONOT = [
    luettelo(versio=2), luettelo(ylimaarainen=1), luettelo(aika="2026-11-21T01:10:00"), luettelo(aika=None),
    {"versio": 1, "aika": AIKA}, {"versio": 1, "aika": AIKA, "kehotteet": []}, {"versio": 1, "aika": AIKA, "kehotteet": {}},
    luettelo(*[RIVI | {"tunniste": f"k{n}"} for n in range(kehotteet.MAARA_MAX + 1)]),
    luettelo(RIVI, RIVI),                                                  # sama tunniste kahdesti
    luettelo({k: v for k, v in RIVI.items() if k != "lahde"}), luettelo(RIVI | {"vieras": 1}), luettelo("rivi"),
    rivi(tunniste="Iso"), rivi(tunniste="../x"), rivi(tunniste=""), rivi(tunniste=5), rivi(tunniste="a" * 41),
    rivi(muokattava="true"), rivi(muokattava=1), rivi(enint=0), rivi(enint=True), rivi(enint="6000"),
    rivi(enint=kehotteet.ENINT_MAX + 1),
    rivi(teksti=""), rivi(teksti="  \n "), rivi(teksti=None), rivi(teksti=["x"]),
    rivi(teksti="x" * (kehotteet.TEKSTI_MAX + 1)), rivi(teksti="a\x1bb"), rivi(teksti="suunta\u202ekäännetty"),
    rivi(otsikko=""), rivi(otsikko="x" * 81), rivi(otsikko="kaksi\nriviä"), rivi(kuvaus="x" * 401), rivi(kuvaus=None),
    rivi(ryhma=""), rivi(ryhma="x" * 61), rivi(ryhma="a\nb"), rivi(lahde=""), rivi(lahde="x" * 201),
    rivi(oletus="Olet Ilmari."),                                           # oletus ilman muokkausaikaa
    rivi(muokattu=AIKA),                                                   # muokkausaika ilman oletusta
    rivi(oletus="x", muokattu="eilen"), rivi(oletus="", muokattu=AIKA), rivi(oletus="a\x00b", muokattu=AIKA),
    luettelo(KIINTEA | {"oletus": "aja", "muokattu": AIKA}),               # kiinteä teksti ei voi olla muokattu
]


@pytest.mark.parametrize("data", HUONOT)
def test_kelvoton_luettelo_hylataan(tmp_path, data):
    k = lue_kehotteet(kirjoita(tmp_path / "t", data))
    assert k.tila == "error" and k.viesti and k.kehotteet == ()
    assert "/" not in k.viesti and str(tmp_path) not in k.viesti           # ei polkuja virheilmoituksessa


@pytest.mark.parametrize("raaka", ["{rikki", "[]", '{"versio": 1, "versio": 1, "aika": null, "kehotteet": []}',
                                   '{"versio": NaN, "aika": "x", "kehotteet": []}', "\xff"])
def test_rikkinainen_json_hylataan(tmp_path, raaka):
    hak = tmp_path / "t"
    hak.mkdir()
    (hak / "kehotteet.json").write_bytes(raaka.encode("latin-1"))
    assert lue_kehotteet(hak).tila == "error"


def test_puuttuva_tiedosto_tai_hakemisto_on_julkaisematon(tmp_path):
    (tmp_path / "tyhja").mkdir()
    for hak in (tmp_path / "tyhja", tmp_path / "eiole"):
        k = lue_kehotteet(hak)
        assert k == Kehotteet("not_published", "Prompteja ei ole vielä tallennettu.")
    assert lue_kehotteet("suhteellinen/polku").tila == "error"


def test_vaara_omistaja_linkki_ja_liian_suuri_hylataan(tmp_path, monkeypatch):
    hak = kirjoita(tmp_path / "t", luettelo())
    k = lue_kehotteet(hak, omistajat=frozenset({os.getuid() + 1}))
    assert k.tila == "error" and "omistaja" in k.viesti
    linkki = tmp_path / "linkki"
    linkki.mkdir()
    (linkki / "kehotteet.json").symlink_to(hak / "kehotteet.json")
    assert lue_kehotteet(linkki).tila == "error"
    kova = tmp_path / "kova"
    kova.mkdir()
    os.link(hak / "kehotteet.json", kova / "kehotteet.json")              # kaksi nimeä samalle tiedostolle
    assert lue_kehotteet(kova).tila == "error"
    monkeypatch.setattr(kehotteet, "RAJA", 100)
    assert lue_kehotteet(hak).tila == "error"


def test_tarkistus_ei_muuta_eika_paasta_lapi_vierasta():
    aika, rivit = tarkista(luettelo(MUOKATTU))
    assert aika == AIKA and rivit == (MUOKATTU,) and set(rivit[0]) == kehotteet.RIVI_KENTAT
