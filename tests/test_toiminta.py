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
    assert (rivi["teksti"], rivi["savy"], rivi["seis"], rivi["kaynnissa"]) == ("Vapaa", "success", False, False)
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "seis": True, "seis_aika": "2026-11-18T22:15:00+00:00",
                                                                  "seis_kuka": "elias"}), NYT)
    assert (rivi["teksti"], rivi["savy"], rivi["seis"]) == ("Seis", "danger", True) and "klo 00.15 (elias)" in rivi["selitys"]
    vuoro = {"laji": "yoajo", "nimi": "Yöajo", "saie": 12, "istunto": 3, "alkoi": "2026-11-19T02:00:00+02:00",
             "paattyy": "2026-11-19T04:55:00+02:00"}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), NYT)
    assert rivi["teksti"] == "Yöajo klo 04.55 asti" and rivi["seis"] is False and rivi["kaynnissa"] is True
    assert rivi["selitys"] == "Ilmari tekee yön työt säikeeseen 12."
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), datetime(2026, 11, 19, 3, 0, tzinfo=UTC))
    assert rivi["teksti"] == "Yöajon aika ylittyi" and rivi["savy"] == "warning" and rivi["kaynnissa"] is True
    # käyttöliittymän teksteissä ei jargonia (Hub juureksi 18.11.2026)
    for tilanne in (perus, {**perus, "seis": True}, {**perus, "vuoro": vuoro}):
        r = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne=tilanne), NYT)
        assert not any(sana in (r["teksti"] + r["selitys"]).lower() for sana in ("gateway", "julkais", "dsh", "kontti"))
    assert "gateway" not in toiminta.tilarivi(toiminta.Toiminta("error", "x"), NYT)["selitys"].lower()


# --- Sivut: Nyt (/hub, juuri) ja Asetukset (Hub juureksi 18.11.2026) -------------------------------------------------

def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_nyt_esimerkkitilassa_ilman_lomakkeita():
    r = asiakas().get("/hub?demo=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    teksti = " ".join(sivu.get_text(" ").split())
    assert r.status_code == 200 and "Esimerkkitila" in r.text and "<form" not in r.text and 'action="' not in r.text
    tila = sivu.find("p", class_="state-word")
    assert " ".join(tila.get_text().split()) == "Työvuoro klo 17.05 asti" and tila.find("span", class_="dot dot--live")
    assert "Ilmari tekee työvuoron työt säikeeseen 13. Malli on käynnissä, ei työtä kesken." in teksti
    assert r.headers.get("Refresh") == "30"                      # vuoro käynnissä: sivu päivittyy itsestään
    assert [b.get_text() for b in sivu.select(".state .actions button")] == ["Seis"]   # vuoron aikana ei Töihin nyt
    # odottaa sinua: esimerkin työ 98 odottaa hyväksyntää
    odottaa = sivu.find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert [a["href"] for a in odottaa.select("a.row")] == ["/hub/kehita/98?demo=1"] and "hyväksy" in odottaa.get_text()
    # raportti tekstinä, nimi ja aika otsikon reunassa
    raportti = sivu.find("section", attrs={"aria-labelledby": "h-raportti"})
    assert raportti.find("span", class_="aside").get_text() == "Yöajo 19.11. klo 04.40"
    laatikko = raportti.find("div", class_="sheet pre")
    assert laatikko.get_text().startswith("Aamuraportti 19.11.\n\nTehty\n") and not laatikko.find_all(True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; näkyy tekstinä" in r.text and "<script>alert" not in r.text
    # teot: uusin ensin, jokainen avattava rivi; työlinkki vain julkaistuille töille
    teot = sivu.find("section", attrs={"aria-labelledby": "h-teot"})
    rivit = teot.select("ol.rows.log > li > details")
    assert len(rivit) == 9 and not teot.find("details", class_="fold")
    assert "Työvuoro alkoi" in rivit[0].summary.get_text() and rivit[0].find("time").get_text() == "15.40"
    assert 'href="/hub/kehita/43?demo=1"' in r.text and 'href="/hub/kehita/101' not in r.text and "työ 101" in r.text
    assert "Peruminen:" in r.text and "kone" in teot.get_text() and "gateway" not in teot.find("span", class_="who").get_text()
    # muualle: esimerkkitilassa linkit eivät vie mihinkään
    muualle = sivu.find("section", attrs={"aria-labelledby": "h-muualle"})
    assert [(a.get_text(), a["href"]) for a in muualle.find_all("a")] == [("Ravintopolku ↗", "#"), ("Hahmo ↗", "#")]
    assert r.text.index('id="h-tila"') < r.text.index('id="h-odottaa"') < r.text.index('id="h-raportti"') \
        < r.text.index('id="h-teot"') < r.text.index('id="h-muualle"')


def test_nyt_ilman_lahdetta():
    r = asiakas().get("/hub")
    assert r.status_code == 200 and "Ilmarin tila ei ole saatavilla" in r.text and "<form" not in r.text
    assert "Odottaa sinua" not in r.text and "Muualle" not in r.text and "Refresh" not in r.headers


def test_vanha_ilmari_nyt_ohjautuu_juureen_kysely_mukana():
    c = asiakas()
    for vanha, uusi in (("/hub/ilmari", "/hub"), ("/hub/ilmari?toihin=rajatesti", "/hub?toihin=rajatesti"),
                        ("/hub/ilmari?demo=1", "/hub?demo=1")):
        r = c.get(vanha, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == uusi


def tuotanto(tmp_path, monkeypatch, toiminta_hak: Path, keskustelu: dict | None = None, polku: str = "/"):
    """Tuotantotila (Serve, identiteetti) testijulkaisulla: toiminta ja keskustelu tmp-hakemistoista."""
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: OMAT)
    monkeypatch.setattr(toiminta, "OLETUS", toiminta_hak)
    k = tmp_path / "keskustelu"
    if keskustelu is not None:
        k.mkdir()
        (k / "viestit.json").write_text(json.dumps({"muoto": "aiops-keskustelu-v1", "paivitetty": "2026-11-19T01:00:00+00:00",
                                                    "viimeisin": 0, "malli": keskustelu, "viestit": []}))
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", k)
    if not Path(kehitys.OLETUS).exists():
        Path(kehitys.OLETUS).mkdir(parents=True)   # töiden hakemisto on olemassa (tyhjä), ellei testi aseta omaa
    config = parse_config({"hub": {"rp_id": RP, "julkaisut": str(tmp_path / "ajot"), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None) as client:
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


def test_tuotannossa_nyt_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    """Nyt-sivulla vain tilan ohjaus: Töihin nyt ja Seis (Jatka vain Seis-tilassa). Muut lomakkeet ovat Asetuksissa."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "toiminta"))
    assert r.status_code == 200 and "Refresh" not in r.headers and "form-action 'self'" in r.headers["content-security-policy"]
    f = lomakkeet(r)
    assert f == {"/ilmari/vuoro": {"paluu": "hub"}, "/ilmari/seis": {"paluu": "hub"}}
    sivu = BeautifulSoup(r.text, "html.parser")
    assert [b.get_text() for b in sivu.select(".state .actions button")] == ["Töihin nyt", "Seis"]
    assert "btn--primary" in sivu.find("form", action=f"https://{RP}/ilmari/vuoro").button["class"]
    assert "btn--stop" in sivu.find("form", action=f"https://{RP}/ilmari/seis").button["class"]
    tila = " ".join(sivu.find("div", class_="state").get_text(" ").split())
    assert tila.startswith("Vapaa") and "Yöajo pois päältä." in tila and sivu.find("span", class_="dot dot--ok")
    # odottaa sinua: epäonnistunut rajatesti vie Asetuksiin
    odottaa = sivu.find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert [a["href"] for a in odottaa.select("a.row")] == ["/hub/asetukset#rajatesti"]
    assert "Rajatesti ei mennyt läpi" in odottaa.get_text() and "1 kohta ei läpi" in odottaa.get_text()
    assert not sivu.find_all("script") and "&lt;b&gt;x&lt;/b&gt;" in r.text
    # Muualle: Ravintopolku ja Hahmo omissa porteissaan samalla nimellä
    muualle = sivu.find("section", attrs={"aria-labelledby": "h-muualle"})
    assert [a["href"] for a in muualle.find_all("a")] == [f"https://{RP}:8443/", f"https://{RP}:8444/"]


def test_tuotannossa_seis_jatka_ja_tuntematon_tila(tmp_path, monkeypatch):
    seis = {**TILA, "seis": True, "seis_aika": "2026-11-19T01:00:00+00:00", "seis_kuka": "elias"}
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a", tila=seis), keskustelu={"dsh_tyo": 44, "tila": "running"})
    f = lomakkeet(r)
    assert set(f) == {"/ilmari/jatka"} and "Pysäytetty klo 03.00 (elias)" in r.text
    assert "btn--primary" in BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/jatka").button["class"]
    assert BeautifulSoup(r.text, "html.parser").find("span", class_="dot dot--stop")
    # julkaisematon tai rikkinäinen tila: Seis ja Jatka molemmat tarjolla, gateway päättää; virhe odottaa Eliasta
    for hak in (tmp_path / "ei", julkaise(tmp_path / "b", tila=b"{rikki")):
        r = tuotanto(tmp_path, monkeypatch, hak)
        f = lomakkeet(r)
        assert set(f) == {"/ilmari/seis", "/ilmari/jatka"} and "Tila ei tiedossa" in r.text
        odottaa = BeautifulSoup(r.text, "html.parser").find("section", attrs={"aria-labelledby": "h-odottaa"})
        assert odottaa is not None and ("Ilmarin tilaa ei voi lukea" in odottaa.get_text()
                                        or "Osaa tilasta ei voi lukea" in odottaa.get_text())


def test_tuotannossa_odottaa_sinua_vain_tarvittaessa_ja_enintaan_viisi(tmp_path, monkeypatch):
    """Sallittu: hyväksyttävä työ näkyy (linkki työn sivulle). Kielletty: kun mitään ei odota, osiota ei ole; yli viisi
    riviä katkaistaan."""
    kunnossa = {**TILA, "rajatesti": {**TILA["rajatesti"], "lapi": True, "kohdat": []}}
    (tmp_path / "x").mkdir()
    r = tuotanto(tmp_path / "x", monkeypatch, julkaise(tmp_path / "ok", tila=kunnossa))
    assert "Odottaa sinua" not in r.text
    juuri = tmp_path / "kehitys"
    for tyo in range(1, 8):
        (juuri / str(tyo)).mkdir(parents=True)
        (juuri / str(tyo) / "meta.json").write_text(json.dumps({
            "tyo": tyo, "toive": f"Toive {tyo}\nlisää", "luotu": "2026-11-18T12:00:00+00:00", "jattaja": "elias",
            "lahde": "aiops", "tila": "succeeded", "tiedostot": [],
            "tulos": {"paluukoodi": 0, "haara": f"ilmari/{tyo}", "commiteja": 1, "testit": {"paluukoodi": 0}}}))
    (juuri / "8").mkdir()
    (juuri / "8" / "meta.json").write_text(json.dumps({"tyo": 8, "toive": "Kesken", "tila": "running", "tiedostot": []}))
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    (tmp_path / "y").mkdir()
    r = tuotanto(tmp_path / "y", monkeypatch, julkaise(tmp_path / "ok2", tila=kunnossa))
    odottaa = BeautifulSoup(r.text, "html.parser").find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert [a["href"] for a in odottaa.select("a.row")] == [f"/hub/kehita/{n}" for n in (7, 6, 5, 4, 3)]
    assert "Toive 7" in odottaa.get_text() and "lisää" not in odottaa.get_text() and "Sinun toiveesi" in odottaa.get_text()
    assert "Kesken" not in odottaa.get_text() and r.headers.get("Refresh") == "30"   # työ 8 käynnissä: päivittyy


def test_tuotannossa_asetukset_lomakkeet_gatewaylle(tmp_path, monkeypatch):
    """Yöajo, tavoitteet, pysyvät ohjeet ja rajatesti Asetuksissa samoilla lomakkeilla ja kentillä kuin ennen."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "toiminta"), polku="/asetukset")
    assert r.status_code == 200 and "Refresh" not in r.headers   # ei automaattista päivitystä: tyhjentäisi lomakkeet
    f = lomakkeet(r)
    assert set(f) == {"/ilmari/asetukset", "/ilmari/tavoitteet", "/ilmari/ohje/3/poista", "/ilmari/ohje/9/poista",
                      "/ilmari/rajatesti"}
    assert all(kentat["paluu"] == "hub" for kentat in f.values())
    assert f["/ilmari/asetukset"] == {"yoajo_paalla": "1", "yoajo_kello": "03:30", "paluu": "hub"}
    assert f["/ilmari/tavoitteet"]["rivit"] == "Kuvareitti valmiiksi\nAamuraportti <i>7</i>"
    sivu = BeautifulSoup(r.text, "html.parser")
    assert not sivu.find("input", attrs={"name": "yoajo_paalla"}).has_attr("checked")  # yöajo pois päältä
    assert not sivu.find("form", action=f"https://{RP}/ilmari/rajatesti").button.has_attr("disabled")
    assert [s["id"] for s in sivu.find_all("section", id=True)] == ["yoajo", "tavoitteet", "ohjeet", "aivot",
                                                                      "rajatesti", "kone", "ulkoasu"]
    raja = sivu.find("section", id="rajatesti")
    assert "ei läpi" in raja.get_text() and "&lt;b&gt;auki&lt;/b&gt;" in r.text
    assert raja.find("details", class_="fold").summary.get_text() == "Kaikki kohdat (2)"
    assert not sivu.find_all("script") and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    muut = {a.get_text(): a["href"] for a in sivu.find("section", attrs={"aria-labelledby": "h-muut"}).find_all("a")}
    assert muut == {"Promptit ja säännöt": "/hub/kehotteet", "Dokumentit": "/hub/dokumentit",
                    "Kaikki työt (raaka lista)": f"https://{RP}/tyot", "Puhelimen passkey": f"https://{RP}/passkey"}


@pytest.mark.parametrize("hakemisto", ["ei", "suhteellinen"])
def test_tuotannossa_asetukset_lukuvirheessa_ilman_lomakkeita(tmp_path, monkeypatch, hakemisto):
    """Kielletty suunta: kun Ilmarin tilaa ei voi lukea (puuttuu, väärä omistaja, aikaraja), Asetuksissa ei ole yöajon,
    tavoitteiden, ohjeiden eikä rajatestin lomaketta: oletusarvoinen lomake (yöajo päällä 02.00, tyhjät tavoitteet)
    korvaisi tallennettaessa oikeat asetukset. Seis ja Jatka toimivat yhä Nyt-sivulla. (Sallittu suunta:
    test_tuotannossa_asetukset_lomakkeet_gatewaylle.)"""
    hak = tmp_path / "ei" if hakemisto == "ei" else Path("suhteellinen/polku")
    r = tuotanto(tmp_path, monkeypatch, hak, polku="/asetukset")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and lomakkeet(r) == {} and not sivu.find("textarea") and not sivu.find("input")
    assert [s["id"] for s in sivu.find_all("section", id=True)] == ["yoajo", "tavoitteet", "ohjeet", "aivot",
                                                                      "rajatesti", "kone", "ulkoasu"]
    tyhjat = {s["id"]: [p.get_text() for p in s.select("p.empty")] for s in sivu.find_all("section", id=True)}
    assert tyhjat["tavoitteet"] == ["Tavoitteita ei voi lukea."] and tyhjat["ohjeet"] == ["Ohjeita ei voi lukea."]
    assert len(tyhjat["yoajo"]) == 1 and tyhjat["rajatesti"] == ["Rajatestin tulosta ei voi lukea."]
    assert "Ei pysyviä ohjeita." not in r.text and "Aja rajatesti nyt" not in r.text
    nyt = tuotanto(tmp_path, monkeypatch, hak)
    assert set(lomakkeet(nyt)) == {"/ilmari/seis", "/ilmari/jatka"}


def test_tuotannossa_odottaa_sinua_kertoo_jos_toita_ei_voi_lukea(tmp_path, monkeypatch):
    """Sallittu: luettava (tyhjä) työhakemisto ei lisää riviä. Kielletty: lukematon työhakemisto ei jää hiljaa
    pois, vaan Odottaa sinua kertoo siitä ja vie Työt-sivulle."""
    kunnossa = {**TILA, "rajatesti": {**TILA["rajatesti"], "lapi": True, "kohdat": []}}
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a", tila=kunnossa))
    assert "Odottaa sinua" not in r.text
    tiedosto = tmp_path / "ei-hakemisto"
    tiedosto.write_text("x")
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", tiedosto)
    (tmp_path / "b").mkdir()
    r = tuotanto(tmp_path / "b", monkeypatch, julkaise(tmp_path / "a2", tila=kunnossa))
    odottaa = BeautifulSoup(r.text, "html.parser").find("section", attrs={"aria-labelledby": "h-odottaa"})
    assert [(a["href"], " ".join(a.get_text(" ").split())) for a in odottaa.select("a.row")] == \
        [("/hub/kehita", "! Töitä ei voi lukea päivitä")]


def test_tuotannossa_tila_kertoo_kesken_olevan_tyon(tmp_path, monkeypatch):
    """Vapaa-tilassa käynnissä oleva työ näkyy pääsanana linkkinä ja vilkkuvana pisteenä, ei vihreänä "Vapaa"."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a"), keskustelu={"dsh_tyo": 44, "tila": "running"})
    sivu = BeautifulSoup(r.text, "html.parser")
    tila = sivu.find("p", class_="state-word")
    assert " ".join(tila.get_text().split()) == "Työ 44 kesken" and tila.a["href"] == "/hub/kehita/44"
    assert tila.find("span", class_="dot dot--live") and not sivu.find("span", class_="dot--ok")
    assert " ".join(sivu.find("p", class_="state-text").get_text().split()) == "Malli on käynnissä. Yöajo pois päältä."
    (tmp_path / "x").mkdir()
    r = tuotanto(tmp_path / "x", monkeypatch, julkaise(tmp_path / "b"), keskustelu={"tila": "running"})
    tila = BeautifulSoup(r.text, "html.parser").find("p", class_="state-word")
    assert tila.get_text(strip=True) == "Vapaa" and tila.find("span", class_="dot dot--ok")


def test_teot_ilman_raakoja_tunnisteita_ja_paiva_vaihtuu():
    """Avatussa tekorivissä ei koodin tunnistetta (tyovuoro alkoi, yoajo paattyi); puhelimella päivä näkyy, kun se
    vaihtuu (rivin p.day, piilossa leveällä näytöllä, jossa päivä on joka rivillä)."""
    sivu = BeautifulSoup(asiakas().get("/hub?demo=1").text, "html.parser")
    lisat = " ".join(d.get_text(" ") for d in sivu.select(".log .more"))
    for raaka in ("tyovuoro", "yoajo", "tyo alkoi", "kirjaus", "_"):
        assert raaka not in lisat
    assert [p.get_text() for p in sivu.select(".log p.day")] == ["19.11.", "18.11."]


def test_tuotannossa_rajatesti_pois_kaytosta_kun_tyo_kesken(tmp_path, monkeypatch):
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a"), keskustelu={"dsh_tyo": 44, "tila": "running"},
                 polku="/asetukset")
    assert BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/rajatesti").button.has_attr("disabled")
    assert "Rajatestin voi ajaa, kun työ 44 on valmis." in r.text


def test_asetukset_esimerkkitilassa_ja_ilman_lahdetta():
    r = asiakas().get("/hub/asetukset?demo=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and "<form" not in r.text and "Refresh" not in r.headers
    assert sivu.find("textarea", attrs={"name": "rivit"}).get_text().startswith("Ravintopolun kuvareitti valmiiksi")
    assert "&lt;b&gt;ei html&lt;/b&gt;" in r.text and "Poista ohje, jota et tunnista." not in r.text   # ei selityksiä
    r = asiakas().get("/hub/asetukset")
    assert r.status_code == 200 and "Asetukset eivät ole saatavilla" in r.text and 'id="tavoitteet"' not in r.text


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
    assert rivi["toihin"] is True and rivi["teksti"] == "Vapaa"   # sallittu: ei seis, ei vuoroa
    vuoro = {"laji": "tyovuoro", "nimi": "Työvuoro", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T02:40:00+02:00",
             "paattyy": "2026-11-19T04:05:00+02:00"}
    rivi = toiminta.tilarivi(toiminta.Toiminta("ready", tilanne={**perus, "vuoro": vuoro}), NYT)
    assert rivi["teksti"] == "Työvuoro klo 04.05 asti" and "työvuoron työt säikeeseen 14" in rivi["selitys"]
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
    """Sallittu: lomake gatewaylle (paluu=hub), kun Ilmari ei ole seis-tilassa eikä vuoroa ole. Käynnissä oleva työ tai
    yöajo näyttää napin harmaana ja yhden rivin syyn (gateway kieltäytyy joka tapauksessa)."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "a"))
    nappi = BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button
    assert "Töihin nyt" in nappi.get_text() and not nappi.has_attr("disabled") and "Töihin nyt toimii" not in r.text
    for n, (malli, syy) in enumerate((({"dsh_tyo": 44, "tila": "running"}, "Töihin nyt toimii, kun työ 44 on valmis."),
                                      ({"yoajo": True, "tila": "running"}, "Töihin nyt toimii, kun yöajo on päättynyt."))):
        (tmp_path / str(n)).mkdir()
        r = tuotanto(tmp_path / str(n), monkeypatch, julkaise(tmp_path / "a"), keskustelu=malli)
        assert BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button.has_attr("disabled")
        assert syy in r.text


def test_tuotannossa_toihin_nyt_rajatesti_ensin(tmp_path, monkeypatch):
    """Gateway palaa osoitteeseen ?toihin=rajatesti (vanha /hub/ilmari ohjautuu juureen kysely mukana), kun Töihin nyt
    ajaa ensin rajatestin: sivu kertoo yhdellä rivillä, että vuoro alkaa itsestään. Käynnissä oleva rajatesti (tekolokin
    uusin gatewayn rajatesti-rivi) näkyy ilman linkkiä, koska sitä ei julkaista Työt-sivulle. Kielletty: kehitystyö saa
    linkin ja oman syyn, eikä ilmoitusta näytetä ilman paluuparametria."""
    teot = rivit(teko(1, laji="rajatesti", tyo=57, miksi="työvuoron rajatesti: Elias painoi Töihin nyt (elias@github)"))
    for n, (dsh, polku) in enumerate(((57, "/?toihin=rajatesti"), (57, "/"), (58, "/"))):
        (tmp_path / str(n)).mkdir()
        r = tuotanto(tmp_path / str(n), monkeypatch, julkaise(tmp_path / f"a{n}", teot=teot),
                     keskustelu={"dsh_tyo": dsh, "tila": "running"}, polku=polku)
        sivu = BeautifulSoup(r.text, "html.parser")
        teksti = " ".join(sivu.get_text().split())
        linkit = {a["href"].split("?")[0] for a in sivu.find_all("a", href=True) if "/kehita/" in a["href"]}
        assert ("Rajatesti ajetaan ensin (noin minuutti). Työvuoro alkaa sen jälkeen itsestään." in teksti) is (n == 0)
        assert sivu.find("form", action=f"https://{RP}/ilmari/vuoro").button.has_attr("disabled")
        assert r.headers.get("Refresh") == "30"   # työ käynnissä: sivu päivittyy, kunnes vuoro alkaa
        tila = sivu.find("p", class_="state-word")
        assert tila.find("span", class_="dot dot--live") and "Vapaa" not in tila.get_text()   # ei "Vapaa" työn aikana
        if dsh == 57:
            assert tila.get_text(strip=True) == "Rajatesti käynnissä" and "/hub/kehita/57" not in linkit
            assert ("Rajatesti on käynnissä. Jos painoit jo Töihin nyt, vuoro alkaa sen jälkeen itsestään." in teksti) is (n == 1)
            assert "Töihin nyt toimii, kun työ" not in teksti
        else:
            assert "/hub/kehita/58" in linkit and "rajatesti käynnissä" not in teksti.lower()
            assert " ".join(tila.get_text().split()) == "Työ 58 kesken" and tila.a["href"] == "/hub/kehita/58"
            assert "Töihin nyt toimii, kun työ 58 on valmis." in teksti
    # Osoite ei lukitse nappia: vanha ?toihin=rajatesti ilman käynnissä olevaa työtä jättää Töihin nyt käyttöön, ja
    # tuntematon arvo ei näytä ilmoitusta. (Vanhan osoitteen /hub/ilmari ohjaus: test_production.)
    for n, (polku, ilmoitus) in enumerate((("/?toihin=rajatesti", True), ("/?toihin=muu", False))):
        (tmp_path / f"x{n}").mkdir()
        r = tuotanto(tmp_path / f"x{n}", monkeypatch, julkaise(tmp_path / f"ax{n}"), polku=polku)
        assert ("Rajatesti ajetaan ensin" in r.text) is ilmoitus
        nappi = BeautifulSoup(r.text, "html.parser").find("form", action=f"https://{RP}/ilmari/vuoro").button
        assert not nappi.has_attr("disabled")
    # vuoron alettua ilmoitusta ei enää näytetä, vaikka osoitteessa on yhä ?toihin=rajatesti
    vuoro = {**TILA, "vuoro": {"laji": "tyovuoro", "saie": 14, "istunto": 5, "alkoi": "2026-11-19T15:40:00+02:00",
                               "paattyy": "2099-01-01T00:00:00+02:00"}}
    (tmp_path / "v").mkdir()
    r = tuotanto(tmp_path / "v", monkeypatch, julkaise(tmp_path / "av", tila=vuoro), polku="/?toihin=rajatesti")
    assert "Rajatesti ajetaan ensin" not in r.text and "Työvuoro klo" in r.text and r.headers.get("Refresh") == "30"


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
    assert "Viimeisin raportti" not in r.text  # puuttuva tiedosto: ei osiota
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "rikki", raportti={**RAPORTTI, "laji": "x"}))
    sivu = BeautifulSoup(r.text, "html.parser")
    assert "Viimeisin raportti" not in r.text and "/ilmari/seis" in lomakkeet(r)   # rikkinäinen: virhe odottaa Eliasta
    assert "raportti.json" in sivu.find("section", attrs={"aria-labelledby": "h-odottaa"}).get_text()
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "ok", raportti={**RAPORTTI, "laji": "tyovuoro", "teksti":
                                                                            "Tein <script>alert(1)</script>\n<b>x</b>"}))
    sivu = BeautifulSoup(r.text, "html.parser")
    osio = sivu.find("section", attrs={"aria-labelledby": "h-raportti"})
    assert osio.find("span", class_="aside").get_text() == "Työvuoro 19.11. klo 04.40"
    assert osio.find("div", class_="sheet pre").get_text() == "Tein <script>alert(1)</script>\n<b>x</b>"
    assert not sivu.find_all("script") and not osio.find_all("b")
    assert "Tein &lt;script&gt;alert(1)&lt;/script&gt;\n&lt;b&gt;x&lt;/b&gt;" in r.text


def test_tuotannossa_vanhemmat_teot_taitettuina(tmp_path, monkeypatch):
    """12 uusinta tekoa näkyvissä, loput taiton "Vanhemmat teot (N)" alla."""
    r = tuotanto(tmp_path, monkeypatch, julkaise(tmp_path / "t", teot=rivit(*(teko(n) for n in range(1, 31)))))
    osio = BeautifulSoup(r.text, "html.parser").find("section", attrs={"aria-labelledby": "h-teot"})
    nakyvat = osio.find("ol", class_="log", recursive=False)
    assert [li.summary.find_all("span")[-1].get_text() for li in nakyvat.find_all("li", recursive=False)] == \
        [f"teko {n}" for n in range(30, 18, -1)]
    taitto = osio.find("details", class_="fold")
    assert taitto.summary.get_text() == "Vanhemmat teot (18)" and len(taitto.select("ol.log > li")) == 18
