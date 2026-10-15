"""MUODOT-sovitin (muodot.py) ja asennettava sovellus (manifesti).

Riippumaton totuus: alla käsin kirjoitetut julkaisut noudattavat aiops-repon apps/ilmari-selain/MUODOT.md:n kenttiä
(kohdat 2, 3, 7 ja 8), ja odotetut näkymäarvot on laskettu käsin (esim. 23:59:29 + 369,4 s = 00:05:38 seuraavana päivänä).
"""

from __future__ import annotations

import json
import struct

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui import muodot
from ilmari_ui.app import Settings, create_app, format_time
from ilmari_ui.config import parse_config

RP = "tyoasema.taild1a5b7.ts.net"
SERVE = {"x-forwarded-host": RP, "tailscale-user-login": "Elkkuboi@github"}
RUN = "20261013-235929-yo-q6"
OLD = "20261006-232133-yo-q6"
COMMIT = "a47515d0123456789abcdef0123456789abcdef0"

META = {
    "alku": "2026-10-13T23:59:29", "malli": "q6", "ctx": 65536, "ajattelu": "pois",
    "painopiste": "Katselmoi T1-selain.\nToinen rivi.", "suunnitelma": "yo-t1-koe", "repo_commit": COMMIT,
    "taso": "T1", "virhe": "",
    "lopetus": {"syy": "lopeta", "askelia": 85, "kesto_s": 369.4, "nollauksia": 0},
}
OLD_META = {"alku": "2026-10-06T23:21:33", "malli": "q6", "ctx": 65536, "ajattelu": "pois",
            "painopiste": "Valmistele ADR-0011:ää (paikallisen agentin rajapinta). " + "x" * 120,
            "lopetus": {"syy": "lopeta", "askelia": 85, "kesto_s": 369.4}}
PROPOSALS = [
    {"patka": "a", "askel": 3, "aika": "2026-10-14T00:01:00", "otsikko": "<script>alert(1)</script> Eka",
     "perustelu": "Perustelu yksi on tarpeeksi pitkä.", "ehdotus": "Tee näin ensin.", "tiedostot": ["docs/a.md"]},
    {"patka": "a", "askel": 7, "aika": "2026-10-14T00:03:00", "otsikko": "Toka",
     "perustelu": "Perustelu kaksi on tarpeeksi pitkä.", "ehdotus": "Tee noin sitten.", "tiedostot": ["src/b.py", 5]},
]
SOL = {
    "versio": "aiops-sol-tulos-v1", "malli": "gpt-6.1-sol", "paattely": "medium", "ajo": RUN,
    "erat": [
        {"era": 1, "ehdotukset": [1, 2], "tila": "ok", "kustannus_eur": "0.0123",
         "tuomiot": [{"nro": 1, "tuomio": "T", "korjaus_tarpeen": True, "perustelu": "Otteet tukevat.", "lahde": "docs/a.md:3"},
                     {"nro": 2, "tuomio": "V", "korjaus_tarpeen": False, "perustelu": "Rivi sanoo muuta."},
                     {"nro": 1, "tuomio": "E"}]},
        {"era": 2, "ehdotukset": [3], "tila": "hylatty", "selite": "budjetti", "tuomiot": [{"nro": 3, "tuomio": "T"}]},
    ],
}


# --------------------------------------------------------------------------------------------------
# Sovitin
# --------------------------------------------------------------------------------------------------

def test_run_facts_kentat_kasin_lasketut_arvot():
    f = muodot.run_facts(RUN, META)
    assert f["title"] == "yo-t1-koe" and f["level"] == "T1" and f["commit"] == COMMIT[:12]
    assert format_time(f["started_at"]) == "13.10.2026 klo 23.59"
    assert format_time(f["ended_at"]) == "14.10.2026 klo 00.05"
    assert f["model"] == "q6 · ctx 65\u00a0536 · ajattelu pois"
    assert (f["stop_reason"], f["steps"], f["resets"], f["error"]) == ("lopeta", 85, 0, None)


def test_vanha_meta_ilman_suunnitelmaa_saa_otsikon_painopisteesta():
    f = muodot.run_facts(OLD, OLD_META)
    assert f["title"].startswith("Valmistele ADR-0011:ää") and f["title"].endswith("…") and len(f["title"]) == 71
    assert f["level"] is None and f["plan"] is None


@pytest.mark.parametrize("meta", [
    None, [], {"alku": 123, "lopetus": "x", "ctx": "65536", "taso": "T9", "repo_commit": "zz", "malli": ["q6"]},
    {"alku": "ei aika", "lopetus": {"kesto_s": True, "askelia": "85"}}, {"alku": "2026-10-13T23:59:29", "lopetus": {"kesto_s": -5}},
])
def test_vaarat_tyypit_eivat_kaada_eivatka_keksi_arvoja(meta):
    f = muodot.run_facts(RUN, meta)
    assert f["title"] == RUN and f["ended_at"] is None and f["model"] is None and f["level"] is None and f["commit"] is None


def test_tuomiot_vain_ok_erista_ja_ensimmainen_voittaa():
    v = muodot.verdicts_by_number(SOL)
    assert sorted(v) == [1, 2]
    assert (v[1]["verdict"], v[1]["label"], v[1]["correction_needed"], v[1]["source"]) == ("T", "Totta", True, "docs/a.md:3")
    assert (v[2]["verdict"], v[2]["label"]) == ("V", "Väärä")
    assert muodot.verdict_counts(SOL) == {"T": 1, "O": 0, "V": 1, "E": 0}


@pytest.mark.parametrize("sol", [None, [], {"versio": "aiops-sol-tulos-v0", "erat": SOL["erat"]},
                                 {"versio": "aiops-sol-tulos-v1", "erat": "x"}])
def test_vieras_sol_tulos_ei_tuota_tuomioita(sol):
    assert muodot.verdicts_by_number(sol) == {} and muodot.verdict_counts(sol) is None


def test_tuntematon_tuomio_naytetaan_ilman_luokkaa():
    sol = {"versio": "aiops-sol-tulos-v1", "erat": [{"tila": "ok", "tuomiot": [{"nro": 1, "tuomio": "X", "virhe": "tuomio_epakelpo"}]}]}
    v = muodot.verdicts_by_number(sol)[1]
    assert (v["verdict"], v["label"], v["error"]) == (None, "Ei tuomiota", "tuomio_epakelpo")


def test_ehdotusrivi_n_saa_tuomion_n():
    p = muodot.proposals(PROPOSALS, SOL)
    assert [x["number"] for x in p] == [1, 2]
    assert p[0]["verdict"]["verdict"] == "T" and p[1]["verdict"]["verdict"] == "V"
    assert p[1]["files"] == ["src/b.py"] and p[0]["segment"] == "a" and p[1]["step"] == 7


def test_sol_yhteenveto():
    s = muodot.sol_summary(SOL)
    assert (s["model"], s["effort"]) == ("gpt-6.1-sol", "medium")
    assert [(b["batch"], b["state"], b["ok"], b["cost_eur"], b["note"]) for b in s["batches"]] == [
        (1, "ok", True, "0.0123", None), (2, "hylatty", False, None, "budjetti")]


# --------------------------------------------------------------------------------------------------
# Näkymät tuotantotilassa
# --------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("julkaisu") / "ajot"
    run = root / RUN
    run.mkdir(parents=True)
    (run / "meta.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
    (run / "raportti.md").write_text("# Ilmari: yöluenta\n", encoding="utf-8")
    (run / "ehdotukset.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in PROPOSALS), encoding="utf-8")
    (run / "sol-tulos.json").write_text(json.dumps(SOL, ensure_ascii=False), encoding="utf-8")
    (run / "luonnos.patch").write_text("diff --git a/x b/x\n+uusi rivi\n", encoding="utf-8")
    old = root / OLD
    old.mkdir()
    (old / "meta.json").write_text(json.dumps(OLD_META, ensure_ascii=False), encoding="utf-8")
    (old / "raportti.md").write_text("vanha\n", encoding="utf-8")
    config = parse_config({"hub": {"rp_id": RP, "julkaisut": str(root), "kayttajat": {"Elkkuboi@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost", client=None) as c:
        yield c


def test_ajolista_nayttaa_otsikot_maarat_ja_tuomiot(client):
    page = BeautifulSoup(client.get("/ajot", headers=SERVE).text, "html.parser")
    rows = {r.select_one(".run-table-id").text: [td.get_text(" ", strip=True) for td in r.find_all("td")] for r in page.select("tbody tr")}
    assert rows[RUN][2:] == ["13.10.2026 klo 23.59", "q6 · ctx 65\u00a0536 · ajattelu pois", "2", "1 / 0 / 1 / 0"]
    assert rows[RUN][0].startswith("yo-t1-koe")
    assert rows[OLD][4:] == ["0", "–"]


def test_ajon_sivu_nayttaa_ehdotukset_tuomioineen_turvallisesti(client):
    response = client.get(f"/ajot/{RUN}", headers=SERVE)
    page = BeautifulSoup(response.text, "html.parser")
    assert not page.find_all("script") and "&lt;script&gt;alert(1)&lt;/script&gt; Eka" in response.text
    titles = [h.text for h in page.select(".proposal-title")]
    assert titles == ["<script>alert(1)</script> Eka", "Toka"]
    badges = [b.get_text(strip=True) for b in page.select(".proposal-heading .badge")]
    assert badges == ["T · Totta", "V · Väärä"]
    text = page.get_text(" ", strip=True)
    for expected in ("Otteet tukevat. (korjaus tarpeen)", "Lähde: docs/a.md:3", "Erä 1: ok (ehdotukset 1, 2) · 0.0123 €",
                     "Erä 2: hylatty (ehdotukset 3) · budjetti", "+uusi rivi", "Katselmoi T1-selain.", "lopeta · 85 askelta · 6.2 min",
                     "AJON JULKAISU · T1", COMMIT[:12]):
        assert expected in text, expected


# --------------------------------------------------------------------------------------------------
# Asennettava sovellus (PWA)
# --------------------------------------------------------------------------------------------------

def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_manifesti_ja_kuvakkeet(client):
    response = client.get("/static/manifest.webmanifest", headers=SERVE)
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/manifest+json")
    manifest = response.json()
    assert (manifest["start_url"], manifest["scope"], manifest["display"], manifest["id"]) == ("/hub", "/", "standalone", "/hub")
    assert manifest["short_name"] == "Ilmari"
    sizes = {}
    for icon in manifest["icons"]:
        assert icon["src"].startswith("/hub/static/")
        image = client.get(icon["src"].removeprefix("/hub"), headers=SERVE)
        assert image.status_code == 200 and image.headers["content-type"] == "image/png"
        sizes[icon["purpose"], icon["sizes"]] = _png_size(image.content)
    assert sizes == {("any", "192x192"): (192, 192), ("any", "512x512"): (512, 512), ("maskable", "512x512"): (512, 512)}


def test_sivut_linkittavat_manifestin_ja_csp_sallii_vain_oman(client):
    for path in ("/", "/ajot", f"/ajot/{RUN}", "/asetukset"):
        response = client.get(path, headers=SERVE)
        page = BeautifulSoup(response.text, "html.parser")
        assert page.select_one('link[rel="manifest"]')["href"] == "/hub/static/manifest.webmanifest"
        csp = response.headers["content-security-policy"]
        assert "manifest-src 'self'" in csp and "script-src 'none'" in csp and "connect-src 'none'" in csp


def test_virhe_none_merkkijonona_ei_ole_virhe():
    """ilmari_yo.py kirjoittaa "virhe": str(virhe); virheettömän ajon arvo on "None" (todettu 6.10. ajosta)."""
    assert muodot.run_facts(RUN, {"virhe": "None"})["error"] is None
    assert muodot.run_facts(RUN, {"virhe": "RuntimeError: palvelin kaatui"})["error"] == "RuntimeError: palvelin kaatui"


def test_valinnaisten_tiedostojen_puuttuminen_ei_tee_julkaisusta_osittaista(client):
    page = BeautifulSoup(client.get(f"/ajot/{OLD}", headers=SERVE).text, "html.parser")
    text = page.get_text(" ", strip=True)
    assert "Julkaistu" in text and "Osittainen julkaisu" not in text and "Julkaisu on osittainen" not in text
    assert "Ajo kirjasi virheen" not in text


def test_puuttuva_raportti_tai_muu_lukuvirhe_sailyy():
    from ilmari_ui.runs import ReadError
    virheet = (ReadError("not_found", "raportti.md", "puuttuu"), ReadError("not_found", "sol-tulos.json", "puuttuu"),
               ReadError("too_large", "luonnos.patch", "liian suuri"), ReadError("not_found", "luonnos.patch", "puuttuu"))
    assert [(e.code, e.file) for e in muodot.relevant_errors(virheet)] == [("not_found", "raportti.md"), ("too_large", "luonnos.patch")]
