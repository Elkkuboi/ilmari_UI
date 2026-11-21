"""Ilmarin itse varaamat työvuorot (aiops ADR-0033 pala 6): gatewayn tiedosto toiminta/varaukset.json ja Nyt-sivun
rivit Peru-napein.

Riippumaton totuus on alla käsin kirjoitettu tiedosto samassa muodossa, jossa gateway sen kirjoittaa ({"versio": 1,
"aika", "varaukset": [{"id", "alkaa", "minuutit", "miksi"}]}). Sallittu suunta: puuttuva tiedosto on "ei varauksia"
(vanha gateway), rajat kelpaavat ja lista näytetään aikaisin ensin. Kielletty suunta: vieras tai puuttuva kenttä,
väärä tyyppi, kesto rajojen ulkopuolella, toistuva tunniste, aika ilman vyöhykettä ja Ilmarin perustelussa ohjaus- tai
bidi-merkki. Kelvoton tiedosto ei kaada sivua eikä piilota muuta tilaa. Näkymättömät merkit rakennetaan chr():llä.
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
    assert t.tila == "ready" and t.virheet == () and t.varaukset == (V7, V8)


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
    varaukset(V7 | {"miksi": None}), varaukset(V7 | {"miksi": "x" * 301}), varaukset(V7 | {"miksi": "kaksi\nriviä"}),
    varaukset(V7 | {"miksi": "suunta" + chr(0x202E) + "käännetty"}), varaukset(V7 | {"miksi": "a" + chr(0x2067) + "b"}),
    varaukset(V7 | {"miksi": "merkki" + chr(0x200F)}), varaukset(V7 | {"miksi": "a" + chr(0x1B) + "[31m"}),
    varaukset(V7 | {"miksi": "a" + chr(9) + "b"}), varaukset(V7 | {"miksi": "a" + chr(0x7F)}),
    varaukset(V7 | {"miksi": "a" + chr(0x9B) + "b"}), varaukset(V7 | {"miksi": "a" + chr(0x200B) + "b"}),
    varaukset(V7 | {"miksi": "a" + chr(0x2028) + "b"}), varaukset(V7 | {"miksi": "a" + chr(0xDC00)}),
]


@pytest.mark.parametrize("data", HUONOT)
def test_kelvoton_tiedosto_ei_piilota_muuta_tilaa(tmp_path, data):
    t = toiminta.lue_toiminta(kirjoita(julkaise(tmp_path / "t"), data))
    assert t.tila == "ready" and t.varaukset is None
    assert [v for v in t.virheet if v.startswith("varaukset.json: ")] and len(t.virheet) == 1
    assert t.tilanne["seis"] is False and t.asetukset["kello"] == "03:30" and t.teot


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
        "Ilmari on varannut työvuoron: 19.11. klo 18.30, 90 min. Työt 42 ja 43 jäivät kesken; jatkan niitä ennen yöajoa.",
        "Ilmari on varannut työvuoron: 20.11. klo 09.00, 60 min. Aamun raportti ja testien korjaus."]
    assert [[b.get_text() for b in x.find_all("button")] for x in rivit] == [["Peru"], ["Peru"]]
    assert all(f"0{chr(0xA0)}min." in x.span.get_text() for x in rivit)    # kesto ei katkea kahdelle riville
    assert "<form" not in r.text and r.headers.get("Refresh") == "30"        # piilokenttä ei estä päivitystä


def test_tuotannossa_peru_lomake_gatewaylle(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, kirjoita(julkaise(tmp_path / "toiminta"), varaukset(V8, V7)))
    assert r.status_code == 200 and peru_lomakkeet(r) == [{"paluu": "hub", "id": "7"}, {"paluu": "hub", "id": "8"}]
    tila = dom(r).find("section", attrs={"aria-labelledby": "h-tila"})
    assert [" ".join(f.span.get_text().split()) for f in tila.select("form.varaus")] == [
        f"Ilmari on varannut työvuoron: {' '.join(lyhyt_aika(V7['alkaa']).split())}, 90 min. Työt 42 ja 43 jäivät kesken.",
        f"Ilmari on varannut työvuoron: {' '.join(lyhyt_aika(V8['alkaa']).split())}, 60 min."]
    assert r.text.index('class="state"') < r.text.index("Ilmari on varannut") < r.text.index('id="h-odottaa"')
    assert [b.get_text() for b in dom(r).select(".state .actions button")] == ["Töihin nyt", "Seis"]


def test_tuotannossa_ei_varauksia_ei_rivia(tmp_path, monkeypatch):
    for hak in (julkaise(tmp_path / "puuttuu"), kirjoita(julkaise(tmp_path / "tyhja"), varaukset())):
        r = tuotanto(tmp_path, monkeypatch, hak)
        assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == []
    # tilaa ei voi lukea: ei varauksia, vaikka tiedosto olisi
    r = tuotanto(tmp_path, monkeypatch, tmp_path / "eiole")
    assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == []


def test_tuotannossa_kelvoton_tiedosto_ei_kaada_sivua(tmp_path, monkeypatch):
    hak = kirjoita(julkaise(tmp_path / "toiminta"), varaukset(V7 | {"miksi": "a" + chr(0x202E) + "b"}))
    r = tuotanto(tmp_path, monkeypatch, hak)
    assert r.status_code == 200 and "varannut" not in r.text and peru_lomakkeet(r) == [] and chr(0x202E) not in r.text
    odottaa = dom(r).find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert "varaukset.json" in odottaa.get_text() and "Seis" in [b.get_text() for b in dom(r).find_all("button")]


def test_ilmarin_perustelu_koodataan(tmp_path, monkeypatch):
    paha = V7 | {"miksi": "<b>kiire</b><script>alert(1)</script><img src=x onerror=alert(2)>"}
    r = tuotanto(tmp_path, monkeypatch, kirjoita(julkaise(tmp_path / "toiminta"), varaukset(paha)))
    assert r.status_code == 200 and "<script>" not in r.text and "<img" not in r.text and "<b>kiire" not in r.text
    assert "&lt;b&gt;kiire&lt;/b&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    rivi = dom(r).select_one("form.varaus span")
    assert rivi.get_text().endswith(paha["miksi"]) and not rivi.find_all(True)
