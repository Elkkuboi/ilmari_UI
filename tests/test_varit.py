"""Vaihdettavat värit (Eliaksen pyyntö 18.11.2026): neljä väriyhdistelmää, valinta evästeessä ilmari_vari.

Yhdistelmät, nimet, kuvaukset ja taustavärit on kirjoitettu tähän käsin speksin mukaan (ei luettu rekisteristä).
Reitti /hub/ulkoasu/{tunniste} asettaa evästeen ja palaa Asetuksiin; se ei muuta mitään palvelimella. Kielletty suunta:
tuntematon tunniste ei aseta evästettä, eikä kelvoton eväste päädy sivulle.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui.app import PACKAGE_DIR, Settings, create_app, vari
from ilmari_ui.config import parse_config

# (tunniste, nimi, kuvaus, theme-color, color-scheme)
VARIT = (("paperi", "Paperi", "vaalea, lämmin", "#f1ead9", "light"),
         ("liitu", "Liitu", "vaalea, viileä", "#ecece6", "light"),
         ("terminaali", "Terminaali", "tumma, meripihka", "#17140f", "dark"),
         ("fosfori", "Fosfori", "tumma, vihreä", "#0e1411", "dark"))
TUNNISTEET = [v[0] for v in VARIT]
# Kehitystila: sivut, työn sivu ja virhesivu (kaikki käyttävät base.html:ää)
SIVUT = ("/hub", "/hub/keskustelu", "/hub/kehita", "/hub/kehita/98", "/hub/asetukset", "/hub/dokumentit",
         "/hub/dokumentit/arkkitehtuuri", "/hub/ei-ole")
KELVOTTOMAT = ("", "PAPERI", "Fosfori", "musta", "paperi2", "data-vari", '"><script>alert(1)</script>',
               "fosfori\" onload=\"x", "<b>liitu</b>")
CSP = ("default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; manifest-src 'self'; script-src 'none'; "
       "connect-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
OTSAKKEET = {"content-security-policy": CSP, "cache-control": "no-store", "referrer-policy": "same-origin",
             "x-content-type-options": "nosniff", "x-frame-options": "DENY",
             "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()"}
VUOSI = "31536000"
SERVE = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}


def local_client() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def tuotanto_client(tmp_path_factory) -> TestClient:
    julkaisut = tmp_path_factory.mktemp("julkaisu") / "ajot"   # ASCII-polku: konfiguraatio hyväksyy vain nimet
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(julkaisut),
                                   "kayttajat": {"elias@github": "elias"}}})
    return TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None)


def sivun_varit(response) -> tuple[str, str, str]:
    dom = BeautifulSoup(response.text, "html.parser")
    return (dom.html["data-vari"], dom.find("meta", attrs={"name": "color-scheme"})["content"],
            dom.find("meta", attrs={"name": "theme-color"})["content"])


def evaste(response) -> tuple[str, dict[str, str]]:
    """Ainoa Set-Cookie-otsake jäsennettynä: (nimi=arvo, {attribuutti pienellä: arvo})."""
    otsakkeet = response.headers.get_list("set-cookie")
    assert len(otsakkeet) == 1, otsakkeet
    pari, *osat = [o.strip() for o in otsakkeet[0].split(";")]
    attribuutit = {}
    for osa in osat:
        avain, _, arvo = osa.partition("=")
        attribuutit[avain.lower()] = arvo
    return pari, attribuutit


def turvaotsakkeet_ennallaan(response) -> None:
    for nimi, arvo in OTSAKKEET.items():
        assert response.headers[nimi] == arvo, nimi


# --- Rekisteri -----------------------------------------------------------------------------------------------------

def test_rekisteri_vastaa_speksia():
    from ilmari_ui.app import VARIT as REKISTERI
    assert [(v.tunniste, v.nimi, v.kuvaus, v.tausta, "dark" if v.tumma else "light") for v in REKISTERI] == list(VARIT)


@pytest.mark.parametrize("arvo", [None, 1, b"fosfori", ["liitu"], " terminaali", "liitu ", "paperi;x", *KELVOTTOMAT])
def test_rekisteri_palauttaa_oletuksen_kaikelle_muulle(arvo):
    assert vari(arvo).tunniste == "paperi"


@pytest.mark.parametrize("tunniste", TUNNISTEET)
def test_rekisteri_tuntee_nelja_tunnistetta(tunniste):
    assert vari(tunniste).tunniste == tunniste


# --- Sivut evästeen mukaan ----------------------------------------------------------------------------------------

def test_oletus_ilman_evastetta():
    with local_client() as c:
        for polku in SIVUT:
            for kysely in ("", "?demo=1"):
                assert sivun_varit(c.get(polku + kysely)) == ("paperi", "light", "#f1ead9"), polku + kysely


@pytest.mark.parametrize("tunniste,nimi,kuvaus,tausta,teema", VARIT)
def test_jokainen_vari_asettaa_sivun_varit(tunniste, nimi, kuvaus, tausta, teema):
    with local_client() as c:
        c.cookies.set("ilmari_vari", tunniste)
        for polku in SIVUT:
            for kysely in ("", "?demo=1"):
                assert sivun_varit(c.get(polku + kysely)) == (tunniste, teema, tausta), polku + kysely


@pytest.mark.parametrize("arvo", KELVOTTOMAT)
def test_kelvoton_evaste_antaa_oletuksen_eika_paady_sivulle(arvo):
    with local_client() as c:
        for polku in ("/hub?demo=1", "/hub/asetukset?demo=1", "/hub/ei-ole"):
            r = c.get(polku, headers={"cookie": f"ilmari_vari={arvo}"})
            assert sivun_varit(r) == ("paperi", "light", "#f1ead9")
            dom = BeautifulSoup(r.text, "html.parser")
            assert {t["data-vari"] for t in dom.select("[data-vari]")} <= set(TUNNISTEET)
            if "<" in arvo or '"' in arvo:
                assert arvo not in r.text and "<script" not in r.text and "onload" not in r.text


def test_tuotannossa_sama_evaste_ohjaa_sivuja(tmp_path_factory):
    with tuotanto_client(tmp_path_factory) as c:
        assert sivun_varit(c.get("/", headers=SERVE)) == ("paperi", "light", "#f1ead9")
        for polku in ("/", "/asetukset", "/ei-ole"):
            r = c.get(polku, headers=SERVE | {"cookie": "ilmari_vari=fosfori"})
            assert sivun_varit(r) == ("fosfori", "dark", "#0e1411")


# --- Asetukset: Ulkoasu --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("valittu", [None, *TUNNISTEET])
def test_asetuksissa_nelja_naytetta_ja_kaytossa_oleva_merkitty(valittu):
    kaytossa = valittu or "paperi"
    with local_client() as c:
        for kysely, perassa in (("", ""), ("?demo=1", "?demo=1")):
            otsakkeet = {"cookie": f"ilmari_vari={valittu}"} if valittu else {}
            dom = BeautifulSoup(c.get("/hub/asetukset" + kysely, headers=otsakkeet).text, "html.parser")
            osio = dom.select_one("section#ulkoasu")
            assert osio is not None and osio.find_next_sibling("section").select_one("#h-muut") is not None
            aside = " ".join(osio.select_one("h2.label .aside").get_text().split())
            assert aside == f"käytössä: {dict((v[0], v[1]) for v in VARIT)[kaytossa]}"
            naytteet = osio.select("ul.swatches > li > a.swatch")
            assert [(a["data-vari"], a["href"], a.select_one(".swatch-name").get_text(),
                     a.select_one(".swatch-line").get_text()) for a in naytteet] == \
                [(t, f"/hub/ulkoasu/{t}{perassa}", n, k) for t, n, k, _, _ in VARIT]
            assert [a["data-vari"] for a in naytteet if a.get("aria-current") == "true"] == [kaytossa]
            assert all(a.select_one(".dot")["aria-hidden"] == "true" for a in naytteet)


def test_ulkoasu_on_ennen_muut_osiota_ja_ankkurilla():
    with local_client() as c:
        dom = BeautifulSoup(c.get("/hub/asetukset?demo=1").text, "html.parser")
        osiot = [s.get("id") or s.select_one("h2, h1").get_text().strip() for s in dom.select("main section")]
        assert osiot[-2:] == ["ulkoasu", "Muut"]


# --- Reitti /hub/ulkoasu/{tunniste} -------------------------------------------------------------------------------

@pytest.mark.parametrize("tunniste", TUNNISTEET)
def test_reitti_asettaa_evasteen_ja_palaa_asetuksiin(tunniste):
    with local_client() as c:
        for kysely, kohde in (("", "/hub/asetukset#ulkoasu"), ("?demo=1", "/hub/asetukset?demo=1#ulkoasu")):
            r = c.get(f"/hub/ulkoasu/{tunniste}{kysely}", follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == kohde
            pari, attribuutit = evaste(r)
            assert pari == f"ilmari_vari={tunniste}"
            assert attribuutit == {"httponly": "", "max-age": VUOSI, "path": "/", "samesite": "Lax"}   # ei Secure
            turvaotsakkeet_ennallaan(r)
        # seurattuna: Asetukset näyttää valitun värin
        c.cookies.clear()
        r = c.get(f"/hub/ulkoasu/{tunniste}?demo=1")
        assert r.status_code == 200 and (r.url.path, r.url.query) == ("/hub/asetukset", b"demo=1")
        assert sivun_varit(r)[0] == tunniste


def test_reitin_evaste_tuotannossa_on_secure(tmp_path_factory):
    with tuotanto_client(tmp_path_factory) as c:
        r = c.get("/ulkoasu/terminaali", headers=SERVE, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/hub/asetukset#ulkoasu"
        pari, attribuutit = evaste(r)
        assert pari == "ilmari_vari=terminaali"
        assert attribuutit == {"httponly": "", "max-age": VUOSI, "path": "/", "samesite": "Lax", "secure": ""}
        turvaotsakkeet_ennallaan(r)
        # esimerkkitila ei kulje tuotannossa
        assert c.get("/ulkoasu/liitu?demo=1", headers=SERVE, follow_redirects=False).headers["location"] == \
            "/hub/asetukset#ulkoasu"


@pytest.mark.parametrize("polku", ["/hub/ulkoasu/musta", "/hub/ulkoasu/PAPERI", "/hub/ulkoasu/Fosfori",
                                   "/hub/ulkoasu/paperi%20", "/hub/ulkoasu/%20liitu", "/hub/ulkoasu/paperi;x",
                                   "/hub/ulkoasu/%3Cscript%3E", "/hub/ulkoasu/terminaali/x", "/hub/ulkoasu/",
                                   "/hub/ulkoasu", "/hub/ulkoasu/..%2Fpaperi"])
def test_tuntematon_tunniste_on_404_ilman_evastetta(polku):
    with local_client() as c:
        for kysely in ("", "?demo=1"):
            r = c.get(polku + kysely, follow_redirects=False)
            assert r.status_code == 404 and "set-cookie" not in r.headers, polku
            assert "<script" not in r.text
            turvaotsakkeet_ennallaan(r)


def test_tuntematon_tunniste_tuotannossa(tmp_path_factory):
    with tuotanto_client(tmp_path_factory) as c:
        r = c.get("/ulkoasu/musta", headers=SERVE, follow_redirects=False)
        assert r.status_code == 404 and "set-cookie" not in r.headers
        turvaotsakkeet_ennallaan(r)


@pytest.mark.parametrize("metodi", ["POST", "PUT", "DELETE"])
def test_reitti_ei_ota_vastaan_muuta_kuin_lukua(metodi, tmp_path_factory):
    with local_client() as c:
        r = c.request(metodi, "/hub/ulkoasu/fosfori", follow_redirects=False)
        assert r.status_code == 403 and "set-cookie" not in r.headers
    with tuotanto_client(tmp_path_factory) as c:
        r = c.request(metodi, "/ulkoasu/fosfori", headers=SERVE, follow_redirects=False)
        assert r.status_code == 405 and "set-cookie" not in r.headers


def test_reitti_vain_vartijan_lapi(tmp_path_factory):
    """Kielletty suunta: väärä tunnus tai osoite ei saa evästettä."""
    with tuotanto_client(tmp_path_factory) as c:
        for otsakkeet, tila in ((SERVE | {"tailscale-user-login": "muu@example.com"}, 403),
                                (SERVE | {"x-forwarded-host": "paha.example"}, 421)):
            r = c.get("/ulkoasu/fosfori", headers=otsakkeet, follow_redirects=False)
            assert r.status_code == tila and "set-cookie" not in r.headers
    with local_client() as c:
        r = c.get("/hub/ulkoasu/fosfori", headers={"host": "evil.org"}, follow_redirects=False)
        assert r.status_code == 403 and "set-cookie" not in r.headers


def test_sivujen_turvaotsakkeet_ennallaan_kaikilla_vareilla():
    with local_client() as c:
        for tunniste in TUNNISTEET:
            r = c.get("/hub/asetukset?demo=1", headers={"cookie": f"ilmari_vari={tunniste}"})
            assert r.status_code == 200 and "set-cookie" not in r.headers
            turvaotsakkeet_ennallaan(r)


# --- Tyylitiedosto ----------------------------------------------------------------------------------------------

def _lohkot(css: str) -> dict[str, tuple[str, dict[str, str]]]:
    """Väriyhdistelmien lohkot: {tunniste: (valitsin, {muuttuja tai color-scheme: arvo})}."""
    lohkot = {}
    for m in re.finditer(r'(?m)^([^{}\n]*\[data-vari="([a-z]+)"\][^{}\n]*)\{([^}]*)\}', css):
        runko = re.sub(r"/\*.*?\*/", "", m.group(3), flags=re.S)
        arvot = dict((k.strip(), v.strip()) for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+);", runko))
        lohkot[m.group(2)] = (m.group(1).strip(), arvot)
    return lohkot


def test_tyylitiedostossa_nelja_lohkoa_eika_vareja_niiden_ulkopuolella():
    css = (PACKAGE_DIR / "static" / "app.css").read_text(encoding="utf-8")
    lohkot = _lohkot(css)
    assert list(lohkot) == TUNNISTEET
    assert lohkot["paperi"][0] == ':root, [data-vari="paperi"]'   # oletus ilman attribuuttia
    muuttujat = {"--paper", "--sheet", "--shade", "--ink", "--ink-2", "--ink-3", "--rule", "--accent", "--ok",
                 "--warn", "--stop"}
    for tunniste, nimi, kuvaus, tausta, teema in VARIT:
        arvot = lohkot[tunniste][1]
        assert set(arvot) == muuttujat | {"color-scheme"}, tunniste
        assert arvot["color-scheme"] == teema and arvot["--paper"] == tausta, tunniste
        assert all(re.fullmatch(r"#[0-9a-f]{6}", arvot[m]) for m in muuttujat), tunniste
    ulkopuolella = re.sub(r'(?m)^[^{}\n]*\[data-vari="[a-z]+"\][^{}\n]*\{[^}]*\}', "", css)
    ulkopuolella = re.sub(r"/\*.*?\*/", "", ulkopuolella, flags=re.S)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", ulkopuolella)
    assert not re.search(r"\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(", ulkopuolella)
    assert not re.search(r":\s*(white|black|gray|grey|red|green|blue|canvas|canvastext)\b", ulkopuolella, re.I)
    assert "color-scheme" not in ulkopuolella and "prefers-color-scheme" not in css
    assert "background: var(--paper)" in re.search(r"(?m)^html \{[^}]*\}", css).group(0)   # ei valkoista reunaa


def _suhde(a: str, b: str) -> float:
    def l(h: str) -> float:
        kanavat = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b_ = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in kanavat]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_
    suuri, pieni = sorted((l(a), l(b)), reverse=True)
    return (suuri + 0.05) / (pieni + 0.05)


@pytest.mark.parametrize("tunniste", TUNNISTEET)
def test_tekstivarit_erottuvat_taustoilta(tunniste):
    """WCAG AA (4,5:1): jokainen tekstiväri sivun ja tulosteen taustalla sekä täytetyn napin teksti."""
    arvot = _lohkot((PACKAGE_DIR / "static" / "app.css").read_text(encoding="utf-8"))[tunniste][1]
    for teksti in ("--ink", "--ink-2", "--ink-3", "--accent", "--ok", "--warn", "--stop"):
        for tausta in ("--paper", "--sheet"):
            assert _suhde(arvot[teksti], arvot[tausta]) >= 4.5, (teksti, tausta)
    for tausta, teksti in (("--ink", "--paper"), ("--accent", "--sheet"), ("--stop", "--sheet")):   # napit
        assert _suhde(arvot[teksti], arvot[tausta]) >= 4.5, (tausta, teksti)
