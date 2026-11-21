"""Promptit ja säännöt (aiops 21.11.2026): gatewayn julkaiseman luettelon lukija.

Riippumaton totuus on alla käsin kirjoitettu luettelo samassa muodossa, jossa aiopsin gateway sen kirjoittaa
(src/aiops/gateway/kehotteet.py: KENTAT). Kielletty suunta: vieras tai puuttuva kenttä, väärä tyyppi, liian pitkä
tai ohjausmerkkejä sisältävä teksti, toistuva tunniste, kiinteä teksti muokattuna esitettynä, väärä omistaja, linkki
ja liian suuri tiedosto.

Käsikirjan versiot ja lukko (aiops ADR-0033 pala 6): uusi muoto (lukittu ja jokaisella rivillä versiot) ja vanha muoto
ilman niitä kelpaavat. Rikkinäinen versiolista ei kaada luetteloa: rivin teksti säilyy ja vain versiot jäävät pois.
Kielletty merkki Ilmarin tekstissä (voimassa oleva teksti, version teksti, perustelu) piilottaa vain sen tekstin, ei
riviä, versioita eikä lukkoa. Näkymättömät merkit rakennetaan chr():llä, ei kirjoiteta lähdekoodiin.
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
# Vanhassa muodossa lukija lisää riville nämä: versioita ei ole tiedossa (ei virhettä).
VANHA = {"versiot": None, "voimassa": None, "versiot_virhe": False, "teksti_virhe": False}


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
    assert k.kehotteet[0] == MUOKATTU | VANHA and k.kehotteet[1] == KIINTEA | VANHA and k.lukittu is None
    assert [(nimi, [r["tunniste"] for r in rivit]) for nimi, rivit in ryhmittain(k)] == [
        ("Ilmari", ["jarjestelma", "tyokalut"]), ("Ilmarin kädet", ["tyon_alku"])]
    assert etsi(k, "tyon_alku")["otsikko"] == "Työn alku"
    assert etsi(k, "eiole") is None and etsi(k, "ISO") is None and etsi(k, "../x") is None


def test_esimerkkiaineisto_kelpaa():
    k = lue_kehotteet(toiminta.ESIMERKKI)
    assert k.tila == "ready" and [r["tunniste"] for r in k.kehotteet] == ["jarjestelma", "vuoro", "tyokalut", "tyon_alku"]
    assert k.kehotteet[0]["muokattu"] and k.kehotteet[0]["oletus"] and not k.kehotteet[1]["muokattu"]
    assert k.lukittu is False and all(r["enint"] == 12000 and not r["versiot_virhe"] for r in k.kehotteet)
    assert [(v["n"], v["kuka"]) for v in k.kehotteet[0]["versiot"]] == [(4, "ilmari"), (3, "elias"), (2, "ilmari"),
                                                                       (1, "tehdas")]
    assert k.kehotteet[0]["voimassa"]["n"] == 4 and [r["versiot"] for r in k.kehotteet[1:]] == [(), (), ()]


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
    aika, rivit, lukittu = tarkista(luettelo(MUOKATTU))
    assert aika == AIKA and rivit == (MUOKATTU | VANHA,) and lukittu is None
    assert set(rivit[0]) == kehotteet.RIVI_KENTAT | set(VANHA)
    aika, rivit, lukittu = tarkista(uusi(MUOKATTU | {"versiot": [V2]}))
    assert lukittu is False and set(rivit[0]) == kehotteet.RIVI_KENTAT | set(VANHA)
    assert set(rivit[0]["versiot"][0]) == kehotteet.VERSIO_KENTAT | {"tekija", "sama", "voimassa", "muutokset"}


# --- Käsikirjan versiot ja lukko (aiops ADR-0033 pala 6) ---------------------------------------------------------

ALKU = RIVI["teksti"]
V1 = {"n": 1, "aika": "2026-11-20T09:00:00+02:00", "kuka": "tehdas", "miksi": "", "teksti": ALKU}
V2 = {"n": 2, "aika": "2026-11-20T10:00:00+02:00", "kuka": "ilmari", "miksi": "Raportit lyhyemmiksi.",
      "teksti": MUOKATTU["teksti"]}
V3 = {"n": 3, "aika": "2026-11-20T11:00:00+02:00", "kuka": "elias", "miksi": "palautettu versio 1", "teksti": ALKU}


def uusi(*rivit: dict, lukittu=False, **muutos) -> dict:
    """Uusi muoto, jonka gateway kirjoittaa: lukko ja jokaisella rivillä versiot (oletuksena tyhjä lista)."""
    data = luettelo(*rivit, **muutos) | {"lukittu": lukittu}
    for r in data["kehotteet"]:
        r.setdefault("versiot", [])
    return data


def test_versiot_uusin_ensin_ja_voimassa_oleva_merkitty(tmp_path):
    """Gateway kirjoittaa uusimman ensin; lukija järjestää numeron mukaan joka tapauksessa."""
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(MUOKATTU | {"versiot": [V1, V2]}, KIINTEA, KADET, lukittu=True)))
    assert k.tila == "ready" and k.lukittu is True
    rivi = k.kehotteet[0]
    assert rivi["teksti"] == MUOKATTU["teksti"] and rivi["versiot_virhe"] is False
    assert [(v["n"], v["tekija"], v["voimassa"], v["sama"]) for v in rivi["versiot"]] == [
        (2, "Ilmari", True, True), (1, "alkuperäinen", False, False)]
    assert rivi["voimassa"] == rivi["versiot"][0] and rivi["versiot"][0]["miksi"] == "Raportit lyhyemmiksi."
    assert [(r["versiot"], r["voimassa"]) for r in k.kehotteet[1:]] == [((), None), ((), None)]


def test_voimassa_on_uusin_sama_teksti(tmp_path):
    """Elias palautti alkuperäisen (versio 3): se on voimassa, ja versio 1 on sama teksti (ei palautettavaa)."""
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"versiot": [V3, V2, V1]})))
    versiot = k.kehotteet[0]["versiot"]
    assert [(v["n"], v["tekija"], v["voimassa"], v["sama"]) for v in versiot] == [
        (3, "Elias", True, True), (2, "Ilmari", False, False), (1, "alkuperäinen", False, True)]
    # voimassa oleva teksti ei vastaa yhtään versiota (esim. muokattu ennen versioita): mitään ei merkitä
    k = lue_kehotteet(kirjoita(tmp_path / "u", uusi(MUOKATTU | {"versiot": [V1]})))
    assert k.kehotteet[0]["voimassa"] is None and not k.kehotteet[0]["versiot"][0]["sama"]
    k = lue_kehotteet(kirjoita(tmp_path / "v", uusi(MUOKATTU)))
    assert k.kehotteet[0]["versiot"] == () and k.kehotteet[0]["voimassa"] is None


def test_versioiden_rajat_kelpaavat(tmp_path):
    """Sallittu suunta rajoilla: 10 versiota, 12 000 merkin raja, 300 merkin perustelu, emojin ZWJ, sarkain tekstissä."""
    emoji = chr(0x1F468) + chr(0x200D) + chr(0x1F4BB)
    versiot = [V1 | {"n": n, "miksi": "x" * 300 if n == 10 else emoji, "teksti": f"versio{chr(9)}{n}\nrivi"}
               for n in range(10, 0, -1)]
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"enint": 12000, "versiot": versiot})))
    rivi = k.kehotteet[0]
    assert k.tila == "ready" and rivi["enint"] == 12000 and len(rivi["versiot"]) == 10 and not rivi["versiot_virhe"]
    assert rivi["versiot"][0]["miksi"] == "x" * 300 and rivi["versiot"][1]["miksi"] == emoji


HUONOT_TIEDOSTOT = [
    uusi(lukittu="true"), uusi(lukittu=1), uusi(lukittu=None), uusi(lukittu=[]),
    luettelo(RIVI | {"versiot": []}),                                       # versiot ilman lukkoa (vanha ja uusi sekaisin)
]
# Lukko on kelvollinen, mutta luettelo ei: lukko säilyy, jotta Elias voi lukita, vaikka luettelo olisi rikki.
RIKKI_LUKKO_EHJA = [
    uusi(RIVI) | {"kehotteet": [copy.deepcopy(RIVI)]},                     # lukko, mutta rivillä ei versioita
    uusi(RIVI | {"versiot": [], "vieras": 1}), uusi(RIVI | {"enint": kehotteet.ENINT_MAX + 1}),
    uusi(RIVI | {"teksti": ""}), uusi(RIVI | {"teksti": None}), uusi(RIVI | {"teksti": "x" * (kehotteet.TEKSTI_MAX + 1)}),
    uusi(KIINTEA | {"teksti": "suunta" + chr(0x202E) + "käännetty"}),     # kiinteä teksti: koko luettelo kuten ennen
    uusi(RIVI, aika="0001-01-01T00:30:00+01:00"),                          # ei mahdu Suomen aikaan
]


@pytest.mark.parametrize("data", HUONOT_TIEDOSTOT)
def test_kelvoton_lukko_tai_kenttajoukko_hylkaa_luettelon(tmp_path, data):
    k = lue_kehotteet(kirjoita(tmp_path / "t", data))
    assert k.tila == "error" and k.kehotteet == () and k.lukittu is None


@pytest.mark.parametrize("lukittu", [True, False])
@pytest.mark.parametrize("data", RIKKI_LUKKO_EHJA)
def test_rikkinainen_luettelo_sailyttaa_lukon(tmp_path, data, lukittu):
    k = lue_kehotteet(kirjoita(tmp_path / "t", json.dumps(data | {"lukittu": lukittu})))
    assert k.tila == "error" and k.kehotteet == () and k.lukittu is lukittu


def ilman(kentta: str) -> dict:
    return {k: v for k, v in V1.items() if k != kentta}


HUONOT_VERSIOT = [
    "x", None, {}, [V1, V1], [V1 | {"n": n} for n in range(1, kehotteet.VERSIOITA_MAX + 2)],
    [V1 | {"n": 0}], [V1 | {"n": -1}], [V1 | {"n": True}], [V1 | {"n": "1"}], [V1 | {"n": 1.0}], [V1 | {"n": 2**53}],
    [V1 | {"kuka": "Elias"}], [V1 | {"kuka": "system"}], [V1 | {"kuka": None}], [V1 | {"kuka": ["elias"]}],
    [V1 | {"aika": "2026-11-21T09:00:00"}], [V1 | {"aika": "eilen"}], [V1 | {"aika": None}],
    [V1 | {"miksi": "x" * 301}], [V1 | {"miksi": None}], [V1 | {"miksi": 5}],
    [V1 | {"teksti": ""}], [V1 | {"teksti": " \n "}], [V1 | {"teksti": None}],
    [V1 | {"teksti": "x" * (kehotteet.TEKSTI_MAX + 1)}],
    [V1 | {"aika": "9999-12-31T23:30:00-05:00"}], [V1 | {"aika": "0001-01-01T00:30:00+01:00"}],   # ei mahdu Suomen aikaan
    [V1 | {"aika": "2099-01-01T00:00:00+02:00"}], [V1 | {"aika": "2026-11-21T01:21:00+02:00"}],   # tiedostoa uudempi (yli 10 min)
    [V1 | {"vieras": 1}], [ilman("miksi")], [ilman("n")], ["versio"], [[V1]],
]


@pytest.mark.parametrize("versiot", HUONOT_VERSIOT)
def test_kelvoton_versiolista_ei_piilota_rivia(tmp_path, versiot):
    """Kielletty suunta: versiot jäävät pois (versiot_virhe), mutta rivin teksti ja muut rivit näkyvät. JSON ASCII-muodossa,
    jotta yksinäinen surrogaatti kulkee tiedostoon \\u-merkintänä."""
    data = uusi(MUOKATTU | {"versiot": versiot}, KIINTEA | {"versiot": []}, KADET | {"versiot": []})
    k = lue_kehotteet(kirjoita(tmp_path / "t", json.dumps(data)))
    assert k.tila == "ready" and k.lukittu is False
    rivi = k.kehotteet[0]
    assert rivi["versiot"] is None and rivi["voimassa"] is None and rivi["versiot_virhe"] is True
    assert rivi["teksti"] == MUOKATTU["teksti"] and rivi["oletus"] == MUOKATTU["oletus"]
    assert [(r["versiot"], r["versiot_virhe"]) for r in k.kehotteet[1:]] == [((), False), ((), False)]


KIELLETYT_MERKIT = [chr(0x202E), chr(0x2066), chr(0x200F), chr(0x200E), chr(0x61C), chr(0x200B), chr(0xFEFF), chr(0xAD),
                    chr(0x2060), chr(0x180E), chr(0xE0041), chr(0x1B), chr(0x7F), chr(0x85), chr(0x9B), chr(0x2028),
                    chr(0x2029), chr(0xD800), chr(0x202D)]


@pytest.mark.parametrize("merkki", KIELLETYT_MERKIT, ids=lambda m: f"U+{ord(m):04X}")
def test_kielletty_merkki_piilottaa_vain_sen_tekstin(tmp_path, merkki):
    """Kielletty suunta per teksti: version teksti tai perustelu, jossa on kielletty merkki, on None (ei näytetä eikä
    tekstitöntä palauteta), mutta lista, muut versiot ja rivi näkyvät. Samoin voimassa oleva teksti uudessa muodossa."""
    huono_teksti = V2 | {"n": 4, "teksti": "Olet Ilmari." + merkki + "x"}
    huono_miksi = V2 | {"n": 3, "miksi": "syy" + merkki + "x", "teksti": "Kolmas teksti."}
    data = uusi(MUOKATTU | {"versiot": [huono_teksti, huono_miksi, V2, V1]}, KIINTEA, lukittu=True)
    k = lue_kehotteet(kirjoita(tmp_path / "t", json.dumps(data)))
    assert k.tila == "ready" and k.lukittu is True
    rivi = k.kehotteet[0]
    assert rivi["teksti"] == MUOKATTU["teksti"] and not rivi["teksti_virhe"] and not rivi["versiot_virhe"]
    v4, v3, v2, v1 = rivi["versiot"]
    assert v4["teksti"] is None and v4["miksi"] == V2["miksi"] and not v4["sama"] and v4["muutokset"] is None
    assert v3["teksti"] == "Kolmas teksti." and v3["miksi"] is None
    assert v2["teksti"] == MUOKATTU["teksti"] and v2["voimassa"] and v2["miksi"] == V2["miksi"]
    assert v3["muutokset"]["verrattu"] == 2 and v1["muutokset"] is None
    # Ilmari kirjoitti saman merkin voimassa olevaan tekstiin: teksti piiloon, rivi, versiot ja lukko näkyvät
    paha = MUOKATTU | {"teksti": huono_teksti["teksti"], "versiot": [huono_teksti, V2, V1]}
    k = lue_kehotteet(kirjoita(tmp_path / "u", json.dumps(uusi(paha, KIINTEA, lukittu=False))))
    assert k.tila == "ready" and k.lukittu is False and [r["tunniste"] for r in k.kehotteet] == ["jarjestelma", "tyokalut"]
    rivi = k.kehotteet[0]
    assert rivi["teksti"] is None and rivi["teksti_virhe"] and rivi["oletus"] == MUOKATTU["oletus"]
    assert [(v["n"], v["teksti"] is None, v["sama"]) for v in rivi["versiot"]] == [(4, True, False), (2, False, False),
                                                                                (1, False, False)]
    assert rivi["voimassa"] is None


def test_vanhassa_muodossa_ja_kiintealla_rivilla_voimassa_oleva_teksti_kuten_ennen(tmp_path):
    """Vanha muoto (vain Elias muokkaa) ja kiinteä rivi: rivin LRM-merkki kelpaa kuten ennen, bidi-ohjaus kaataa
    luettelon kuten ennen. Uudessa muodossa muokattavalla rivillä LRM piilottaa tekstin."""
    lrm = "Olet Ilmari." + chr(0x200E)
    assert lue_kehotteet(kirjoita(tmp_path / "a", luettelo(RIVI | {"teksti": lrm}))).kehotteet[0]["teksti"] == lrm
    k = lue_kehotteet(kirjoita(tmp_path / "b", uusi(RIVI, KIINTEA | {"teksti": lrm})))
    assert k.kehotteet[1]["teksti"] == lrm and k.kehotteet[0]["teksti"] == RIVI["teksti"]
    assert lue_kehotteet(kirjoita(tmp_path / "c", uusi(RIVI | {"teksti": lrm}))).kehotteet[0]["teksti_virhe"] is True
    assert lue_kehotteet(kirjoita(tmp_path / "d", luettelo(RIVI | {"teksti": "a" + chr(0x202E)}))).tila == "error"


TYHJAT_KIRJAIMET = [chr(0x3164), chr(0x115F), chr(0x1160), chr(0xFFA0), chr(0x2800), chr(0x34F)]


@pytest.mark.parametrize("merkki", TYHJAT_KIRJAIMET, ids=lambda m: f"U+{ord(m):04X}")
def test_tyhjalta_nayttava_perustelu_piilotetaan(tmp_path, merkki):
    """Perustelu on pakollinen: tyhjältä näyttävä merkki piilottaa sen. Pitkässä tekstissä sama merkki näytetään (gateway
    hyväksyy sen, eikä Hub piilota käsikirjaa sen takia)."""
    data = uusi(MUOKATTU | {"versiot": [V2 | {"miksi": merkki * 3}, V1 | {"miksi": "a" + merkki + "b"},
                                        V3 | {"n": 5, "teksti": "x" + merkki + "y"}]})
    versiot = lue_kehotteet(kirjoita(tmp_path / "t", data)).kehotteet[0]["versiot"]
    assert [(v["n"], v["miksi"]) for v in versiot] == [(5, V3["miksi"]), (2, None), (1, None)]
    assert versiot[0]["teksti"] == "x" + merkki + "y"


def test_sallitut_merkit_perustelussa(tmp_path):
    """Sallittu suunta: emoji ZWJ:llä ja värinvalitsimella, ääkköset, lainausmerkit ja tyhjä perustelu."""
    sydan = chr(0x2764) + chr(0xFE0F)
    perustelut = ["", "Ääkköset ja \"lainaus\" & <merkit>", sydan + " kiitos", chr(0x1F468) + chr(0x200D) + chr(0x1F4BB)]
    versiot = [V1 | {"n": n + 1, "miksi": m} for n, m in enumerate(perustelut)]
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"versiot": versiot})))
    assert [v["miksi"] for v in k.kehotteet[0]["versiot"]] == perustelut[::-1]


def test_versio_saa_olla_hieman_tiedostoa_uudempi(tmp_path):
    """Sallittu suunta: kellon heitto alle 10 min ei hylkää versiota (tiedoston aika 01.10)."""
    data = uusi(RIVI | {"versiot": [V1 | {"aika": "2026-11-21T01:19:00+02:00"}, V2 | {"aika": "2026-11-20T23:19:00Z"}]})
    rivi = lue_kehotteet(kirjoita(tmp_path / "t", data)).kehotteet[0]
    assert not rivi["versiot_virhe"] and [v["n"] for v in rivi["versiot"]] == [2, 1]


def test_aiempi_alkuperainen_erotetaan_nykyisesta(tmp_path):
    """Tehdas-versio, jonka teksti on paketin nykyinen alkuperäinen, on "alkuperäinen"; muu (paketti päivittyi) on
    "aiempi alkuperäinen", jotta se ei sekoitu Palauta alkuperäinen -nappiin."""
    vanha_tehdas = V1 | {"teksti": "Vanha paketin teksti."}
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(MUOKATTU | {"versiot": [V2, vanha_tehdas]})))
    assert [v["tekija"] for v in k.kehotteet[0]["versiot"]] == ["Ilmari", "aiempi alkuperäinen"]
    k = lue_kehotteet(kirjoita(tmp_path / "u", uusi(MUOKATTU | {"versiot": [V2, V1]})))
    assert [v["tekija"] for v in k.kehotteet[0]["versiot"]] == ["Ilmari", "alkuperäinen"]
    k = lue_kehotteet(kirjoita(tmp_path / "v", uusi(RIVI | {"versiot": [V3, V2, vanha_tehdas]})))   # ei muokattu: oletus None
    assert [v["tekija"] for v in k.kehotteet[0]["versiot"]] == ["Elias", "Ilmari", "aiempi alkuperäinen"]


def test_muutokset_edellisesta_versiosta(tmp_path, monkeypatch):
    """Jokaisesta versiosta muuttuneet rivit edelliseen näkyvään versioon; vanhimmasta ei mitään."""
    a = {"n": 1, "teksti": "yksi\nkaksi\nkolme"}
    b = {"n": 2, "teksti": "yksi\nKAKSI\nkolme\nneljä"}
    c = {"n": 3, "teksti": "yksi\nKAKSI\nkolme\nneljä"}
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"versiot": [V1 | c, V1 | b, V1 | a]})))
    v3, v2, v1 = k.kehotteet[0]["versiot"]
    assert v2["muutokset"] == {"verrattu": 1, "lisatty": 2, "poistettu": 1, "leikattu": False,
                               "rivit": (("del", "kaksi"), ("add", "KAKSI"), ("add", "neljä"))}
    assert v3["muutokset"] == {"verrattu": 2, "lisatty": 0, "poistettu": 0, "rivit": (), "leikattu": False}
    assert v1["muutokset"] is None
    monkeypatch.setattr(kehotteet, "MUUTOKSIA_NAYTA", 2)
    v2 = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"versiot": [V1 | b, V1 | a]}))).kehotteet[0]["versiot"][0]
    assert v2["muutokset"]["leikattu"] and len(v2["muutokset"]["rivit"]) == 2 and v2["muutokset"]["lisatty"] == 2
    monkeypatch.setattr(kehotteet, "MUUTOS_RIVIT_MAX", 3)                  # liian monirivinen: ei laskettu
    v2 = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI | {"versiot": [V1 | b, V1 | a]}))).kehotteet[0]["versiot"][0]
    assert v2["muutokset"] is None and v2["teksti"] == b["teksti"]


def test_kiintealla_rivilla_ei_voi_olla_versioita(tmp_path):
    k = lue_kehotteet(kirjoita(tmp_path / "t", uusi(RIVI, KIINTEA | {"versiot": [V1]})))
    assert k.tila == "ready" and k.kehotteet[0]["versiot_virhe"] is False
    assert k.kehotteet[1]["versiot"] is None and k.kehotteet[1]["versiot_virhe"] is True
