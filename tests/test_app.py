"""Hubin HTTP-raja ja sivut kehitys- ja esimerkkitilassa (Hub juureksi 18.11.2026).

TestClientin puuttuva asiakasosoite edustaa Unix-soketin rajaa. Tavallisen TCP-asiakkaan pitää epäonnistua, vaikka se
antaisi uskottavat identiteettiotsakkeet. Sivurakenne (neljä valikkolinkkiä, vanhojen osoitteiden ohjaukset, poistetut
osat) on kirjoitettu tähän käsin speksin mukaan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from fastapi.responses import HTMLResponse

from ilmari_ui.app import PACKAGE_DIR, Settings, create_app, format_time, koneen_ika, lyhyt_aika, paivity
from ilmari_ui.config import parse_config

# (osoite, otsikko, aktiivinen valikkolinkki)
SIVUT = (("/hub", "Nyt", "Nyt"), ("/hub/keskustelu", "Keskustelu", "Keskustelu"), ("/hub/kehita", "Työt", "Työt"),
         ("/hub/asetukset", "Asetukset", "Asetukset"), ("/hub/dokumentit", "Dokumentit", "Asetukset"))
VALIKKO = [("Nyt", "/hub"), ("Keskustelu", "/hub/keskustelu"), ("Työt", "/hub/kehita"), ("Asetukset", "/hub/asetukset")]
# (kohde, ankkuri): kysely säilyy ja ankkuri tulee sen perään (vanha gateway palaa /hub/mallit-osoitteeseen)
VANHAT = {"/hub/ilmari": "/hub", "/hub/mallit": ("/hub/asetukset", "#aivot"), "/hub/jarjestelma": ("/hub/asetukset", "#kone"),
          "/hub/saannot": "/hub/dokumentit", "/hub/ajot": "/hub", "/hub/ajot/20261013-001914-yo-demo": "/hub",
          "/hub/hyvaksynnat": "/hub", "/hub/sovellukset": "/hub", "/hub/sovellukset/ravintopolku": "/hub",
          "/hub/ideat": "/hub"}
KIELLETYT_SANAT = ("gateway", "julkaisu", "julkais", "dsh", "adr", "kontti", "politiikka", "main")
FONTIT = ("IBMPlexMono-Regular.woff2", "IBMPlexMono-Italic.woff2", "IBMPlexMono-Medium.woff2", "IBMPlexMono-SemiBold.woff2")


def local_client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings), base_url="http://ilmari.local", client=None)


def soup(response) -> BeautifulSoup:
    return BeautifulSoup(response.text, "html.parser")


@pytest.fixture
def demo_client():
    with local_client(Settings(demo_enabled=True)) as client:
        yield client


# --- Sivut ja rakenne --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("polku,otsikko,aktiivinen", SIVUT)
def test_jokainen_sivu_toimii_kehitys_ja_esimerkkitilassa(demo_client, polku, otsikko, aktiivinen):
    for kysely in ("", "?demo=1"):
        r = demo_client.get(polku + kysely)
        dom = soup(r)
        assert r.status_code == 200 and dom.html["lang"] == "fi" and dom.find("main", id="main") is not None
        assert dom.html["data-vari"] == "paperi"   # oletusvärit ilman evästettä (tests/test_varit.py)
        assert dom.title.get_text() == f"{otsikko} · Ilmari"
        assert dom.find("meta", attrs={"name": "color-scheme"})["content"] == "light"
        assert dom.find("meta", attrs={"name": "theme-color"})["content"] == "#f1ead9"
        assert [l["href"] for l in dom.find_all("link", rel="stylesheet")] == ["/hub/static/app.css"]
        assert len(dom.find_all("h1")) == 1
        merkinta = dom.select("main > .wrap > p.note")
        assert bool(merkinta and "Esimerkkitila" in merkinta[0].get_text()) is bool(kysely)
        alapalkki = " ".join(dom.find("footer", class_="foot").get_text(" ").split())
        assert re.fullmatch(r"Ilmari Hub · (kehitysympäristö|esimerkkitila) Haettu klo \d\d\.\d\d", alapalkki)


@pytest.mark.parametrize("polku,otsikko,aktiivinen", SIVUT)
def test_valikossa_on_tasan_nelja_linkkia(demo_client, polku, otsikko, aktiivinen):
    for kysely, perassa in (("", ""), ("?demo=1", "?demo=1")):
        dom = soup(demo_client.get(polku + kysely))
        linkit = dom.select("header.top nav.nav a")
        assert [(a.get_text(), a["href"]) for a in linkit] == [(n, h + perassa) for n, h in VALIKKO]
        assert [a.get_text() for a in linkit if a.get("aria-current") == "page"] == [aktiivinen]
        brand = dom.select_one("header.top a.brand")
        assert brand.get_text() == "ILMARI" and brand["href"] == "/hub" + perassa
        assert len(dom.find_all("nav")) == 1   # ei sivupalkkia, alapalkkia eikä hampurilaisvalikkoa


def test_esimerkkitila_kulkee_sisaisissa_linkeissa(demo_client):
    for polku, _, _ in SIVUT:
        for a in soup(demo_client.get(polku + "?demo=1")).select("a[href^='/hub']"):
            assert parse_qs(urlsplit(a["href"]).query).get("demo") == ["1"], (polku, a["href"])


@pytest.mark.parametrize("vanha,uusi", VANHAT.items())
def test_vanhat_osoitteet_ohjataan_kysely_mukana(demo_client, vanha, uusi):
    uusi, ankkuri = uusi if isinstance(uusi, tuple) else (uusi, "")
    r = demo_client.get(vanha, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == uusi + ankkuri and "set-cookie" not in r.headers
    r = demo_client.get(vanha + "?demo=1&toihin=rajatesti", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == uusi + "?demo=1&toihin=rajatesti" + ankkuri
    assert demo_client.get(vanha + "?demo=1").status_code == 200   # seurattuna sivu toimii


def test_ohjaus_ei_ole_avoin_uudelleenohjaus(demo_client):
    for kysely in ("next=//evil.org", "x=%0d%0aLocation:%20https://evil.org", "@evil.org"):
        r = demo_client.get("/hub/ilmari?" + kysely, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"].startswith("/hub?")
        assert "\r" not in r.headers["location"] and "\n" not in r.headers["location"]


@pytest.mark.parametrize("metodi", ["POST", "PUT", "DELETE"])
def test_vanhat_osoitteet_eivat_ota_vastaan_muuta_kuin_lukua(demo_client, metodi):
    assert demo_client.request(metodi, "/hub/ilmari").status_code == 403   # vartija ennen reititystä


def test_poistetut_osat_eivat_nay(demo_client):
    for polku, _, _ in SIVUT:
        for kysely in ("", "?demo=1"):
            r = demo_client.get(polku + kysely)
            dom = soup(r)
            assert not dom.find("svg") and not dom.select(".sidebar, .bottom-nav, .mobile-menu, .demo-banner, .panel")
            assert "skin" not in r.text and "data-skin" not in r.text and "themes.css" not in r.text
            valikko = dom.select_one("nav.nav").get_text()
            for nimi in ("Koti", "Ilmari nyt", "Kehitä", "Ajot", "Sovellukset", "Hyväksynnät", "Ideat", "Järjestelmä",
                         "Säännöt", "Mallit"):
                assert nimi not in valikko
    for staattinen in ("themes.css", "icon.svg"):
        assert demo_client.get(f"/hub/static/{staattinen}").status_code == 404


def tuotanto_asiakas(tmp_path) -> TestClient:
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(tmp_path / "ajot"),
                                   "kayttajat": {"elias@github": "elias"}}})
    return TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None)


def test_kayttoliittyman_teksteissa_ei_jargonia(demo_client, tmp_path):
    """Kehitystilan ja tyhjän tuotannon sivuilla näkyy vain käyttöliittymän oma teksti (ei dataa): ei sanoja gateway,
    julkaisu, dsh, ADR, kontti tai politiikka. (Esimerkkiaineisto on dataa, ei käyttöliittymän tekstiä.)"""
    serve = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}
    with tuotanto_asiakas(tmp_path) as tuotanto:
        vastaukset = [demo_client.get(p) for p, _, _ in SIVUT] + [demo_client.get("/hub/ei-ole")]
        vastaukset += [tuotanto.get(p.removeprefix("/hub") or "/", headers=serve) for p, _, _ in SIVUT]
        # esimerkkitilan sivut (myös työt, dokumentti ja haku): data (tulosteet, dokumentit, koodi) ei ole
        # käyttöliittymän tekstiä, joten se jätetään pois
        for p in [p for p, _, _ in SIVUT] + ["/hub/kehita/98", "/hub/kehita/41", "/hub/kehita/42", "/hub/kehita/43",
                                             "/hub/kehita/40", "/hub/dokumentit/arkkitehtuuri", "/hub/dokumentit?q=ilmari"]:
            vastaukset.append(demo_client.get(p + ("&" if "?" in p else "?") + "demo=1"))
    for r in vastaukset:
        dom = soup(r)
        for data in dom.select(".pre, .sheet, .prose, pre, code, a[href*='/hub/dokumentit/']"):
            data.decompose()
        teksti = dom.get_text(" ").lower()
        teksti = teksti.replace("adresseja", "")
        for sana in KIELLETYT_SANAT:
            assert not re.search(rf"\b{sana}", teksti), (r.url, sana)


def test_ei_skripteja_tyyleja_eika_tapahtumakasittelijoita(demo_client):
    for polku, _, _ in SIVUT:
        for kysely in ("", "?demo=1"):
            dom = soup(demo_client.get(polku + kysely))
            assert not dom.find_all(["script", "style", "iframe", "object", "embed"])
            assert not [a for t in dom.find_all(True) for a in t.attrs if a.lower().startswith("on") or a == "style"]


def test_paikalliset_tiedostot_latautuvat_turvaotsakkein(demo_client):
    dom = soup(demo_client.get("/hub"))
    resurssit = [l["href"] for l in dom.find_all("link", href=True)]
    assert set(resurssit) == {"/hub/static/favicon-v2.svg", "/hub/static/manifest.webmanifest",
                              "/hub/static/icon-192-v2.png", "/hub/static/app.css"}
    for polku in resurssit + [f"/hub/static/fonts/{f}" for f in FONTIT] + ["/hub/static/fonts/IBM-Plex-LICENSE.txt",
                                                                         "/hub/static/icon-512-v2.png",
                                                                         "/hub/static/icon-maskable-512-v2.png"]:
        r = demo_client.get(polku)
        assert r.status_code == 200 and r.content, polku
        assert "script-src 'none'" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"
    assert demo_client.get("/hub/static/fonts/IBMPlexMono-Regular.woff2").headers["content-type"] == "font/woff2"
    assert "SIL Open Font License" in demo_client.get("/hub/static/fonts/IBM-Plex-LICENSE.txt").text


def test_tyyli_viittaa_vain_paikallisiin_fontteihin():
    css = (PACKAGE_DIR / "static" / "app.css").read_text(encoding="utf-8")
    viittaukset = re.findall(r'url\("([^"]+)"\)', css)
    assert sorted(viittaukset) == sorted(f"fonts/{f}" for f in FONTIT)
    assert all((PACKAGE_DIR / "static" / v).is_file() for v in viittaukset)
    assert "@import" not in css and "http" not in css
    # yksi tyyli: värit valitaan evästeellä (ei selaimen tummaa tilaa), ei varjoja eikä pyöristyksiä; sisäviivat
    # (valikon alleviivaus, valitun värinäytteen kehys) ovat ainoat box-shadow-arvot
    assert "prefers-color-scheme" not in css and "border-radius: 0" in css
    assert {v.strip() for v in re.findall(r"box-shadow:\s*([^;}]+)", css)} <= {"inset 0 -2px 0 var(--ink)",
                                                                             "inset 0 0 0 1px var(--ink)", "none"}
    assert "text-shadow" not in css and "gradient" not in css
    assert not re.search(r"border-radius:\s*[1-9]", css)


VANHAT_KUVAKKEET = ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "favicon.svg")


def test_manifesti_ja_kuvakkeet(demo_client):
    """Kuvakkeet versioiduilla nimillä (19.11.2026): asennettu sovellus huomaa uuden kuvakkeen vain uudesta
    osoitteesta. Jokainen manifestin kuvake on olemassa, oikean kokoinen PNG ja ladattavissa."""
    m = json.loads((PACKAGE_DIR / "static" / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert (m["name"], m["start_url"], m["background_color"], m["theme_color"]) == ("Ilmari", "/hub", "#f1ead9", "#f1ead9")
    assert [(k["src"], k["sizes"], k["purpose"]) for k in m["icons"]] == [
        ("/hub/static/icon-192-v2.png", "192x192", "any"), ("/hub/static/icon-512-v2.png", "512x512", "any"),
        ("/hub/static/icon-maskable-512-v2.png", "512x512", "maskable")]
    for kuvake in m["icons"]:
        tiedosto = PACKAGE_DIR / "static" / Path(kuvake["src"]).name
        koko = int(kuvake["sizes"].split("x")[0])
        data = tiedosto.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(data[16:20], "big") == koko
        assert int.from_bytes(data[20:24], "big") == koko and kuvake["type"] == "image/png"
        r = demo_client.get(kuvake["src"])
        assert r.status_code == 200 and r.content == data and r.headers["content-type"] == "image/png"
    svg = (PACKAGE_DIR / "static" / "favicon-v2.svg").read_text(encoding="utf-8")
    assert "#f1ead9" in svg and "#1f1b16" in svg and "#a8431a" in svg and "<script" not in svg


def test_vanhoja_kuvakenimia_ei_ole():
    """Kielletty suunta: vanhoja (versioimattomia) kuvaketiedostoja tai viittauksia niihin ei jää."""
    for vanha in VANHAT_KUVAKKEET:
        assert not (PACKAGE_DIR / "static" / vanha).exists(), vanha
        assert local_client(Settings(demo_enabled=True)).get(f"/hub/static/{vanha}").status_code == 404
    for tiedosto in [*PACKAGE_DIR.rglob("*.html"), *PACKAGE_DIR.rglob("*.py"), PACKAGE_DIR / "static" / "manifest.webmanifest"]:
        teksti = tiedosto.read_text(encoding="utf-8")
        assert not [v for v in VANHAT_KUVAKKEET if "/" + v in teksti], tiedosto


def test_juuri_ohjaa_hubiin_ilman_evastetta(demo_client):
    response = demo_client.get("/", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/hub" and "set-cookie" not in response.headers


def test_esimerkkitila_on_oletuksena_pois_eika_kehitystila_nayta_keksittya(tmp_path):
    r = local_client(Settings()).get("/hub?demo=1")
    assert r.status_code == 200 and "Esimerkkitila" not in r.text and "Aamuraportti" not in r.text
    assert "Ilmarin tila ei ole saatavilla" in r.text


def test_esimerkkitila_vaatii_kyselyn(demo_client):
    live, demo = demo_client.get("/hub"), demo_client.get("/hub?demo=1")
    assert "Esimerkkitila" not in live.text and "Aamuraportti" not in live.text
    assert "Esimerkkitila: keksitty aineisto" in demo.text and "Aamuraportti 19.11." in demo.text


@pytest.mark.parametrize("polku,paivitys", [("/hub?demo=1", "30"), ("/hub", None), ("/hub/kehita?demo=1", "15"),
                                            ("/hub/kehita", None), ("/hub/asetukset?demo=1", None),
                                            ("/hub/keskustelu?demo=1", None), ("/hub/dokumentit?demo=1", None)])
def test_automaattinen_paivitys_vain_kun_jotain_on_kaynnissa(demo_client, polku, paivitys):
    """Esimerkissä työvuoro ja työ 42 ovat käynnissä. Asetukset ei päivity koskaan (tyhjentäisi lomakkeet); keskustelu
    päivittyy vain, kun Ilmari vastaa vielä (test_keskustelu)."""
    assert demo_client.get(polku).headers.get("refresh") == paivitys


@pytest.mark.parametrize("html,paivittyy", [
    ("<p>tila</p>", True), ('<form><input type="hidden" name="paluu" value="hub"><button>Seis</button></form>', True),
    ("<p>&lt;textarea&gt; on tekstiä, ei kenttä</p>", True),
    ("<textarea name=t></textarea>", False), ('<input name="nimi">', False), ('<input type="text" name="x">', False),
    ('<input name="x" type="hidden"><input name="y">', False), ("<select name=s></select>", False),
    ("<TEXTAREA></TEXTAREA>", False)])
def test_paivitys_ei_koskaan_sivulle_jolla_on_muokattava_kentta(html, paivittyy):
    """Raja koodissa (19.11.2026): päivitys tyhjentäisi kesken kirjoitetun tekstin."""
    assert ("refresh" in paivity(HTMLResponse(html), "5").headers) is paivittyy


def test_paivittyvalla_sivulla_ei_ole_tekstikenttaa(demo_client):
    """Jokainen sivu ja tila esimerkissä: joko päivitys tai muokattava kenttä, ei molempia. Nyt ja käynnissä oleva
    työ päivittyvät ilman kenttiä; Työt seuraa työtä 42 ilman toivekenttää, kirjoitustilassa kenttä ilman päivitystä."""
    tulokset = {}
    for polku in ("/hub", "/hub/keskustelu", "/hub/kehita", "/hub/kehita?kirjoita=1", "/hub/kehita?toive=x",
                  "/hub/kehita/41", "/hub/kehita/42", "/hub/kehita/98", "/hub/asetukset", "/hub/dokumentit"):
        r = demo_client.get(polku + ("&" if "?" in polku else "?") + "demo=1")
        kentat = [k for k in soup(r).find_all(["textarea", "select", "input"]) if k.get("type") != "hidden"]
        assert not ("refresh" in r.headers and kentat), polku
        tulokset[polku] = ("refresh" in r.headers, bool(kentat))
    assert tulokset["/hub"] == (True, False) and tulokset["/hub/kehita/42"] == (True, False)
    assert tulokset["/hub/kehita"] == (True, False) and tulokset["/hub/kehita?kirjoita=1"] == (False, True)
    assert tulokset["/hub/kehita?toive=x"] == (False, True) and tulokset["/hub/keskustelu"] == (False, True)
    assert tulokset["/hub/kehita/98"] == (False, True)


# --- Raja (kehitystila): vain luku, oma alkuperä, Unix-soketti ----------------------------------------------------

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
@pytest.mark.parametrize("path", ["/hub", "/hub/keskustelu", "/hub/asetukset", "/hub/static/app.css"])
def test_all_mutating_or_unneeded_methods_fail_closed(demo_client, method, path):
    response = demo_client.request(method, path, content='{"approve":true}')
    assert response.status_code == 403
    assert "Pääsy estetty" in response.text
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("headers", [
    {"host": "evil.org"}, {"host": "ilmari.local:80"}, {"host": "ILMARI.LOCAL"},
    {"host": "ilmari.local.evil.org"}, {"host": ""},
    [("host", "ilmari.local"), ("host", "evil.org")],
    [("host", "ilmari.local"), ("host", "ilmari.local")],
    {"origin": "https://evil.org"}, {"origin": "null"}, {"origin": "http://ilmari.local:80"},
    {"origin": "https://ilmari.local"},
    {"origin": "https://ilmari.local.evil.org"},
    [("origin", "http://ilmari.local"), ("origin", "https://evil.org")],
    [("origin", "http://ilmari.local"), ("origin", "http://ilmari.local")],
    {"sec-fetch-site": "cross-site"}, {"sec-fetch-site": "same-site"},
    [("sec-fetch-site", "same-origin"), ("sec-fetch-site", "cross-site")],
    [("sec-fetch-site", "same-origin"), ("sec-fetch-site", "same-origin")],
    {"tailscale-funnel-request": "true"}, {"tailscale-funnel-request": "false"},
])
def test_untrusted_host_origin_fetch_metadata_or_funnel_is_rejected(demo_client, headers):
    response = demo_client.get("/hub?demo=1", headers=headers)
    assert response.status_code == 403
    assert "Pääsy estetty" in response.text
    assert "Aamuraportti" not in response.text


@pytest.mark.parametrize("headers", [
    {}, {"origin": "http://ilmari.local"},
    {"sec-fetch-site": "none"}, {"sec-fetch-site": "same-origin"},
])
def test_allowed_unix_origin_has_corresponding_happy_path(demo_client, headers):
    assert demo_client.get("/hub", headers=headers).status_code == 200


def test_https_origin_matches_https_request_scheme():
    client = TestClient(create_app(), base_url="https://ilmari.local", client=None)
    assert client.get("/hub", headers={"origin": "https://ilmari.local"}).status_code == 200
    assert client.get("/hub", headers={"origin": "http://ilmari.local"}).status_code == 403


@pytest.mark.parametrize("identity", [{}, {"tailscale-user-login": "owner@example.org"}, {"tailscale-user-login": "owner@example.org", "x-forwarded-host": "ilmari.local", "x-forwarded-for": "100.64.0.1", "x-forwarded-proto": "https"}])
def test_tcp_cannot_spoof_a_trusted_tailscale_identity(identity):
    client = TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=("127.0.0.1", 12345))
    assert client.get("/hub?demo=1", headers=identity).status_code == 403


def test_security_headers_cover_success_denial_redirects_missing_pages_and_assets(demo_client):
    responses = (
        demo_client.get("/hub"), demo_client.get("/does-not-exist"),
        demo_client.get("/hub", headers={"host": "evil.org"}),
        demo_client.get("/hub/static/app.css"), demo_client.get("/hub/static/fonts/IBMPlexMono-Regular.woff2"),
        demo_client.get("/hub/ilmari", follow_redirects=False),
    )
    for response in responses:
        policy = response.headers["content-security-policy"]
        for directive in ("default-src 'none'", "script-src 'none'", "connect-src 'none'", "frame-ancestors 'none'",
                          "object-src 'none'", "base-uri 'none'", "font-src 'self'", "style-src 'self'"):
            assert directive in policy
        assert "unsafe-inline" not in policy and "https:" not in policy
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", ["/hub/kehita/unknown", "/hub/kehita/%2E%2E%2Fsecret", "/hub/dokumentit/x",
                                  "/missing", "/hub/static/../app.py"])
def test_missing_and_invalid_identifiers_have_safe_error_pages(demo_client, path):
    response = demo_client.get(path + "?demo=1")
    assert response.status_code == 404
    assert soup(response).find("main", id="main") or "Not Found" in response.text
    assert "Traceback" not in response.text and "/srv/aiops" not in response.text


def test_virhesivu_on_samaa_tyylia(demo_client):
    dom = soup(demo_client.get("/hub/ei-ole?demo=1"))
    assert dom.title.get_text() == "Sivua ei löydy · Ilmari" and dom.select_one("a.back")["href"] == "/hub?demo=1"
    assert not dom.select('nav a[aria-current="page"]')


@pytest.mark.parametrize("value,expected", [
    ("2026-10-13T22:05:00Z", "14.10.2026 klo 01.05"),
    ("2026-01-13T22:05:00Z", "14.01.2026 klo 00.05"),
    ("2026-10-13T22:05:00+03:00", "13.10.2026 klo 22.05"),
    ("2026-10-13T22:05:00", "Ei saatavilla"),
    ("invalid", "Ei saatavilla"), (None, "Ei saatavilla"),
])
def test_display_timestamps_use_helsinki_and_reject_ambiguous_times(value, expected):
    assert format_time(value) == expected


def test_lyhyt_aika_ei_nayta_paivamaaralta():
    """Tämän päivän aika on "klo 20.05" (ei luettavissa päiväksi 20.5.), muu "18.11. klo 21.14"; sitovat välilyönnit
    pitävät ajan yhdellä rivillä."""
    from datetime import datetime, timedelta
    from ilmari_ui.app import HELSINKI
    nyt = datetime.now(HELSINKI).replace(hour=20, minute=5, second=0, microsecond=0)
    assert lyhyt_aika(nyt.isoformat()) == "klo\u00a020.05"
    eilen = nyt - timedelta(days=1)
    assert lyhyt_aika(eilen.isoformat()) == f"{eilen.day}.{eilen.month}.\u00a0klo\u00a020.05"
    assert lyhyt_aika("2026-11-18T21:14:00") == "" and lyhyt_aika(None) == ""   # ilman vyöhykettä ei arvata


def test_koneen_ika_ymmarrettavasti():
    from types import SimpleNamespace as K
    assert koneen_ika(K(ika_s=20, vanhentunut=False, paivitetty="")) == "päivitetty 20 s sitten"
    assert koneen_ika(K(ika_s=None, vanhentunut=True, paivitetty="")) == "päivitysaika ei tiedossa"
    assert koneen_ika(K(ika_s=1500, vanhentunut=True, paivitetty="")) == "päivitetty 25 min sitten"
    assert koneen_ika(K(ika_s=7300, vanhentunut=True, paivitetty="")) == "päivitetty 2 h sitten"
    vanha = K(ika_s=27937 * 60, vanhentunut=True, paivitetty="2026-10-30T10:00:00+00:00")
    assert koneen_ika(vanha) == "päivitetty 30.10.\u00a0klo\u00a012.00"


def test_vanhentunut_konetieto_varoittaa_ja_himmenee():
    """Vanhentuneen konetiedon reunateksti on varoitusvärinen: tyylin pitää voittaa .label .aside -väri."""
    css = (PACKAGE_DIR / "static" / "app.css").read_text(encoding="utf-8")
    assert ".label .aside.warn { color: var(--warn); }" in css
