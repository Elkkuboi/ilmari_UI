"""Ilmari nyt (aiops ADR-0032, Pala 1, 18.11.2026): toiminnan lukija ja sivu.

Riippumaton totuus on käsin kirjoitettu julkaisu alla (speksin muodot: asetukset.json, tila.json, ohjeet.json,
tavoitteet.json, teot.jsonl). Testataan molemmat suunnat: kelvollinen näkyy, kelvoton hylätään tiedostokohtaisesti
eikä piilota Seis-tilaa; lomakkeet menevät gatewaylle vain tuotannossa.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui import kehitys, toiminta
from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import parse_config

UID = os.getuid()
OMAT = frozenset({UID})
RP = "tyoasema.test"
SERVE = {"x-forwarded-host": RP, "tailscale-user-login": "elias@github", "x-forwarded-proto": "https",
         "x-forwarded-for": "100.67.5.28"}
NYT = datetime(2026, 11, 19, 1, 10, tzinfo=UTC)  # 03.10 Helsingissä

ASETUKSET = {"versio": 1, "yoajo": {"paalla": False, "kello": "03:30"}}
TILA = {"versio": 1, "seis": False, "seis_aika": None, "seis_kuka": None, "yoajo_viimeisin": "2026-11-18",
        "vuoro": None,
        "rajatesti": {"aika": "2026-11-19T01:58:00+02:00", "tyo": 7, "lapi": False, "kohdat": [
            {"nimi": "docker_soketti", "odotus": "estetty", "lapi": False, "havainto": "/var/run/docker.sock <b>auki</b>"},
            {"nimi": "internet", "odotus": "sallittu", "lapi": True, "havainto": "1.1.1.1:443 yhdistyi"}]}}
OHJEET = {"versio": 1, "ohjeet": [{"id": 3, "aika": "2026-11-18T10:00:00+02:00", "teksti": "Raportit lyhyesti.\nEi listoja."},
                                  {"id": 9, "aika": "2026-11-18T11:00:00+02:00", "teksti": "<script>alert(1)</script>"}]}
TAVOITTEET = {"versio": 1, "aika": "2026-11-18T12:00:00+02:00", "rivit": ["Kuvareitti valmiiksi", "Aamuraportti <i>7</i>"]}
RAPORTTI = {"versio": 1, "aika": "2026-11-19T04:40:00+02:00", "saie": 12, "laji": "yoajo",
            "teksti": "Aamuraportti\n\n- Tein <b>x</b>\n- Testit läpi"}


def teko(n: int, **muutos) -> dict:
    t = {"aika": f"2026-11-18T{n // 60:02d}:{n % 60:02d}:00+02:00", "lahde": "gateway", "laji": "tyo_alkoi",
         "mita": f"teko {n}", "miksi": "", "peru": "", "tyo": None, "saie": None}
    t.update(muutos)
    return t


def rivit(*teot) -> bytes:
    return b"".join(json.dumps(t, ensure_ascii=False).encode("utf-8") + b"\n" for t in teot)


def julkaise(hak: Path, *, asetukset=ASETUKSET, tila=TILA, ohjeet=OHJEET, tavoitteet=TAVOITTEET, teot=None,
             raportti=None) -> Path:
    """None jättää tiedoston pois (raportti puuttuu oletuksena); bytes kirjoitetaan sellaisenaan."""
    hak.mkdir(parents=True, exist_ok=True)
    for nimi, data in (("asetukset.json", asetukset), ("tila.json", tila), ("ohjeet.json", ohjeet),
                       ("tavoitteet.json", tavoitteet), ("raportti.json", raportti)):
        if data is not None:
            (hak / nimi).write_bytes(data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode())
    teot = rivit(teko(1, lahde="ilmari", laji="kirjaus", mita="Tein <b>x</b>", miksi="koska", peru="git revert", tyo=5),
                 teko(2, laji="seis", mita="Seis painettu")) if teot is None else teot
    if teot is not False:
        (hak / "teot.jsonl").write_bytes(teot)
    return hak


# --- Lukija ---------------------------------------------------------------------------------------------------------

def test_esimerkki_kelpaa_kokonaan():
    t = toiminta.lue_toiminta(toiminta.ESIMERKKI)
    assert t.tila == "ready" and t.virheet == () and t.teot_ohitettu == 0
    assert t.asetukset == {"paalla": True, "kello": "02:00", "oletus": False}
    assert t.tilanne["rajatesti"]["lapi"] is True and len(t.ohjeet) == 3
    # Pala 1b: esimerkissä työvuoro käynnissä ja yön raportti julkaistu
    assert t.tilanne["vuoro"]["laji"] == "tyovuoro" and t.tilanne["vuoro"]["nimi"] == "Työvuoro"
    assert t.tilanne["vuoro"]["saie"] == 13 and t.tilanne["yoajo_viimeisin"] == "2026-11-19"
    assert len(t.teot) == 9 and t.teot[0]["laji"] == "tyovuoro_alkoi"  # uusin ensin
    assert t.raportti["laji"] == "yoajo" and t.raportti["saie"] == 12 and t.raportti_virhe is False


def test_kelvollinen_julkaisu(tmp_path):
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", raportti=RAPORTTI), omistajat=OMAT)
    assert t.tila == "ready" and t.virheet == ()
    assert t.raportti == {"aika": "2026-11-19T04:40:00+02:00", "saie": 12, "laji": "yoajo", "nimi": "Yöajo",
                          "teksti": "Aamuraportti\n\n- Tein <b>x</b>\n- Testit läpi"} and t.raportti_virhe is False
    assert t.asetukset == {"paalla": False, "kello": "03:30", "oletus": False}
    assert t.tilanne["seis"] is False and t.tilanne["yoajo_viimeisin"] == "2026-11-18"
    r = t.tilanne["rajatesti"]
    assert r["lapi"] is False and [k["nimi"] for k in r["hylatyt"]] == ["docker_soketti"]
    assert r["kohdat"][0]["odotus_teksti"] == "pitää estyä" and r["kohdat"][0]["havainto"] == "/var/run/docker.sock <b>auki</b>"
    assert [o["id"] for o in t.ohjeet] == [3, 9] and t.ohjeet[0]["teksti"] == "Raportit lyhyesti.\nEi listoja."
    assert t.tavoitteet == {"aika": "2026-11-18T12:00:00+02:00", "rivit": ["Kuvareitti valmiiksi", "Aamuraportti <i>7</i>"]}
    assert [x["mita"] for x in t.teot] == ["Seis painettu", "Tein <b>x</b>"]
    assert t.teot[1] == {"aika": "2026-11-18T00:01:00+02:00", "lahde": "ilmari", "tekija": "Ilmari", "laji": "kirjaus",
                         "mita": "Tein <b>x</b>", "miksi": "koska", "peru": "git revert", "tyo": 5, "saie": None,
                         "tyo_linkki": False}


def test_puuttuva_hakemisto_ja_puuttuvat_tiedostot(tmp_path):
    assert toiminta.lue_toiminta(tmp_path / "ei", omistajat=OMAT).tila == "not_published"
    tyhja = tmp_path / "tyhja"
    tyhja.mkdir()
    t = toiminta.lue_toiminta(tyhja, omistajat=OMAT)
    # puuttuva tiedosto = oletus kuten gatewayssa (yöajo päällä 02:00, ei seis), ei virhe; ei raporttia ei ole virhe
    assert t.tila == "ready" and t.virheet == () and t.teot == () and t.ohjeet == ()
    assert t.raportti is None and t.raportti_virhe is False
    assert t.asetukset == {"paalla": True, "kello": "02:00", "oletus": True}
    assert t.tilanne["seis"] is False and t.tilanne["vuoro"] is None and t.tavoitteet == {"aika": None, "rivit": []}


def test_vaara_omistaja_ja_polku(tmp_path):
    hak = julkaise(tmp_path / "t")
    t = toiminta.lue_toiminta(hak, omistajat=frozenset({UID + 1}))
    assert t.tila == "error" and "omistaja" in t.viesti
    assert toiminta.lue_toiminta("suhteellinen/polku").tila == "error"
    assert 0 in kehitys.sallitut_omistajat()  # tuotannon omistajat: root ja gateway


def test_symlinkki_ei_kelpaa(tmp_path):
    hak = julkaise(tmp_path / "t", tila=None, teot=False)
    (tmp_path / "muu.json").write_text(json.dumps({**TILA, "seis": True}))
    (hak / "tila.json").symlink_to(tmp_path / "muu.json")
    (tmp_path / "muu.jsonl").write_bytes(rivit(teko(1)))
    (hak / "teot.jsonl").symlink_to(tmp_path / "muu.jsonl")
    t = toiminta.lue_toiminta(hak, omistajat=OMAT)
    assert t.tilanne is None and t.teot is None and len(t.virheet) == 2
    linkki = tmp_path / "linkki"
    linkki.symlink_to(hak)
    assert toiminta.lue_toiminta(linkki, omistajat=OMAT).tila == "error"


@pytest.mark.parametrize("nimi,arvo", [
    ("asetukset", {**ASETUKSET, "lisa": 1}),
    ("asetukset", {**ASETUKSET, "versio": 2}),
    ("asetukset", {**ASETUKSET, "versio": True}),
    ("asetukset", {"versio": 1, "yoajo": {"paalla": "true", "kello": "02:00"}}),
    ("asetukset", {"versio": 1, "yoajo": {"paalla": True, "kello": "24:00"}}),
    ("asetukset", {"versio": 1, "yoajo": {"paalla": True, "kello": "2:00"}}),
    ("asetukset", {"versio": 1, "yoajo": {"paalla": True, "kello": "02:00", "kesto": 180}}),
    ("tila", {**TILA, "seis": "false"}),
    ("tila", {**TILA, "pysaytetty": True}),
    ("tila", {k: v for k, v in TILA.items() if k != "seis_kuka"}),
    ("tila", {**TILA, "seis_aika": "2026-11-18T10:00:00"}),  # ei aikavyöhykettä
    ("tila", {**TILA, "yoajo_viimeisin": "eilen"}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": 1, "aika": "2026-11-18T10:00:00+02:00", "teksti": "x" * 401}]}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": 1, "aika": "2026-11-18T10:00:00+02:00", "teksti": " "}]}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": i, "aika": "2026-11-18T10:00:00+02:00", "teksti": "x"} for i in range(1, 42)]}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": 1, "aika": "2026-11-18T10:00:00+02:00", "teksti": "a"}] * 2}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": True, "aika": "2026-11-18T10:00:00+02:00", "teksti": "a"}]}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": 0, "aika": "2026-11-18T10:00:00+02:00", "teksti": "a"}]}),
    ("ohjeet", {"versio": 1, "ohjeet": [{"id": 1, "aika": "2026-11-18T10:00:00+02:00", "teksti": "a\x1b[31m"}]}),
    ("tavoitteet", {**TAVOITTEET, "rivit": ["x"] * 21}),
    ("tavoitteet", {**TAVOITTEET, "rivit": ["x" * 201]}),
    ("tavoitteet", {**TAVOITTEET, "rivit": ["kaksi\nriviä"]}),
    ("tavoitteet", {**TAVOITTEET, "rivit": ["oikein", "‮väärin"]}),
    ("tavoitteet", {**TAVOITTEET, "aika": None}),
    ("tavoitteet", b'{"versio": 1, "versio": 1, "aika": "2026-11-18T12:00:00+02:00", "rivit": []}'),
    ("tavoitteet", b'{"versio": 1, "aika": "2026-11-18T12:00:00+02:00", "rivit": [NaN]}'),
    ("tavoitteet", b"[" * 30000 + b"]" * 30000),  # RecursionError ei kaada sivua
    ("tavoitteet", b"{ei json"),
], ids=lambda v: v if isinstance(v, str) else type(v).__name__)
def test_kelvoton_tiedosto_hylataan_yksinaan(tmp_path, nimi, arvo):
    """Rikkinäinen tiedosto näkyy virheenä ja sen osa on None; muut osat näkyvät (ei kaada sivua)."""
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", **{nimi: arvo}), omistajat=OMAT)
    osa = {"asetukset": t.asetukset, "tila": t.tilanne, "ohjeet": t.ohjeet, "tavoitteet": t.tavoitteet}
    assert t.tila == "ready" and osa[nimi] is None and len(t.virheet) == 1 and t.virheet[0].startswith(nimi)
    assert all(v is not None for k, v in osa.items() if k != nimi) and len(t.teot) == 2


@pytest.mark.parametrize("muutos", [
    {"vuoro": {"laji": "yoajo", "saie": 0, "istunto": 1, "alkoi": "2026-11-19T02:00:00+02:00", "paattyy": "2026-11-19T04:55:00+02:00"}},
    {"vuoro": {"laji": "yoajo", "saie": 2, "istunto": 1, "alkoi": "2026-11-19T02:00:00+02:00"}},
    {"rajatesti": {**TILA["rajatesti"], "kohdat": [TILA["rajatesti"]["kohdat"][0]] * 41}},
    {"rajatesti": {**TILA["rajatesti"], "kohdat": [{**TILA["rajatesti"]["kohdat"][0], "havainto": "x" * 201}]}},
    {"rajatesti": {**TILA["rajatesti"], "kohdat": [{**TILA["rajatesti"]["kohdat"][0], "odotus": "ehka"}]}},
    {"rajatesti": {**TILA["rajatesti"], "lapi": 1}},
    {"rajatesti": {**TILA["rajatesti"], "tyo": "7"}},
])
def test_rikkinainen_vuoro_tai_rajatesti_ei_piilota_seisia(tmp_path, muutos):
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", tila={**TILA, "seis": True, **muutos}), omistajat=OMAT)
    avain = next(iter(muutos))
    assert t.tilanne is not None and t.tilanne["seis"] is True
    assert t.tilanne[avain] is None and t.tilanne[avain + "_virhe"] is True and len(t.virheet) == 1
    assert toiminta.tilarivi(t, NYT)["seis"] is True


def test_tekoloki_ohittaa_kelvottomat_rivit(tmp_path):
    kelvottomat = [
        json.dumps({**teko(3), "lisa": 1}).encode(),
        json.dumps(teko(4, lahde="elias")).encode(),                    # lahde on gatewayn: vain gateway | ilmari
        json.dumps(teko(5, tyo="5")).encode(),
        json.dumps(teko(6, tyo=True)).encode(),
        json.dumps(teko(7, aika="2026-11-18T10:00:00")).encode(),
        json.dumps(teko(8, mita=" ")).encode(),
        json.dumps(teko(9, mita="x" * 2100)).encode(),                  # rivi yli 2000 tavua
        b"{ei json",
        b"",
        b'{"aika": 1, "aika": 2}',
    ]
    data = rivit(teko(1)) + b"\n".join(kelvottomat) + b"\n" + rivit(teko(2, mita="ok\x07‮\nrivi", saie=4))
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", teot=data + b'{"kesken": '), omistajat=OMAT)
    assert t.virheet == () and t.teot_ohitettu == len(kelvottomat)  # päättämätön viimeinen pala ei ole virhe
    assert [x["mita"] for x in t.teot] == ["ok rivi", "teko 1"] and t.teot[0]["saie"] == 4


def test_tekoloki_rajataan_sataan_ja_hantaan(tmp_path):
    t = toiminta.lue_toiminta(julkaise(tmp_path / "a", teot=rivit(*(teko(n) for n in range(250)))), omistajat=OMAT)
    assert len(t.teot) == 100 and t.teot[0]["mita"] == "teko 249" and t.teot[-1]["mita"] == "teko 150"
    # iso loki: vain loppu luetaan; katkennut ensimmäinen rivi ei ole virhe
    iso = rivit(*(teko(n % 1400, miksi="m" * 1500) for n in range(600)))
    assert len(iso) > toiminta.HANTA
    t = toiminta.lue_toiminta(julkaise(tmp_path / "b", teot=iso), omistajat=OMAT)
    assert len(t.teot) == 100 and t.teot_ohitettu == 0 and t.virheet == ()
    # kierrätys ei toimi: liian iso loki on virhe, muu sivu näkyy
    with open(julkaise(tmp_path / "c", teot=b"") / "teot.jsonl", "wb") as f:
        f.truncate(toiminta.TEOT_RAJA + 1)
    t = toiminta.lue_toiminta(tmp_path / "c", omistajat=OMAT)
    assert t.teot is None and t.virheet[0].startswith("teot.jsonl") and t.tilanne is not None


def test_kierretty_loki_jatkaa_uutta(tmp_path):
    hak = julkaise(tmp_path / "t", teot=rivit(teko(10), teko(11)))
    (hak / "teot.1.jsonl").write_bytes(rivit(*(teko(n) for n in range(5))))
    t = toiminta.lue_toiminta(hak, omistajat=OMAT)
    assert [x["mita"] for x in t.teot] == ["teko 11", "teko 10", "teko 4", "teko 3", "teko 2", "teko 1", "teko 0"]
    # sama inode molemmilla nimillä (kierrätys kesken luvun) luetaan kerran
    rivi = rivit(teko(1))
    luettu = []

    def hanta(hd, nimi, omistajat, deadline):
        luettu.append(nimi)
        return rivi, True, (1, 2, 3)
    alkup = toiminta._lue_hanta
    toiminta._lue_hanta = hanta
    try:
        teot, ohitettu = toiminta._lue_teot(0, None, 0.0)
    finally:
        toiminta._lue_hanta = alkup
    assert luettu == ["teot.jsonl", "teot.1.jsonl"] and len(teot) == 1 and ohitettu == 0


def test_lisays_luvun_aikana_ei_haittaa_mutta_katkaisu_haittaa(tmp_path, monkeypatch):
    hak = julkaise(tmp_path / "t", teot=rivit(teko(1), teko(2)))
    polku = hak / "teot.jsonl"
    alkup = os.pread

    def lisaa_ensin(fd, n, offset):
        with open(polku, "ab") as f:
            f.write(rivit(teko(3)))
        monkeypatch.setattr(os, "pread", alkup)
        return alkup(fd, n, offset)
    monkeypatch.setattr(os, "pread", lisaa_ensin)
    t = toiminta.lue_toiminta(hak, omistajat=OMAT)
    assert t.virheet == () and [x["mita"] for x in t.teot] == ["teko 2", "teko 1"]  # avaushetken koko
    assert len(toiminta.lue_toiminta(hak, omistajat=OMAT).teot) == 3

    def katkaise_ensin(fd, n, offset):
        os.truncate(polku, 10)
        monkeypatch.setattr(os, "pread", alkup)
        return alkup(fd, n, offset)
    monkeypatch.setattr(os, "pread", katkaise_ensin)
    t = toiminta.lue_toiminta(hak, omistajat=OMAT)
    assert t.teot is None and "muuttui" in t.virheet[0]


def test_tilarivi():
    assert toiminta.tilarivi(None, NYT) is None
    assert toiminta.tilarivi(toiminta.Toiminta("not_published", "x"), NYT)["seis"] is None
    assert toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=None), NYT)["teksti"] == "Tila ei tiedossa"
    perus = {"seis": False, "seis_aika": None, "seis_kuka": None, "vuoro": None}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=perus), NYT)
    assert (rivi["teksti"], rivi["savy"], rivi["seis"]) == ("Käynnissä", "success", False)
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "seis": True, "seis_aika": "2026-11-18T22:15:00+00:00",
                                                                  "seis_kuka": "elias"}), NYT)
    assert (rivi["teksti"], rivi["savy"], rivi["seis"]) == ("Seis", "danger", True) and "klo 00.15 (elias)" in rivi["selitys"]
    vuoro = {"laji": "yoajo", "nimi": "Yöajo", "saie": 12, "istunto": 3, "alkoi": "2026-11-19T02:00:00+02:00",
             "paattyy": "2026-11-19T04:55:00+02:00"}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), NYT)
    assert rivi["teksti"] == "Yöajo käynnissä klo 04.55 asti" and rivi["seis"] is False
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), datetime(2026, 11, 19, 3, 0, tzinfo=UTC))
    assert rivi["teksti"] == "Yöajon aika ylittyi" and rivi["savy"] == "warning"


# --- Sivu -------------------------------------------------------------------------------------------------------------

def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_sivu_esimerkkitilassa_ilman_lomakkeita():
    r = asiakas().get("/hub/ilmari?demo=1")
    assert r.status_code == 200 and "Ilmari nyt." in r.text and "Esimerkkitila" in r.text
    assert "Työvuoro käynnissä klo 17.05 asti" in r.text and "työvuoron työt säikeeseen 13" in r.text
    assert "Rajatesti" in r.text and "Läpi" in r.text and "/ilmari/vuoro" not in r.text
    assert 'action="' not in r.text and "Refresh" not in r.headers
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<script>alert" not in r.text
    assert "&lt;b&gt;ei html&lt;/b&gt;" in r.text and "<b>ei html" not in r.text
    assert r.text.index("Loin tehtavat.md") < r.text.index("Lisää kuvareitille")  # uusin ensin
    assert "Peruminen:" in r.text and "Ravintopolun kuvareitti valmiiksi" in r.text
    # Pala 1b: yön raportti Tila-paneelin jälkeen, koodattuna; rajatestin työ ei ole linkki (työtä ei julkaista)
    sivu = BeautifulSoup(r.text, "html.parser")
    raportti = sivu.find("section", attrs={"aria-labelledby": "ilmari-raportti"})
    assert raportti is not None and "Viimeisin raportti" in raportti.h2.get_text()
    assert r.text.index('id="ilmari-tila"') < r.text.index('id="ilmari-raportti"') < r.text.index('id="ilmari-yoajo"')
    teksti = raportti.find("div", class_="safe-text")
    assert teksti.get_text().startswith("Aamuraportti 19.11.\n\nTehty\n") and not teksti.find_all(True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; näkyy tekstinä" in r.text and "Yöajo · " in raportti.get_text()
    assert "Koko keskustelu: Keskustelu → kansio Yöajot" in " ".join(raportti.get_text().split())
    assert 'href="/hub/kehita/43?' in r.text and 'href="/hub/kehita/101' not in r.text and "työ 101" in r.text


def test_sivu_ilman_lahdetta():
    r = asiakas().get("/hub/ilmari")
    assert r.status_code == 200 and "lähdettä ei ole määritetty" in r.text and "<form" not in r.text


def test_ilmari_nyt_on_valikossa_ja_puhelimen_alapalkissa():
    r = asiakas().get("/hub?demo=1")
    alapalkki = r.text.split('class="bottom-nav"')[1].split("</nav>")[0]
    assert 'href="/hub/ilmari' in alapalkki and "Ilmari nyt" in alapalkki and 'href="/hub/kehita' in alapalkki
    assert 'aria-current="page"' in asiakas().get("/hub/ilmari?demo=1").text.split('class="bottom-nav"')[1]


def tuotanto(tmp_path, monkeypatch, toiminta_hak: Path, keskustelu: dict | None = None, polku: str = "/ilmari"):
    """Tuotantotila (Serve, identiteetti) testijulkaisulla: toiminta ja keskustelu tmp-hakemistoista."""
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: OMAT)
    monkeypatch.setattr(toiminta, "OLETUS", toiminta_hak)
    k = tmp_path / "keskustelu"
    if keskustelu is not None:
        k.mkdir()
        (k / "viestit.json").write_text(json.dumps({"muoto": "aiops-keskustelu-v1", "paivitetty": "2026-11-19T01:00:00+00:00",
                                                    "viimeisin": 0, "malli": keskustelu, "viestit": []}))
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", k)
    root = tmp_path / "ajot"
    root.mkdir(exist_ok=True)
    config = parse_config({"hub": {"rp_id": RP, "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        return client.get(polku, headers=SERVE)


def lomakkeet(r) -> dict[str, dict[str, str]]:
    """{action: {kenttä: arvo}}; tarkistaa samalla, että jokainen lomake on POST gatewaylle ja mahtuu sen 8 kenttään."""
    tulos = {}
    for f in BeautifulSoup(r.text, "html.parser").find_all("form"):
        assert f["method"] == "post" and f["action"].startswith(f"https://{RP}/ilmari/")
        kentat = f.find_all(["input", "textarea", "select"])
        assert len(kentat) <= 8
        tulos[f["action"][len(f"https://{RP}"):]] = {k["name"]: (k.get("value") or k.get_text()) for k in kentat}
    return tulos


def test_tuotannossa_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "toiminta"))
    assert r.status_code == 200 and "Refresh" not in r.headers and "form-action 'self'" in r.headers["content-security-policy"]
    f = lomakkeet(r)
    assert set(f) == {"/ilmari/seis", "/ilmari/asetukset", "/ilmari/tavoitteet", "/ilmari/ohje/3/poista",
                      "/ilmari/ohje/9/poista", "/ilmari/rajatesti", "/ilmari/vuoro"}  # ei Jatkaa, kun ei seis-tilassa
    assert all(kentat["paluu"] == "hub" for kentat in f.values()) and f["/ilmari/vuoro"] == {"paluu": "hub"}
    assert f["/ilmari/asetukset"] == {"yoajo_paalla": "1", "yoajo_kello": "03:30", "paluu": "hub"}
    assert f["/ilmari/tavoitteet"]["rivit"] == "Kuvareitti valmiiksi\nAamuraportti <i>7</i>"
    sivu = BeautifulSoup(r.text, "html.parser")
    assert not sivu.find("input", attrs={"name": "yoajo_paalla"}).has_attr("checked")  # yöajo pois päältä
    assert not sivu.find("form", action=f"https://{RP}/ilmari/rajatesti").button.has_attr("disabled")
    assert "Ei läpi" in r.text and "&lt;b&gt;auki&lt;/b&gt;" in r.text and "Käynnissä" in r.text
    assert not sivu.find_all("script") and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text


def test_tuotannossa_seis_jatka_ja_tuntematon_tila(tmp_path, monkeypatch):
    seis = {**TILA, "seis": True, "seis_aika": "2026-11-19T01:00:00+00:00", "seis_kuka": "elias"}
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a", tila=seis), keskustelu={"dsh_tyo": 44, "tila": "running"})
    f = lomakkeet(r)
    assert "/ilmari/jatka" in f and "/ilmari/seis" not in f and "Pysäytetty klo 03.00 (elias)" in r.text
    assert BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/rajatesti").button.has_attr("disabled")
    assert "dsh-työ 44" in r.text
    # julkaisematon tai rikkinäinen tila: Seis ja Jatka molemmat tarjolla, gateway päättää
    for hak in (tmp_path / "ei", julkaise(tmp_path / "b", tila=b"{rikki")):
        r = tuotanto(tmp_path, monkeypatch, hak)
        f = lomakkeet(r)
        assert {"/ilmari/seis", "/ilmari/jatka"} <= set(f) and "Tila ei tiedossa" in r.text


# --- Pala 1b (18.11.2026): työvuoro, Töihin nyt, viimeisin raportti ja tekolokin työlinkit ---------------------------

def kirjoita_kuin_gateway(hak: Path, nimi: str, sisalto: dict) -> None:
    """Sama tapa kuin aiops src/aiops/toiminta.py _kirjoita_json: indent=1, ensure_ascii=False, rivinvaihto loppuun,
    väliaikaistiedosto tilassa 0640, fsync ja rename."""
    data = json.dumps(sisalto, ensure_ascii=False, indent=1).encode("utf-8") + b"\n"
    tmp = hak / f".{nimi}.uusi"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o640)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(tmp, hak / nimi)


def test_raportin_kentat_kiinnitetty_gatewayn_kanssa(tmp_path):
    """Ristiinlukittu aiopsin kanssa (Pala 1b, sopimus gateway ↔ Hub): gateway kirjoittaa vuoron päättyessä
    raportti.json:n täsmälleen näillä kentillä ja lajeilla; teksti on Ilmarin viesti (enintään 8000 merkkiä, vain
    rivinvaihto sallittu, gatewayn näkyviksi koodaamat merkit kirjaimellisina \\uXXXX-jonoina)."""
    assert toiminta.RAPORTTI_KENTAT == frozenset({"versio", "aika", "saie", "laji", "teksti"})
    assert set(toiminta.VUOROT) == {"yoajo", "tyovuoro"} and toiminta.RAPORTTI_MAX == 8000
    assert toiminta.RAJAT["raportti.json"] == 64 * 1024
    for laji, nimi in (("yoajo", "Yöajo"), ("tyovuoro", "Työvuoro")):
        hak = julkaise(tmp_path / laji)
        alku = "Raportti <script>alert(1)</script>\nrivi \\u001b[31m\n"
        teksti = alku + "ä" * (8000 - len(alku))
        kirjoita_kuin_gateway(hak, "raportti.json", {"versio": 1, "aika": "2026-11-19T16:58:03+02:00", "saie": 14,
                                                     "laji": laji, "teksti": teksti})
        assert (hak / "raportti.json").stat().st_mode & 0o777 == 0o640
        t = toiminta.lue_toiminta(hak, omistajat=OMAT)
        assert t.virheet == () and t.raportti_virhe is False
        assert t.raportti == {"aika": "2026-11-19T16:58:03+02:00", "saie": 14, "laji": laji, "nimi": nimi, "teksti": teksti}


@pytest.mark.parametrize("arvo", [
    {**RAPORTTI, "lisa": 1},
    {k: v for k, v in RAPORTTI.items() if k != "saie"},
    {**RAPORTTI, "versio": 2},
    {**RAPORTTI, "laji": "paiva"},                      # tuntematon laji on kelvoton tiedosto
    {**RAPORTTI, "laji": None},
    {**RAPORTTI, "saie": 0},
    {**RAPORTTI, "saie": "12"},
    {**RAPORTTI, "saie": True},
    {**RAPORTTI, "aika": "2026-11-19T04:40:00"},       # ei aikavyöhykettä
    {**RAPORTTI, "aika": None},
    {**RAPORTTI, "teksti": "x" * 8001},
    {**RAPORTTI, "teksti": " \n "},
    {**RAPORTTI, "teksti": ["lista"]},
    {**RAPORTTI, "teksti": "väri\x1b[31m"},
    {**RAPORTTI, "teksti": "suunta ‮ käännetty"},
    b'{"versio": 1, "versio": 1, "aika": "2026-11-19T04:40:00+02:00", "saie": 1, "laji": "yoajo", "teksti": "x"}',
    b"{ei json",
    b"[" * 30000 + b"]" * 30000,
    json.dumps(RAPORTTI).encode() + b" " * (64 * 1024),  # yli 64 KiB
], ids=lambda v: type(v).__name__)
def test_kelvoton_raportti_ei_kaada_sivua(tmp_path, arvo):
    """Kielletty suunta: rikkinäinen raportti näkyy virheenä ("Raporttia ei voi lukea"), muu tila ja Seis näkyvät."""
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", tila={**TILA, "seis": True}, raportti=arvo), omistajat=OMAT)
    assert t.tila == "ready" and t.raportti is None and t.raportti_virhe is True
    assert len(t.virheet) == 1 and t.virheet[0].startswith("raportti.json")
    assert t.tilanne["seis"] is True and t.asetukset is not None and len(t.teot) == 2


def test_raportti_linkkina_ei_kelpaa(tmp_path):
    hak = julkaise(tmp_path / "t")
    (tmp_path / "muu.json").write_text(json.dumps(RAPORTTI))
    (hak / "raportti.json").symlink_to(tmp_path / "muu.json")
    t = toiminta.lue_toiminta(hak, omistajat=OMAT)
    assert t.raportti is None and t.raportti_virhe is True and t.tilanne is not None


def test_tilarivi_tyovuoro_ja_toihin_nyt():
    perus = {"seis": False, "seis_aika": None, "seis_kuka": None, "vuoro": None, "vuoro_virhe": False}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=perus), NYT)
    assert rivi["toihin"] is True and rivi["teksti"] == "Käynnissä"   # sallittu: ei seis, ei vuoroa
    vuoro = {"laji": "tyovuoro", "nimi": "Työvuoro", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T02:40:00+02:00",
             "paattyy": "2026-11-19T04:05:00+02:00"}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), NYT)
    assert rivi["teksti"] == "Työvuoro käynnissä klo 04.05 asti" and "työvuoron työt säikeeseen 14" in rivi["selitys"]
    assert rivi["toihin"] is False and rivi["seis"] is False
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), datetime(2026, 11, 19, 2, 6, tzinfo=UTC))
    assert rivi["teksti"] == "Työvuoron aika ylittyi" and rivi["toihin"] is False
    # kielletty: Seis, rikkinäinen vuoro, tuntematon tila tai puuttuva tieto piilottaa napin
    for tilanne in ({**perus, "seis": True}, {**perus, "vuoro_virhe": True},
                    {k: v for k, v in perus.items() if k != "vuoro_virhe"}):
        assert toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=tilanne), NYT)["toihin"] is False
    assert toiminta.tilarivi(toiminta.Toiminta("error", "x"), NYT)["toihin"] is False
    assert toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=None), NYT)["toihin"] is False


def test_tyovuoro_tila_json_luetaan(tmp_path):
    vuoro = {"laji": "tyovuoro", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T15:40:00+02:00",
             "paattyy": "2026-11-19T17:05:00+02:00"}
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", tila={**TILA, "vuoro": vuoro}), omistajat=OMAT)
    assert t.virheet == () and t.tilanne["vuoro"] == {**vuoro, "nimi": "Työvuoro"}


def test_tekolokin_tyolinkki_vain_tyoriveille(tmp_path, monkeypatch):
    """Linkki Kehitä-sivulle vain riveillä, joiden työ julkaistaan siellä. tyo_alkoi kirjoitetaan kuten gateway sen
    kirjoittaa: lähde ilmari (teksti on mallin), työn numero gatewayn. Rajatestin rivit (myös Töihin nyt -pyynnön
    raukeaminen) ja Ilmarin kirjaukset näyttävät numeron tekstinä."""
    teot = rivit(teko(1, lahde="ilmari", laji="tyo_alkoi", tyo=11), teko(2, laji="tyo_paattyi", tyo=12),
                 teko(3, laji="tyo_peruttu", tyo=13), teko(4, laji="rajatesti", tyo=14),
                 teko(5, laji="rajatesti_tulos", tyo=15), teko(6, lahde="ilmari", laji="kirjaus", tyo=16),
                 teko(7, laji="tyovuoro_estetty", tyo=17), teko(8, laji="tyo_alkoi"))
    t = toiminta.lue_toiminta(julkaise(tmp_path / "t", teot=teot), omistajat=OMAT)
    assert {x["tyo"]: x["tyo_linkki"] for x in t.teot} == {11: True, 12: True, 13: True, 14: False, 15: False, 16: False,
                                                         17: False, None: False}
    r = tuotanto(tmp_path, monkeypatch, tmp_path / "t")
    linkit = {a["href"].split("?")[0] for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True)
              if "/kehita/" in a["href"]}
    assert linkit == {"/hub/kehita/11", "/hub/kehita/12", "/hub/kehita/13"}
    assert all(f"työ {n}" in r.text for n in (14, 15, 16, 17))


def test_tuotannossa_toihin_nyt(tmp_path, monkeypatch):
    """Sallittu: lomake gatewaylle (paluu=hub), kun Ilmari ei ole seis-tilassa eikä vuoroa ole. dsh-työ tai vanha yöajo
    näyttää napin harmaana syyn kanssa (gateway kieltäytyy joka tapauksessa)."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a"))
    nappi = BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button
    assert "Töihin nyt" in nappi.get_text() and not nappi.has_attr("disabled")
    assert "Ilmari tekee saman kierroksen kuin yöllä (rästit, itsearviointi, tutkimus, raportti), enintään 90 min." in r.text
    for n, (malli, syy) in enumerate((({"dsh_tyo": 44, "tila": "running"}, "Töihin nyt toimii, kun dsh-työ 44 on valmis."),
                                      ({"yoajo": True, "tila": "running"}, "Töihin nyt toimii, kun yöajo on päättynyt."))):
        (tmp_path / str(n)).mkdir()
        r = tuotanto(tmp_path / str(n), monkeypatch, julkaise(tmp_path / "a"), keskustelu=malli)
        assert BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button.has_attr("disabled")
        assert syy in r.text


def test_tuotannossa_toihin_nyt_rajatesti_ensin(tmp_path, monkeypatch):
    """Gateway palaa osoitteeseen ?toihin=rajatesti, kun Töihin nyt ajaa ensin rajatestin: sivu kertoo, että vuoro
    alkaa itsestään. Käynnissä oleva rajatesti (tekolokin uusin gatewayn rajatesti-rivi) näkyy ilman linkkiä, koska
    sitä ei julkaista Kehitä-sivulle, eikä sivu käske odottamaan dsh-työtä. Kielletty: kehitystyö saa linkin ja
    entisen syyn, eikä ilmoitusta näytetä ilman paluuparametria."""
    teot = rivit(teko(1, laji="rajatesti", tyo=57, miksi="työvuoron rajatesti: Elias painoi Töihin nyt (elias@github)"))
    for n, (dsh, polku) in enumerate(((57, "/ilmari?toihin=rajatesti"), (57, "/ilmari"), (58, "/ilmari"))):
        (tmp_path / str(n)).mkdir()
        r = tuotanto(tmp_path / str(n), monkeypatch, julkaise(tmp_path / f"a{n}", teot=teot),
                     keskustelu={"dsh_tyo": dsh, "tila": "running"}, polku=polku)
        sivu = BeautifulSoup(r.text, "html.parser")
        teksti = " ".join(sivu.get_text().split())
        linkit = {a["href"].split("?")[0] for a in sivu.find_all("a", href=True) if "/kehita/" in a["href"]}
        assert ("Töihin nyt vastaanotettu: rajatesti ajetaan ensin" in teksti) is (n == 0)
        assert sivu.find("form", action=f"https://{RP}/ilmari/vuoro").button.has_attr("disabled")
        if dsh == 57:
            assert "rajatesti (työ 57) käynnissä" in teksti and "/hub/kehita/57" not in linkit
            assert "Rajatesti (työ 57) on käynnissä: jos painoit jo Töihin nyt, työvuoro alkaa sen jälkeen itsestään." in teksti
            assert "Töihin nyt toimii, kun dsh-työ" not in teksti
        else:
            assert "/hub/kehita/58" in linkit and "rajatesti (työ" not in teksti
            assert "Töihin nyt toimii, kun dsh-työ 58 on valmis." in teksti
    # Osoite ei lukitse nappia: vanha ?toihin=rajatesti ilman käynnissä olevaa työtä jättää Töihin nyt käyttöön, ja
    # tuntematon arvo ei näytä ilmoitusta.
    for n, (polku, ilmoitus) in enumerate((("/ilmari?toihin=rajatesti", True), ("/ilmari?toihin=muu", False))):
        (tmp_path / f"x{n}").mkdir()
        r = tuotanto(tmp_path / f"x{n}", monkeypatch, julkaise(tmp_path / f"ax{n}"), polku=polku)
        assert ("vastaanotettu" in r.text) is ilmoitus
        nappi = BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button
        assert not nappi.has_attr("disabled")


@pytest.mark.parametrize("tila", [
    {**TILA, "seis": True, "seis_aika": "2026-11-19T01:00:00+00:00", "seis_kuka": "elias"},
    {**TILA, "vuoro": {"laji": "tyovuoro", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T15:40:00+02:00",
                       "paattyy": "2099-01-01T00:00:00+02:00"}},
    {**TILA, "vuoro": {"laji": "yoajo", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T02:00:00+02:00",
                       "paattyy": "2026-11-19T04:55:00+02:00"}},                    # aika ylittyi, vuoro yhä tilassa
    {**TILA, "vuoro": {"laji": "tyovuoro", "saie": 0}},                             # rikkinäinen vuoro
    b"{rikki",                                                                       # tila ei tiedossa
], ids=["seis", "tyovuoro", "ylittynyt", "rikki_vuoro", "rikki_tila"])
def test_tuotannossa_ei_toihin_nyt(tmp_path, monkeypatch, tila):
    """Kielletty: nappia ei näytetä Seis-tilassa, vuoron aikana eikä kun tilaa ei voi lukea; Seis näkyy silti."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a", tila=tila))
    f = lomakkeet(r)
    assert "/ilmari/vuoro" not in f and "Töihin nyt" not in r.text and ("/ilmari/seis" in f or "/ilmari/jatka" in f)


def test_tuotannossa_raportti_paneeli(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "ei"))
    assert "Viimeisin raportti" not in r.text  # puuttuva tiedosto: ei paneelia
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "rikki", raportti={**RAPORTTI, "laji": "x"}))
    assert "Viimeisin raportti" in r.text and "Raporttia ei voi lukea." in r.text and "/ilmari/seis" in lomakkeet(r)
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "ok", raportti={**RAPORTTI, "laji": "tyovuoro", "teksti":
                                                                            "Tein <script>alert(1)</script>\n<b>x</b>"}))
    sivu = BeautifulSoup(r.text, "html.parser")
    paneeli = sivu.find("section", attrs={"aria-labelledby": "ilmari-raportti"})
    assert "Työvuoro · " in paneeli.get_text() and "säie 12" in paneeli.get_text()
    assert paneeli.find("div", class_="safe-text").get_text() == "Tein <script>alert(1)</script>\n<b>x</b>"
    assert not sivu.find_all("script") and not paneeli.find_all("b")
    assert "Tein &lt;script&gt;alert(1)&lt;/script&gt;\n&lt;b&gt;x&lt;/b&gt;" in r.text
