"""Tuotantotila (aiops ADR-0013): Tailscale Serven polku /hub, gatewayn vartijan säännöt ja etuliitteen palautus.

Riippumaton totuus on alla käsin kirjoitettu otsaketaulukko. Se perustuu kahteen havaintoon työasemalla:
gatewayn otsakevedos 1.10.2026 (aiops ADR-0010, tarkennus 7b-3) ja Hubin Serve-koe 14.10.2026, jossa koepolku
/hub-koe/ajot/x?y=1 saapui sokettiin muodossa /ajot/x?y=1. Pyynnöllä oli otsakkeet Host: localhost,
X-Forwarded-Host: tyoasema.taild1a5b7.ts.net ja Tailscale-User-Login: Elkkuboi@github. Serve korvasi asiakkaan
väärentämät arvot ja poisti asiakkaan Tailscale-Funnel-Request-otsakkeen, mutta päästi X-Forwarded-Prefixin läpi.
"""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import parse_config

RP = "tyoasema.taild1a5b7.ts.net"
LOGIN = "Elkkuboi@github"
RUN_ID = "20261013-235929-yo-q6"
SERVE = {"x-forwarded-host": RP, "tailscale-user-login": LOGIN, "x-forwarded-proto": "https",
         "x-forwarded-for": "100.67.5.28"}


@pytest.fixture
def publication(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("julkaisu") / "ajot"  # ASCII-polku: konfiguraatio hyväksyy vain nimimerkit
    run = root / RUN_ID
    run.mkdir(parents=True)
    (run / "meta.json").write_text(json.dumps({"alku": "2026-10-13T23:59:29", "malli": "q6"}), encoding="utf-8")
    (run / "raportti.md").write_text("# Ilmari: yöluenta\nRiippumaton tuotantotestin raportti.\n", encoding="utf-8")
    return root


@pytest.fixture
def config(publication: Path):
    return parse_config({"hub": {"rp_id": RP, "julkaisut": str(publication), "kayttajat": {LOGIN: "elias"}}})


@pytest.fixture
def client(config):
    settings = Settings(runs_dir=config.runs_dir, identity=config)
    with TestClient(create_app(settings), base_url="http://localhost", client=None) as c:
        yield c


def get(client: TestClient, path: str, headers=None, method: str = "GET"):
    return client.request(method, path, headers=headers if headers is not None else SERVE, follow_redirects=False)


# --------------------------------------------------------------------------------------------------
# Otsaketaulukko: (kuvaus, otsakkeet, metodi, odotettu tila)
# --------------------------------------------------------------------------------------------------

def _ilman(*nimet: str) -> dict:
    return {k: v for k, v in SERVE.items() if k not in nimet}


TAULUKKO = [
    ("Serven pyyntö", SERVE, "GET", 200),
    ("HEAD (vartija päästää; FastAPIn GET-reitit eivät vastaa HEADiin)", SERVE, "HEAD", 405),
    ("portti nimessä", SERVE | {"x-forwarded-host": f"{RP}:443"}, "GET", 200),
    ("isot kirjaimet nimessä", SERVE | {"x-forwarded-host": RP.upper()}, "GET", 200),
    ("navigointi osoiteriviltä", SERVE | {"sec-fetch-site": "none"}, "GET", 200),
    ("linkki gatewaysta", SERVE | {"sec-fetch-site": "same-origin"}, "GET", 200),
    ("oma alkuperä", SERVE | {"origin": f"https://{RP}"}, "GET", 200),
    ("X-Forwarded-Prefix ei vaikuta", SERVE | {"x-forwarded-prefix": "/muu"}, "GET", 200),
    ("POST", SERVE, "POST", 405),
    ("PUT", SERVE, "PUT", 405),
    ("DELETE", SERVE, "DELETE", 405),
    ("ei X-Forwarded-Hostia (Host localhost)", _ilman("x-forwarded-host"), "GET", 421),
    ("väärä nimi", SERVE | {"x-forwarded-host": "paha.example"}, "GET", 421),
    ("väärä portti", SERVE | {"x-forwarded-host": f"{RP}:8443"}, "GET", 421),
    ("nimen jatke", SERVE | {"x-forwarded-host": f"{RP}.paha.example"}, "GET", 421),
    ("Funnel", SERVE | {"tailscale-funnel-request": "?1"}, "GET", 403),
    ("ei tunnusta", _ilman("tailscale-user-login"), "GET", 403),
    ("tuntematon tunnus", SERVE | {"tailscale-user-login": "hyokkaaja@example.com"}, "GET", 403),
    ("tunnus eri kirjainkoolla", SERVE | {"tailscale-user-login": LOGIN.lower()}, "GET", 403),
    ("toinen sivusto", SERVE | {"sec-fetch-site": "cross-site"}, "GET", 403),
    ("sama sivusto, eri alkuperä", SERVE | {"sec-fetch-site": "same-site"}, "GET", 403),
    ("kotinäytön sovellus tai linkki muualta", SERVE | {"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate",
                                                       "sec-fetch-dest": "document"}, "GET", 200),
    ("linkki toisesta portista", SERVE | {"sec-fetch-site": "same-site", "sec-fetch-mode": "navigate",
                                          "sec-fetch-dest": "document"}, "GET", 200),
    ("upotus kehykseen muualta", SERVE | {"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate",
                                          "sec-fetch-dest": "iframe"}, "GET", 403),
    ("kuva toiselta sivustolta", SERVE | {"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors",
                                          "sec-fetch-dest": "image"}, "GET", 403),
    ("haku toiselta sivustolta", SERVE | {"sec-fetch-site": "cross-site", "sec-fetch-mode": "cors",
                                          "sec-fetch-dest": "empty"}, "GET", 403),
    ("vieras alkuperä", SERVE | {"origin": "https://paha.example"}, "GET", 403),
    ("alkuperä null", SERVE | {"origin": "null"}, "GET", 403),
    ("alkuperä ilman HTTPS:ää", SERVE | {"origin": f"http://{RP}"}, "GET", 403),
]


@pytest.mark.parametrize("kuvaus,otsakkeet,metodi,odotettu", TAULUKKO, ids=[r[0] for r in TAULUKKO])
def test_otsaketaulukko(client, kuvaus, otsakkeet, metodi, odotettu):
    assert get(client, "/", otsakkeet, metodi).status_code == odotettu


@pytest.mark.parametrize("nimi,arvo,odotettu", [
    ("x-forwarded-host", RP, 421),
    ("host", "localhost", 421),
    ("tailscale-user-login", LOGIN, 403),
    ("origin", f"https://{RP}", 403),
    ("sec-fetch-site", "same-origin", 403),
])
def test_toistettu_otsake_hylataan(client, nimi, arvo, odotettu):
    """Kelvollinen arvo kahdesti on silti hylkäys: yksikäsitteisyys ennen kaikkea."""
    otsakkeet = [(k, v) for k, v in SERVE.items() if k != nimi] + [(nimi, arvo), (nimi, arvo)]
    assert client.request("GET", "/", headers=otsakkeet).status_code == odotettu


def test_tcp_asiakas_hylataan_vaikka_otsakkeet_ovat_oikeat(config):
    settings = Settings(runs_dir=config.runs_dir, identity=config)
    with TestClient(create_app(settings), base_url="http://localhost") as tcp:  # oletusasiakas = TCP-osoite
        assert tcp.get("/", headers=SERVE).status_code == 403


def test_hylkays_ei_heijasta_syotetta(client):
    vastaus = get(client, "/", SERVE | {"x-forwarded-host": "<script>alert(1)</script>"})
    assert vastaus.status_code == 421 and "<script>" not in vastaus.text and RP in vastaus.text


# --------------------------------------------------------------------------------------------------
# Etuliitteen palautus: Serve toimittaa polut ilman etuliitettä /hub
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("serven_polku,otsikko", [
    ("/", "Koti"),
    ("/ajot", "Ajot ja raportit"),
    (f"/ajot/{RUN_ID}", "Ajon raportti"),
    ("/hyvaksynnat", "Hyväksynnät"),
    ("/asetukset", "Asetukset ja ulkoasu"),
])
def test_serven_polku_ohjautuu_hubin_sivulle(client, serven_polku, otsikko):
    vastaus = get(client, serven_polku)
    assert vastaus.status_code == 200
    assert BeautifulSoup(vastaus.text, "html.parser").title.text == f"{otsikko} · Ilmari Hub"


def test_ajon_raportti_luetaan_julkaisusta(client):
    assert "Riippumaton tuotantotestin raportti." in get(client, f"/ajot/{RUN_ID}").text


def test_staattinen_tiedosto_etuliitteen_kautta(client):
    vastaus = get(client, "/static/app.css")
    assert vastaus.status_code == 200 and vastaus.headers["content-type"].startswith("text/css")
    assert get(client, "/static/app.css", method="HEAD").status_code == 200  # vartija päästää HEADin


def test_etuliite_ei_tuplaannu(client):
    assert get(client, "/hub/ajot").status_code == 404  # selaimen osoite olisi /hub/hub/ajot


@pytest.mark.parametrize("otsakkeet", [SERVE, SERVE | {"x-forwarded-prefix": "/muu"}])
def test_kaikki_sisaiset_linkit_osoittavat_hubiin(client, otsakkeet):
    sivu = BeautifulSoup(get(client, "/", otsakkeet).text, "html.parser")
    osoitteet = [t.get("href") or t.get("action") or t.get("src") for t in sivu.select("[href], [action], [src]")]
    sisaiset = [o for o in osoitteet if o and o.startswith("/")]
    assert sisaiset and all(o == "/hub" or o.startswith(("/hub/", "/hub?")) for o in sisaiset), sisaiset
    assert not any("/muu" in o for o in sisaiset)


def test_tuotantotila_nayttaa_tyoaseman_eika_kehitysymparistoa(client):
    teksti = get(client, "/").text
    assert "Työasema" in teksti and "Kehitysympäristö" not in teksti and "KEHITYSYMPÄRISTÖ" not in teksti


# --------------------------------------------------------------------------------------------------
# Turvaotsakkeet jokaisessa vastauksessa (Hub jakaa alkuperän gatewayn kanssa, ADR-0013 kohta 5)
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("polku,otsakkeet,metodi,tila", [
    ("/", SERVE, "GET", 200),
    ("/static/app.css", SERVE, "GET", 200),
    ("/ei-ole", SERVE, "GET", 404),
    (f"/ajot/{RUN_ID[:-1]}x", SERVE, "GET", 404),
    ("/", SERVE, "POST", 405),
    ("/", _ilman("tailscale-user-login"), "GET", 403),
    ("/", SERVE | {"x-forwarded-host": "paha.example"}, "GET", 421),
])
def test_turvaotsakkeet_kaikissa_vastauksissa(client, polku, otsakkeet, metodi, tila):
    vastaus = get(client, polku, otsakkeet, metodi)
    assert vastaus.status_code == tila
    csp = vastaus.headers["content-security-policy"]
    for osa in ("default-src 'none'", "script-src 'none'", "connect-src 'none'", "frame-ancestors 'none'",
                "base-uri 'none'", "form-action 'self'"):
        assert osa in csp
    assert vastaus.headers["x-content-type-options"] == "nosniff"
    assert vastaus.headers["cache-control"] == "no-store"
    assert "set-cookie" not in vastaus.headers


def test_sivuilla_ei_ole_skripteja_eika_tapahtumakasittelijoita(client):
    for polku in ("/", "/ajot", f"/ajot/{RUN_ID}", "/asetukset"):
        sivu = BeautifulSoup(get(client, polku).text, "html.parser")
        assert not sivu.find_all("script")
        assert not [a for t in sivu.find_all(True) for a in t.attrs if a.lower().startswith("on")]


# --------------------------------------------------------------------------------------------------
# Tilojen erottelu
# --------------------------------------------------------------------------------------------------

def test_kehitystila_ei_hyvaksy_tuotannon_otsakkeita(publication):
    with TestClient(create_app(Settings(runs_dir=publication)), base_url="http://localhost", client=None) as dev:
        assert dev.get("/hub", headers=SERVE).status_code == 403  # kehitystila vaatii Host ilmari.local


def test_tuotantotila_ei_hyvaksy_kehitystilan_hostia(client):
    assert get(client, "/", {"host": "ilmari.local"}).status_code == 421


def test_esimerkkitila_ja_vieras_julkaisujuuri_estetaan_tuotannossa(config, tmp_path):
    with pytest.raises(ValueError, match="Esimerkkitila"):
        Settings(runs_dir=config.runs_dir, identity=config, demo_enabled=True)
    with pytest.raises(ValueError, match="konfiguraatiosta"):
        Settings(runs_dir=tmp_path, identity=config)
    with pytest.raises(ValueError, match="konfiguraatiosta"):
        Settings(identity=config)


def test_esimerkkidata_ei_nay_tuotannossa(client):
    vastaus = get(client, "/?demo=1")
    assert vastaus.status_code == 200 and "DEMO – ESIMERKKIDATA" not in vastaus.text
