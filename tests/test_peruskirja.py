"""Sääntöpaneeli: peruskirjan lukija, rajattu Markdown ja reitti /hub/saannot (aiops ADR-0013 tarkennus 2026-10-20,
ADR-0017).

Sallittu suunta: julkaisu luetaan, meta näkyy ja peruskirja renderöityy otsikoiksi, listoiksi, taulukoiksi ja koodiksi;
esimerkkitila on merkitty; Serven polku /saannot ohjautuu sivulle.
Kielletyt suunnat: väärä omistaja (tuotannossa vain root), tiivisteen tai koon ristiriita (kesken jäänyt julkaisu),
kelvoton meta.json, linkit, kovat linkit, kokoraja, ohjaus- ja suunnanohjausmerkit, ei-UTF-8 ja HTML peruskirjassa
(näkyy tekstinä, ei merkintänä).

Riippumattomat totuudet: tiedostojen muoto (aiopsin scripts/julkaise_peruskirja.py) ja jäsentimen odotetut rakenteet
on kirjoitettu tähän käsin; tiiviste lasketaan coreutilsin sha256sum-ohjelmalla.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import DEFAULT_RULES_DIR, parse_config
from ilmari_ui.peruskirja import jasenna, lue_peruskirja, osat

UID = os.getuid()
COMMIT = "0123456789abcdef0123456789abcdef01234567"
RP = "tyoasema.taild1a5b7.ts.net"
LOGIN = "Elkkuboi@github"
SERVE = {"x-forwarded-host": RP, "tailscale-user-login": LOGIN}
TEKSTI = """# Ilmarin säännöt (peruskirja)

- Tila: luonnos.

## Taso 1: Ehdottomat

### Laki (ei muutettavissa)

- **L1 — Ei todellisia ihmisiä.** Ei edes
  suostumuksella.
- **L2 — Ei alaikäisiä.** `ikäluokitin` aina.

---

| Sääntö | Nyt |
| --- | --- |
| S3 | `gpt-6.1-sol` |
"""


def _sha256sum(polku: Path) -> str:
    return subprocess.run(["sha256sum", str(polku)], capture_output=True, text=True, check=True).stdout.split()[0]


def julkaise(hakemisto: Path, teksti: str | bytes = TEKSTI, **muutokset) -> Path:
    """Kirjoittaa saman muotoisen julkaisun kuin aiopsin julkaise_peruskirja.py (käsin kirjoitettu muoto)."""
    hakemisto.mkdir(parents=True, exist_ok=True)
    data = teksti.encode("utf-8") if isinstance(teksti, str) else teksti
    (hakemisto / "saannot.md").write_bytes(data)
    meta = {"muoto": "aiops-peruskirja-v1", "lahde": "docs/saannot.md", "commit": COMMIT,
            "sha256": _sha256sum(hakemisto / "saannot.md"), "koko": len(data), "julkaistu": "2026-10-20T21:15:00+03:00"}
    meta.update(muutokset)
    for avain in [k for k, v in meta.items() if v is None]:
        del meta[avain]
    (hakemisto / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return hakemisto


# --------------------------------------------------------------------------------------------------
# Lukija
# --------------------------------------------------------------------------------------------------

def test_kelvollinen_julkaisu_luetaan(tmp_path):
    kirja = lue_peruskirja(julkaise(tmp_path / "peruskirja"), omistaja=UID)
    assert kirja.tila == "ready" and kirja.viesti is None
    assert kirja.meta["commit"] == COMMIT and kirja.meta["koko"] == len(TEKSTI.encode())
    assert kirja.lohkot[0] == {"tyyppi": "otsikko", "taso": 1, "osat": (("teksti", "Ilmarin säännöt (peruskirja)"),)}


def test_vaara_omistaja_hylataan(tmp_path):
    kirja = lue_peruskirja(julkaise(tmp_path / "peruskirja"), omistaja=UID + 4242)
    assert kirja.tila == "error" and "omistaja ei ole root" in kirja.viesti and kirja.lohkot == ()


@pytest.mark.skipif(UID != 0, reason="vaatii rootin: tiedoston omistajan vaihto")
@pytest.mark.parametrize("kohde", ["hakemisto", "saannot.md", "meta.json"])
def test_omistaja_tarkistetaan_hakemistolta_ja_kummaltakin_tiedostolta(tmp_path, kohde):
    hak = julkaise(tmp_path / "p")
    for polku in (hak, hak / "saannot.md", hak / "meta.json"):
        os.chown(polku, 4242, -1)
    os.chown(hak if kohde == "hakemisto" else hak / kohde, 4343, -1)
    kirja = lue_peruskirja(hak, omistaja=4242)
    assert kirja.tila == "error" and "omistaja ei ole root" in kirja.viesti
    os.chown(hak if kohde == "hakemisto" else hak / kohde, 4242, -1)
    assert lue_peruskirja(hak, omistaja=4242).tila == "ready"


def test_puuttuva_hakemisto_ei_ole_virhe_vaan_julkaisematon(tmp_path):
    kirja = lue_peruskirja(tmp_path / "ei-ole", omistaja=UID)
    assert kirja.tila == "not_published" and "deploy.sh" in kirja.viesti


@pytest.mark.parametrize("muutos", [
    {"sha256": "0" * 64},
    {"koko": 1},
])
def test_kesken_jaanyt_tai_ristiriitainen_julkaisu_ei_nay(tmp_path, muutos):
    kirja = lue_peruskirja(julkaise(tmp_path / "p", **muutos), omistaja=UID)
    assert kirja.tila == "error" and kirja.lohkot == ()


def test_vanha_meta_ja_uusi_teksti_ei_nay(tmp_path):
    hak = julkaise(tmp_path / "p")
    (hak / "saannot.md").write_text(TEKSTI + "- uusi rivi\n", encoding="utf-8")  # julkaisija vaihtoi tekstin, meta vanha
    kirja = lue_peruskirja(hak, omistaja=UID)
    assert kirja.tila == "error" and "kesken" in kirja.viesti


@pytest.mark.parametrize("muutos", [
    {"muoto": "aiops-peruskirja-v2"},
    {"lahde": "docs/muu.md"},
    {"commit": "0123456"},
    {"commit": COMMIT.upper()},
    {"sha256": "A" * 64},
    {"koko": "123"},
    {"julkaistu": "2026-10-20T21:15:00"},
    {"julkaistu": "eilen"},
    {"julkaistu": None},
    {"ylimaarainen": 1},
])
def test_kelvoton_meta_hylataan(tmp_path, muutos):
    kirja = lue_peruskirja(julkaise(tmp_path / "p", **muutos), omistaja=UID)
    assert kirja.tila == "error" and kirja.lohkot == ()


def test_meta_jossa_sama_kentta_kahdesti_hylataan(tmp_path):
    hak = julkaise(tmp_path / "p")
    teksti = (hak / "meta.json").read_text()
    (hak / "meta.json").write_text(teksti[:-1] + ', "commit": "' + "f" * 40 + '"}')
    assert lue_peruskirja(hak, omistaja=UID).tila == "error"


@pytest.mark.parametrize("data", [
    b"# x\x00\n", b"# x\x1b[31m\n", "# x\u202e\n".encode(), "# x\u2068\n".encode(), b"\xff\xfe# x\n",
])
def test_kielletty_merkki_tai_koodaus_hylataan(tmp_path, data):
    kirja = lue_peruskirja(julkaise(tmp_path / "p", data), omistaja=UID)
    assert kirja.tila == "error" and kirja.lohkot == ()


def test_kokoraja(tmp_path):
    assert lue_peruskirja(julkaise(tmp_path / "a", b"#" + b"a" * 65534 + b"\n"), omistaja=UID).tila == "ready"
    kirja = lue_peruskirja(julkaise(tmp_path / "b", b"#" + b"a" * 65535 + b"\n"), omistaja=UID)
    assert kirja.tila == "error" and "lukurajan" in kirja.viesti


def test_linkit_hylataan(tmp_path):
    oikea = julkaise(tmp_path / "oikea")
    (tmp_path / "linkki").symlink_to(oikea)
    assert lue_peruskirja(tmp_path / "linkki", omistaja=UID).tila == "error"
    hak = tmp_path / "p"
    hak.mkdir()
    (hak / "saannot.md").symlink_to(oikea / "saannot.md")
    (hak / "meta.json").write_bytes((oikea / "meta.json").read_bytes())
    assert lue_peruskirja(hak, omistaja=UID).tila == "error"
    kova = tmp_path / "k"
    kova.mkdir()
    os.link(oikea / "saannot.md", kova / "saannot.md")
    (kova / "meta.json").write_bytes((oikea / "meta.json").read_bytes())
    assert lue_peruskirja(kova, omistaja=UID).tila == "error"


@pytest.mark.parametrize("polku", ["suhteellinen", "/", "/srv/../etc"])
def test_kelvoton_polku(polku):
    assert lue_peruskirja(polku, omistaja=UID).tila == "error"


# --------------------------------------------------------------------------------------------------
# Rajattu Markdown: käsin kirjoitetut odotetut rakenteet
# --------------------------------------------------------------------------------------------------

def test_jasennin_peruskirjan_rakenne():
    assert jasenna(TEKSTI) == (
        {"tyyppi": "otsikko", "taso": 1, "osat": (("teksti", "Ilmarin säännöt (peruskirja)"),)},
        {"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
            {"osat": (("teksti", "Tila: luonnos."),), "sisennys": 0},)},
        {"tyyppi": "otsikko", "taso": 2, "osat": (("teksti", "Taso 1: Ehdottomat"),)},
        {"tyyppi": "otsikko", "taso": 3, "osat": (("teksti", "Laki (ei muutettavissa)"),)},
        {"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
            {"osat": (("lihava", "L1 — Ei todellisia ihmisiä."), ("teksti", " Ei edes suostumuksella.")), "sisennys": 0},
            {"osat": (("lihava", "L2 — Ei alaikäisiä."), ("teksti", " "), ("koodi", "ikäluokitin"),
                      ("teksti", " aina.")), "sisennys": 0},
        )},
        {"tyyppi": "viiva"},
        {"tyyppi": "taulukko", "otsikot": ((("teksti", "Sääntö"),), (("teksti", "Nyt"),)),
         "rivit": (((("teksti", "S3"),), (("koodi", "gpt-6.1-sol"),)),)},
    )


def test_jasennin_kappale_lainaus_koodi_ja_numeroitu():
    teksti = ("Eka rivi\ntoka rivi.\n\n> lainattu\n> jatkuu\n\n```\n<b>koodia</b>\n  sisennys\n```\n\n"
              "3. kolmas\n4. neljäs\n   jatko\n\n5. viides\n")
    assert jasenna(teksti) == (
        {"tyyppi": "kappale", "osat": (("teksti", "Eka rivi toka rivi."),)},
        {"tyyppi": "lainaus", "osat": (("teksti", "lainattu jatkuu"),)},
        {"tyyppi": "koodi", "teksti": "<b>koodia</b>\n  sisennys"},
        {"tyyppi": "lista", "jarjestetty": True, "alku": 3, "kohdat": (
            {"osat": (("teksti", "kolmas"),), "sisennys": 0},
            {"osat": (("teksti", "neljäs jatko"),), "sisennys": 0},
            {"osat": (("teksti", "viides"),), "sisennys": 0},
        )},
    )


def test_jasennin_sisakkainen_kohta_ja_vuosiluku_kappaleessa():
    assert jasenna("- yla\n  - ala\n- toinen\n") == ({"tyyppi": "lista", "jarjestetty": False, "alku": 1, "kohdat": (
        {"osat": (("teksti", "yla"),), "sisennys": 0}, {"osat": (("teksti", "ala"),), "sisennys": 1},
        {"osat": (("teksti", "toinen"),), "sisennys": 0})},)
    assert jasenna("Päätös tehtiin\n2026. vuonna.\n") == (
        {"tyyppi": "kappale", "osat": (("teksti", "Päätös tehtiin 2026. vuonna."),)},)


@pytest.mark.parametrize("teksti,odotettu", [
    ("**kesken", (("teksti", "**kesken"),)),
    ("`kesken", (("teksti", "`kesken"),)),
    ("****", (("teksti", "****"),)),
    ("a **b** c `d` e", (("teksti", "a "), ("lihava", "b"), ("teksti", " c "), ("koodi", "d"), ("teksti", " e"))),
    ("[linkki](https://example.org)", (("teksti", "[linkki](https://example.org)"),)),
    ("<script>x</script>", (("teksti", "<script>x</script>"),)),
])
def test_tekstinsisaiset_osat(teksti, odotettu):
    assert osat(teksti) == odotettu


def test_repon_ulkopuolinen_crlf_ja_tyhja():
    assert jasenna("# a\r\n\r\nb\r\n") == ({"tyyppi": "otsikko", "taso": 1, "osat": (("teksti", "a"),)},
                                          {"tyyppi": "kappale", "osat": (("teksti", "b"),)})
    assert jasenna("") == ()


# --------------------------------------------------------------------------------------------------
# Reitti kehitys- ja esimerkkitilassa
# --------------------------------------------------------------------------------------------------

def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), base_url="http://ilmari.local", client=None)


def test_sivu_renderoi_peruskirjan(tmp_path):
    with _client(Settings(rules_dir=julkaise(tmp_path / "p"))) as client:
        vastaus = client.get("/hub/saannot")
    assert vastaus.status_code == 200
    assert "script-src 'none'" in vastaus.headers["content-security-policy"]
    sivu = BeautifulSoup(vastaus.text, "html.parser")
    assert sivu.title.text == "Säännöt · Ilmari Hub"
    artikkeli = sivu.find("article", class_="rules-doc")
    assert [h.text for h in artikkeli.find_all(["h2", "h3", "h4"])] == [
        "Ilmarin säännöt (peruskirja)", "Taso 1: Ehdottomat", "Laki (ei muutettavissa)"]
    assert [s.text for s in artikkeli.find_all("strong")] == ["L1 — Ei todellisia ihmisiä.", "L2 — Ei alaikäisiä."]
    assert [c.text for c in artikkeli.find_all("code")] == ["ikäluokitin", "gpt-6.1-sol"]
    assert [th.text for th in artikkeli.find_all("th")] == ["Sääntö", "Nyt"]
    assert artikkeli.find("hr") is not None
    assert "0123456" in sivu.find("dl").text and "20.10.2026 klo 21.15" in sivu.find("dl").text
    assert sivu.find("a", href=lambda h: h and h.startswith("/hub/saannot")) is not None  # navigaatiossa


def test_html_peruskirjassa_nakyy_tekstina(tmp_path):
    vihamielinen = ('# <script>alert(1)</script>\n\n- **<img src=x onerror=alert(2)>** `<iframe>`\n\n'
                    '| <a href="javascript:x">a</a> |\n| --- |\n| <style>*{}</style> |\n\n<b>raaka</b>\n')
    with _client(Settings(rules_dir=julkaise(tmp_path / "p", vihamielinen))) as client:
        vastaus = client.get("/hub/saannot")
    assert vastaus.status_code == 200
    artikkeli = BeautifulSoup(vastaus.text, "html.parser").find("article", class_="rules-doc")
    assert artikkeli.find_all(["script", "img", "iframe", "a", "style", "b"]) == []
    assert "<script>alert(1)</script>" in artikkeli.text and "<b>raaka</b>" in artikkeli.text
    assert "&lt;script&gt;" in vastaus.text


def test_lahdetta_ei_maaritetty_ja_julkaisematon(tmp_path):
    with _client(Settings()) as client:
        assert "Peruskirjan lähdettä ei ole määritetty" in client.get("/hub/saannot").text
    with _client(Settings(rules_dir=tmp_path / "ei-ole")) as client:
        assert "Peruskirjaa ei ole julkaistu" in client.get("/hub/saannot").text


def test_rikkinainen_julkaisu_naytetaan_virheena_ei_sisaltona(tmp_path):
    with _client(Settings(rules_dir=julkaise(tmp_path / "p", sha256="0" * 64))) as client:
        teksti = client.get("/hub/saannot").text
    assert "Peruskirjaa ei voi näyttää turvallisesti" in teksti and "rules-doc" not in teksti


def test_esimerkkitila_on_merkitty():
    with _client(Settings(demo_enabled=True)) as client:
        teksti = client.get("/hub/saannot?demo=1").text
    assert "DEMO – ESIMERKKIDATA" in teksti and "Esimerkkitila: synteettinen peruskirja" in teksti
    assert "Esimerkkiperuskirja (synteettinen)" in teksti


def test_esimerkkiperuskirjan_tiiviste_tasmaa():
    hak = Path(__file__).resolve().parents[1] / "src" / "ilmari_ui" / "demo" / "peruskirja"
    meta = json.loads((hak / "meta.json").read_text())
    assert meta["sha256"] == _sha256sum(hak / "saannot.md")


# --------------------------------------------------------------------------------------------------
# Tuotantotila
# --------------------------------------------------------------------------------------------------

def _tuotanto(tmp_path: Path, rules: Path | None) -> TestClient:
    ajot = tmp_path / "ajot"
    ajot.mkdir(exist_ok=True)
    hub = {"rp_id": RP, "julkaisut": str(ajot), "kayttajat": {LOGIN: "elias"}}
    if rules is not None:
        hub["peruskirja"] = str(rules)
    config = parse_config({"hub": hub})
    return TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                      client=None)


def test_tuotannossa_vain_rootin_julkaisu_kelpaa(tmp_path):
    rules = julkaise(tmp_path / "peruskirja")  # testin käyttäjän kirjoittama
    if UID == 0:  # rootina ajettaessa julkaisu annetaan toiselle käyttäjälle, jotta kielletty suunta testautuu
        for polku in (rules, rules / "saannot.md", rules / "meta.json"):
            os.chown(polku, 4242, -1)
    with _tuotanto(tmp_path, rules) as client:
        vastaus = client.get("/saannot", headers=SERVE)  # Serve poistaa etuliitteen /hub
        assert vastaus.status_code == 200
        assert BeautifulSoup(vastaus.text, "html.parser").title.text == "Säännöt · Ilmari Hub"
        assert "omistaja ei ole root" in vastaus.text and "rules-doc" not in vastaus.text
        if UID == 0:  # sallittu suunta: rootin julkaisema näkyy
            for polku in (rules, rules / "saannot.md", rules / "meta.json"):
                os.chown(polku, 0, -1)
            assert "rules-doc" in client.get("/saannot", headers=SERVE).text


def test_tuotannon_vartija_koskee_saantosivua(tmp_path):
    with _tuotanto(tmp_path, julkaise(tmp_path / "peruskirja")) as client:
        assert client.get("/saannot", headers={**SERVE, "tailscale-user-login": "muu@github"}).status_code == 403
        assert client.post("/saannot", headers=SERVE).status_code == 405


def test_tuotannon_oletuspolku_ja_asetusten_ristiriita(tmp_path):
    config = parse_config({"hub": {"rp_id": RP, "julkaisut": "/srv/aiops/ilmari/ajot", "kayttajat": {LOGIN: "elias"}}})
    assert config.rules_dir == DEFAULT_RULES_DIR == Path("/srv/aiops/ilmari/peruskirja")
    with pytest.raises(ValueError, match="peruskirjan polku"):
        Settings(runs_dir=config.runs_dir, rules_dir=tmp_path, identity=config)
