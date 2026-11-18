"""Tuotantotila (aiops ADR-0013): Tailscale Serven polku /hub, gatewayn vartijan säännöt ja etuliitteen palautus.

Riippumaton totuus on alla käsin kirjoitettu otsaketaulukko. Se perustuu kahteen havaintoon työasemalla:
gatewayn otsakevedos 1.10.2026 (aiops ADR-0010, tarkennus 7b-3) ja Hubin Serve-koe 14.10.2026, jossa koepolku
/hub-koe/ajot/x?y=1 saapui sokettiin muodossa /ajot/x?y=1. Pyynnöllä oli otsakkeet Host: localhost,
X-Forwarded-Host: tyoasema.taild1a5b7.ts.net ja Tailscale-User-Login: Elkkuboi@github. Serve korvasi asiakkaan
väärentämät arvot ja poisti asiakkaan Tailscale-Funnel-Request-otsakkeen, mutta päästi X-Forwarded-Prefixin läpi.
"""

from __future__ import annotations


from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import parse_config

RP = "tyoasema.taild1a5b7.ts.net"
LOGIN = "Elkkuboi@github"
SERVE = {"x-forwarded-host": RP, "tailscale-user-login": LOGIN, "x-forwarded-proto": "https",
         "x-forwarded-for": "100.67.5.28"}


@pytest.fixture
def config(tmp_path_factory):
    # julkaisut-avain hyväksytään yhä (tuotannon hub.toml on rootin), vaikka ajoja ei enää näytetä
    julkaisut = tmp_path_factory.mktemp("julkaisu") / "ajot"  # ASCII-polku: konfiguraatio hyväksyy vain nimimerkit
    return parse_config({"hub": {"rp_id": RP, "julkaisut": str(julkaisut), "kayttajat": {LOGIN: "elias"}}})


@pytest.fixture
def client(config):
    settings = Settings(identity=config)
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
    settings = Settings(identity=config)
    with TestClient(create_app(settings), base_url="http://localhost") as tcp:  # oletusasiakas = TCP-osoite
        assert tcp.get("/", headers=SERVE).status_code == 403


def test_hylkays_ei_heijasta_syotetta(client):
    vastaus = get(client, "/", SERVE | {"x-forwarded-host": "<script>alert(1)</script>"})
    assert vastaus.status_code == 421 and "<script>" not in vastaus.text and RP in vastaus.text


# --------------------------------------------------------------------------------------------------
# Etuliitteen palautus: Serve toimittaa polut ilman etuliitettä /hub
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("serven_polku,otsikko", [
    ("/", "Nyt"),
    ("/keskustelu", "Keskustelu"),
    ("/kehita", "Työt"),
    ("/asetukset", "Asetukset"),
    ("/dokumentit", "Dokumentit"),
])
def test_serven_polku_ohjautuu_hubin_sivulle(client, serven_polku, otsikko):
    vastaus = get(client, serven_polku)
    assert vastaus.status_code == 200
    assert BeautifulSoup(vastaus.text, "html.parser").title.text == f"{otsikko} · Ilmari"


@pytest.mark.parametrize("serven_polku,kohde", [
    ("/ilmari", "/hub"),
    ("/ilmari?toihin=rajatesti", "/hub?toihin=rajatesti"),   # gateway palaa tänne, kun Töihin nyt ajaa rajatestin
    ("/mallit", "/hub/asetukset#aivot"),                     # vanha gateway palaa tänne profiilin ja roolin vaihdon jälkeen
    ("/mallit?x=1", "/hub/asetukset?x=1#aivot"),              # ankkuri kyselyn perään
    ("/jarjestelma", "/hub/asetukset#kone"),
    ("/saannot", "/hub/dokumentit"),
    ("/ajot", "/hub"), ("/ajot/20261013-235929-yo-q6", "/hub"), ("/hyvaksynnat", "/hub"), ("/sovellukset", "/hub"),
    ("/sovellukset/hahmo", "/hub"), ("/ideat", "/hub"),
])
def test_vanhat_osoitteet_ohjataan_selaimen_osoitteeseen(client, serven_polku, kohde):
    """Ohjaus selaimen näkemään osoitteeseen (etuliite /hub mukana), kysely säilyy, turvaotsakkeet ovat mukana."""
    vastaus = get(client, serven_polku)
    assert vastaus.status_code == 307 and vastaus.headers["location"] == kohde
    assert "script-src 'none'" in vastaus.headers["content-security-policy"]


def test_vanha_osoite_ohjataan_vain_vartijan_lapi(client):
    """Kielletty suunta: ohjaus ei ohita vartijaa (väärä tunnus, POST)."""
    assert get(client, "/ilmari", SERVE | {"tailscale-user-login": "muu@example.com"}).status_code == 403
    assert get(client, "/ilmari", method="POST").status_code == 405


def test_staattinen_tiedosto_etuliitteen_kautta(client):
    vastaus = get(client, "/static/app.css")
    assert vastaus.status_code == 200 and vastaus.headers["content-type"].startswith("text/css")
    assert get(client, "/static/app.css", method="HEAD").status_code == 200  # vartija päästää HEADin
    fontti = get(client, "/static/fonts/IBMPlexMono-Regular.woff2")
    assert fontti.status_code == 200 and fontti.headers["content-type"] == "font/woff2"
    assert fontti.content[:4] == b"wOF2" and "font-src 'self'" in fontti.headers["content-security-policy"]


def test_etuliite_ei_tuplaannu(client):
    assert get(client, "/hub/kehita").status_code == 404  # selaimen osoite olisi /hub/hub/kehita


@pytest.mark.parametrize("otsakkeet", [SERVE, SERVE | {"x-forwarded-prefix": "/muu"}])
@pytest.mark.parametrize("polku", ["/", "/keskustelu", "/kehita", "/asetukset", "/dokumentit"])
def test_kaikki_sisaiset_linkit_osoittavat_hubiin(client, otsakkeet, polku):
    sivu = BeautifulSoup(get(client, polku, otsakkeet).text, "html.parser")
    osoitteet = [t.get("href") or t.get("action") or t.get("src") for t in sivu.select("[href], [action], [src]")]
    sisaiset = [o for o in osoitteet if o and o.startswith("/")]
    assert sisaiset and all(o == "/hub" or o.startswith(("/hub/", "/hub?", "/hub#")) for o in sisaiset), sisaiset
    assert not any("/muu" in o for o in sisaiset)
    ulkoiset = [o for o in osoitteet if o and o.startswith("http")]
    assert all(o.startswith((f"https://{RP}/", f"https://{RP}:8443/", f"https://{RP}:8444/")) for o in ulkoiset), ulkoiset


def test_tuotantotila_nayttaa_tyoaseman_eika_kehitysymparistoa(client):
    teksti = get(client, "/").text
    assert "työasema" in teksti and "kehitysympäristö" not in teksti and "Esimerkkitila" not in teksti


# --------------------------------------------------------------------------------------------------
# Turvaotsakkeet jokaisessa vastauksessa (Hub jakaa alkuperän gatewayn kanssa, ADR-0013 kohta 5)
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("polku,otsakkeet,metodi,tila", [
    ("/", SERVE, "GET", 200),
    ("/static/app.css", SERVE, "GET", 200),
    ("/ei-ole", SERVE, "GET", 404),
    ("/kehita/abc", SERVE, "GET", 404),
    ("/ilmari", SERVE, "GET", 307),
    ("/static/fonts/IBMPlexMono-Regular.woff2", SERVE, "GET", 200),
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
    for polku in ("/", "/keskustelu", "/kehita", "/asetukset", "/dokumentit", "/ei-ole"):
        sivu = BeautifulSoup(get(client, polku).text, "html.parser")
        assert not sivu.find_all("script")
        assert not [a for t in sivu.find_all(True) for a in t.attrs if a.lower().startswith("on")]


# --------------------------------------------------------------------------------------------------
# Tilojen erottelu
# --------------------------------------------------------------------------------------------------

def test_kehitystila_ei_hyvaksy_tuotannon_otsakkeita():
    with TestClient(create_app(Settings()), base_url="http://localhost", client=None) as dev:
        assert dev.get("/hub", headers=SERVE).status_code == 403  # kehitystila vaatii Host ilmari.local


def test_tuotantotila_ei_hyvaksy_kehitystilan_hostia(client):
    assert get(client, "/", {"host": "ilmari.local"}).status_code == 421


def test_esimerkkitila_estetaan_tuotannossa(config):
    with pytest.raises(ValueError, match="Esimerkkitila"):
        Settings(identity=config, demo_enabled=True)
    assert Settings(identity=config).identity is config and Settings(demo_enabled=True).identity is None


def test_esimerkkidata_ei_nay_tuotannossa(client):
    vastaus = get(client, "/?demo=1")
    assert vastaus.status_code == 200 and "Esimerkkitila" not in vastaus.text and "Aamuraportti 19.11." not in vastaus.text
