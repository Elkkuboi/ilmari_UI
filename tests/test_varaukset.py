"""Ilmarin itse varaamat työvuorot (aiops ADR-0033 pala 6): gatewayn tiedosto toiminta/varaukset.json ja Nyt-sivun
rivit Peru-napein.

Riippumaton totuus on alla käsin kirjoitettu tiedosto samassa muodossa, jossa gateway sen kirjoittaa ({"versio": 1,
"aika", "varaukset": [{"id", "alkaa", "minuutit", "miksi"}]}). Sallittu suunta: puuttuva tiedosto on "ei varauksia"
(vanha gateway), rajat kelpaavat ja lista näytetään aikaisin ensin alku- ja loppuajan kanssa. Kielletty suunta: vieras
tai puuttuva kenttä, väärä tyyppi, kesto rajojen ulkopuolella, toistuva tunniste, aika ilman vyöhykettä tai Suomen ajan
ulkopuolella. Kelvoton tiedosto ei kaada sivua eikä piilota muuta tilaa. Ilmarin perustelu, jossa on ohjaus-, bidi- tai
tyhjältä näyttävä merkki, jää pois, mutta varaus ja sen Peru näkyvät. Näkymättömät merkit rakennetaan chr():llä.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui import toiminta
from ilmari_ui.app import Settings, create_app, lyhyt_aika
from test_toiminta import RP, julkaise, tuotanto

V7 = {"id": 7, "alkaa": "2026-11-21T18:30:00+02:00", "minuutit": 90, "miksi": "Työt 42 ja 43 jäivät kesken."}
V8 = {"id": 8, "alkaa": "2026-11-22T09:00:00+02:00", "minuutit": 60, "miksi": ""}
PERU = "/ilmari/vuoro/varaus/peru"
LUETTU7 = V7 | {"loppuu": "2026-11-21T20:00:00+02:00"}
LUETTU8 = V8 | {"loppuu": "2026-11-22T10:00:00+02:00"}


def varaukset(*rivit: dict, **muutos) -> dict:
    return {"versio": 1, "aika": "2026-11-21T16:00:00+02:00", "varaukset": [dict(v) for v in rivit]} | muutos


def kirjoita(hak: Path, data) -> Path:
    """JSON ASCII-muodossa, jotta myös yksinäinen surrogaatti kulkee tiedostoon."""
    (hak / "varaukset.json").write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return hak


def dom(r) -> BeautifulSoup:
    return BeautifulSoup(r.text, "html.parser")


def peru_lomakkeet(r) -> list[dict[str, str]]:
    tulos = []
    for f in dom(r).find_all("form", action=f"https://{RP}{PERU}"):
        assert f["method"] == "post"
        tulos.append({k["name"]: k["value"] for k in f.find_all("input")})
    return tulos


# --- Lukija: sallittu suunta -------------------------------------------------------------------------------------

def test_varaukset_luetaan_aikaisin_ensin(tmp_path):
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), varaukset(V8, V7)))
    assert t.tila == "ready" and t.virheet == () and t.varaukset == (LUETTU7, LUETTU8)
    yli_yon = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "u"), varaukset(V7 | {"alkaa": "2026-11-21T23:21:00+02:00",
                                                                                     "minuutit": 240})))
    assert yli_yon.varaukset[0]["loppuu"] == "2026-11-22T03:21:00+02:00"


def test_puuttuva_tiedosto_ei_ole_virhe(tmp_path):
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t"))
    assert t.tila == "ready" and t.varaukset == () and t.virheet == ()
    tyhja = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "u"), varaukset()))
    assert tyhja.varaukset == () and tyhja.virheet == ()


def test_esimerkkiaineisto_kelpaa():
    t = toiminta.lue_toiminta(toiminta.ESIMERKKI)
    assert t.virheet == () and [(v["id"], v["minuutit"]) for v in t.varaukset] == [(7, 90), (8, 60)]


def test_rajat_kelpaavat(tmp_path):
    emoji = chr(0x1F468) + chr(0x200D) + chr(0x1F4BB)
    rivit = [V7 | {"id": n, "alkaa": f"2026-11-22T0{n}:00:00+02:00", "minuutit": 30 if n % 2 else 240,
                   "miksi": "x" * 300 if n == 0 else emoji} for n in range(toiminta.VARAUKSIA_MAX)]
    rivit[0]["id"] = 99
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), varaukset(*rivit)))
    assert t.virheet == () and len(t.varaukset) == toiminta.VARAUKSIA_MAX
    assert t.varaukset[0]["miksi"] == "x" * 300 and t.varaukset[1]["miksi"] == emoji


# --- Lukija: kielletty suunta ------------------------------------------------------------------------------------

def ilman(kentta: str) -> dict:
    return {k: v for k, v in V7.items() if k != kentta}


HUONOT = [
    varaukset(V7, versio=2), varaukset(V7, vieras=1), varaukset(V7, aika="2026-11-21T16:00:00"),
    {"versio": 1, "aika": "2026-11-21T16:00:00+02:00"}, varaukset(varaukset={}), varaukset(varaukset=None),
    varaukset(*[V7 | {"id": n} for n in range(1, toiminta.VARAUKSIA_MAX + 2)]),
    varaukset(V7, V7), varaukset(V7 | {"vieras": 1}), varaukset(ilman("miksi")), varaukset(ilman("id")), ["x"],
    varaukset(V7 | {"id": 0}), varaukset(V7 | {"id": -1}), varaukset(V7 | {"id": True}), varaukset(V7 | {"id": "7"}),
    varaukset(V7 | {"minuutit": 29}), varaukset(V7 | {"minuutit": 241}), varaukset(V7 | {"minuutit": True}),
    varaukset(V7 | {"minuutit": "60"}), varaukset(V7 | {"minuutit": 60.0}),
    varaukset(V7 | {"alkaa": "2026-11-21T18:30:00"}), varaukset(V7 | {"alkaa": "huomenna"}), varaukset(V7 | {"alkaa": None}),
    varaukset(V7 | {"alkaa": "0001-01-01T00:30:00+01:00"}), varaukset(V7 | {"alkaa": "9999-12-31T23:30:00-05:00"}),
    varaukset(V7 | {"alkaa": "9999-12-31T22:00:00+02:00", "minuutit": 240}),   # alku mahtuu, loppu ei
    varaukset(V7, aika="0001-01-01T00:30:00+01:00"),
    varaukset(V7 | {"miksi": None}), varaukset(V7 | {"miksi": "x" * 301}), varaukset(V7 | {"miksi": 5}),
]
# Perustelu jää pois (None), mutta varaus näkyy
HUONOT_PERUSTELUT = ["kaksi\nriviä", "suunta" + chr(0x202E) + "käännetty", "a" + chr(0x2067) + "b", "merkki" + chr(0x200F),
                     "a" + chr(0x1B) + "[31m", "a" + chr(9) + "b", "a" + chr(0x7F), "a" + chr(0x9B) + "b",
                     "a" + chr(0x200B) + "b", "a" + chr(0x2028) + "b", "a" + chr(0xDC00), chr(0x3164) * 3,
                     "a" + chr(0x2800) + "b", chr(0x115F), "a" + chr(0x34F), chr(0xFFA0) + "x", chr(0x1160)]


@pytest.mark.parametrize("data", HUONOT)
def test_kelvoton_tiedosto_ei_piilota_muuta_tilaa(tmp_path, data):
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), data))
    assert t.tila == "ready" and t.varaukset is None
    assert [v for v in t.virheet if v.startswith("varaukset.json: ")] and len(t.virheet) == 1
    assert t.tilanne["seis"] is False and t.asetukset["kello"] == "03:30" and t.teot


@pytest.mark.parametrize("miksi", HUONOT_PERUSTELUT, ids=lambda m: "-".join(f"{ord(c):04X}" for c in m if not c.isalnum()))
def test_kielletty_merkki_piilottaa_vain_perustelun(tmp_path, miksi):
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), varaukset(V7 | {"miksi": miksi}, V8)))
    assert t.virheet == () and t.varaukset == (LUETTU7 | {"miksi": None}, LUETTU8)


@pytest.mark.parametrize("raaka", ["{rikki", "[]", '{"versio": 1, "versio": 1, "aika": null, "varaukset": []}',
                                   '{"versio": 1, "aika": "2026-11-21T16:00:00+02:00", "varaukset": [], "x": NaN}'])
def test_rikkinainen_json_hylataan(tmp_path, raaka):
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), raaka))
    assert t.varaukset is None and t.virheet


def test_linkki_ja_liian_suuri_hylataan(tmp_path, monkeypatch):
    oikea = kirjoita(julkaise(tmp_path / "oikea"), varaukset(V7))
    hak = julkaise(tmp_path / "linkki")
    (hak / "varaukset.json").symlink_to(oikea / "varaukset.json")
    assert toiminta.lue_toiminta(hak).varaukset is None
    monkeypatch.setitem(toiminta.RAJAT, toiminta.VARAUKSET, 50)
    assert toiminta.lue_toiminta(oikea).varaukset is None


# --- Nyt-sivu ----------------------------------------------------------------------------------------------------

def test_nyt_esimerkkitilassa_varaukset_ilman_lomakkeita():
    r = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None).get("/hub?demo=1")
    sivu = dom(r)
    rivit = sivu.select("section[aria-labelledby=h-tila] .varaus")
    assert [" ".join(x.span.get_text().split()) for x in rivit] == [
        "Ilmari on varannut työvuoron: 19.11. klo 18.30–20.00, 90 min.",
        "Ilmari on varannut työvuoron: 20.11. klo 09.00–10.00, 60 min."]
    assert [x.find("p").get_text() for x in rivit] == ["Miksi: Työt 42 ja 43 jäivät kesken; jatkan niitä ennen yöajoa.",
                                                       "Miksi: Aamun raportti ja testien korjaus."]
    assert [[b.get_text() for b in x.find_all("button")] for x in rivit] == [["Peru"], ["Peru"]]
    assert all(f"0{chr(0xA0)}min." in x.span.get_text() for x in rivit)    # kesto ei katkea kahdelle riville
    assert "<form" not in r.text and r.headers.get("Refresh") == "30"        # piilokenttä ei estä päivitystä


def test_tuotannossa_peru_lomake_gatewaylle(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, kirjoita(julkaise(tmp_path / "toiminta"), varaukset(V8, V7)))
    assert r.status_code == 200 and peru_lomakkeet(r) == [{"paluu": "hub", "id": "7"}, {"paluu": "hub", "id": "8"}]
    tila = dom(r).find("section", attrs={"aria-labelledby": "h-tila"})
    assert [" ".join(f.span.get_text().split()) for f in tila.select(".varaus form")] == [
        f"Ilmari on varannut työvuoron: {' '.join(lyhyt_aika(V7['alkaa']).split())}–20.00, 90 min.",
        f"Ilmari on varannut työvuoron: {' '.join(lyhyt_aika(V8['alkaa']).split())}–10.00, 60 min."]
    # Ilmarin perustelu omalla rivillään merkittynä, ei Hubin lauseen jatkona; tyhjästä ei riviä
    assert [[p.get_text() for p in v.find_all("p")] for v in tila.select(".varaus")] == [
        ["Miksi: Työt 42 ja 43 jäivät kesken."], []]
    assert r.text.index('class="state"') < r.text.index("Ilmari on varannut") < r.text.index('id="h-odottaa"')
    assert [b.get_text() for b in dom(r).select(".state .actions button")] == ["Töihin nyt", "Seis"]


def test_tuotannossa_ei_varauksia_ei_rivia(tmp_path, monkeypatch):
    for hak in (julkaise(tmp_path / "puuttuu"), kirjoita(julkaise(tmp_path / "tyhja"), varaukset())):
        r = tuotanto(tmp_path, monkeypatch, hak)
        assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == []
    # tilaa ei voi lukea: ei varauksia, vaikka tiedosto olisi
    r = tuotanto(tmp_path, monkeypatch, tmp_path / "eiole")
    assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == []


@pytest.mark.parametrize("data", [varaukset(V7 | {"minuutit": 29}), varaukset(V7 | {"alkaa": "0001-01-01T00:30:00+01:00"}),
                                  varaukset(V7 | {"alkaa": "9999-12-31T23:30:00-05:00"})])
def test_tuotannossa_kelvoton_tiedosto_ei_kaada_sivua(tmp_path, monkeypatch, data):
    """Myös aika, joka ei mahdu Suomen aikaan (ennen 500): virherivi Odottaa sinua -listassa, muu sivu toimii."""
    r = tuotanto(tmp_path, monkeypatch, kirjoita(julkaise(tmp_path / "toiminta"), data))
    assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == []
    odottaa = dom(r).find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert "varaukset.json" in odottaa.get_text() and "Seis" in [b.get_text() for b in dom(r).find_all("button")]


def test_tuotannossa_kielletty_merkki_perustelussa_ei_piilota_varausta(tmp_path, monkeypatch):
    """Ilmari ei voi piilottaa varaustaan Eliakselta kielletyllä merkillä: varaus ja Peru näkyvät, perustelu ei."""
    hak = kirjoita(julkaise(tmp_path / "toiminta"), varaukset(V7 | {"miksi": "a" + chr(0x202E) + "b"},
                                                              V8 | {"miksi": chr(0x3164) * 3}))
    r = tuotanto(tmp_path, monkeypatch, hak)
    assert r.status_code == 200 and chr(0x202E) not in r.text and chr(0x3164) not in r.text
    assert peru_lomakkeet(r) == [{"paluu": "hub", "id": "7"}, {"paluu": "hub", "id": "8"}]
    assert [[p.get_text() for p in v.find_all("p")] for v in dom(r).select(".varaus")] == [
        ["Miksi: ei voi näyttää (kielletty merkki)."], ["Miksi: ei voi näyttää (kielletty merkki)."]]


def test_ilmarin_perustelu_koodataan(tmp_path, monkeypatch):
    paha = V7 | {"miksi": "<b>kiire</b><script>alert(1)</script><img src=x onerror=alert(2)>"}
    r = tuotanto(tmp_path, monkeypatch, kirjoita(julkaise(tmp_path / "toiminta"), varaukset(paha)))
    assert r.status_code == 200 and "<script>" not in r.text and "<img" not in r.text and "<b>kiire" not in r.text
    assert "&lt;b&gt;kiire&lt;/b&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    rivi = dom(r).select_one(".varaus p")
    assert rivi.get_text() == "Miksi: " + paha["miksi"] and not rivi.find_all(True)
