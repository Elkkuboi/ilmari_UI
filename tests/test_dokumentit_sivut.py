"""Dokumentit-näkymä (aiops istunto 2; Hub juureksi 18.11.2026: Asetusten alla): lista, haku, dokumentti, escapetus,
404 ja vanhan Säännöt-sivun ohjaus."""

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_lista_ja_haku_esimerkkitilassa():
    c = asiakas()
    r = c.get("/hub/dokumentit?demo=1")
    assert r.status_code == 200 and "Esimerkkiarkkitehtuuri" in r.text and "ADR-0099: Esimerkkipäätös" in r.text
    assert "Esimerkkitila" in r.text and 'href="/hub/dokumentit/adr-0099-esimerkki?demo=1"' in r.text
    lomake = BeautifulSoup(r.text, "html.parser").find("form", role="search")
    assert lomake["method"] == "get" and lomake["action"] == "/hub/dokumentit"
    otsikot = [h.get_text(" ", strip=True) for h in BeautifulSoup(r.text, "html.parser").select("h2.label")]
    assert "Päätökset" in otsikot and "ADR)" not in r.text and "asennettu versio" not in r.text   # ei jargonia
    r = c.get("/hub/dokumentit?demo=1&q=periaate")
    haku = BeautifulSoup(r.text, "html.parser").find("h2", id="h-haku")
    assert r.status_code == 200 and haku.find(string=True, recursive=False).strip() == "Haku"
    assert haku.find("span", class_="aside").get_text() == "”periaate” · 1\u00a0osuma"
    # tyhjä tulos: hakusana reunassa ja yksi rivi, ei lukumäärää kahdesti
    haku = BeautifulSoup(c.get("/hub/dokumentit?demo=1&q=xyzzy").text, "html.parser").find("section", attrs={"aria-labelledby": "h-haku"})
    assert haku.find("span", class_="aside").get_text() == "”xyzzy”" and [p.get_text() for p in haku.select("p.empty")] == ["Ei osumia."]


def test_dokumentti_piirretaan_ilman_raakaa_htmlaa():
    r = asiakas().get("/hub/dokumentit/adr-0099-esimerkki?demo=1")
    assert r.status_code == 200 and "<script>alert" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<pre" in r.text and "koodilohko" in r.text
    assert BeautifulSoup(r.text, "html.parser").find("div", class_="prose") is not None


def test_dokumentin_otsikko_ei_toistu():
    """Markdownin ensimmäinen pääotsikko on sama kuin sivun otsikko: se jätetään pois. Muut otsikot säilyvät; reunassa
    ei tiedostopolkua eikä versiotunnistetta."""
    sivu = BeautifulSoup(asiakas().get("/hub/dokumentit/arkkitehtuuri?demo=1").text, "html.parser")
    otsikko = sivu.find("h1", id="h-dok").find(string=True, recursive=False).strip()
    assert otsikko == "Esimerkkiarkkitehtuuri"
    assert otsikko.lower() not in [h.get_text().lower() for h in sivu.select(".prose h2")]
    assert "docs/" not in sivu.find("h1", id="h-dok").get_text()


def test_taulukko_ja_lihavointi():
    c = asiakas()
    assert '<th scope="col">Osa</th>' in c.get("/hub/dokumentit/tilanne?demo=1").text
    assert "<strong>datana</strong>" in c.get("/hub/dokumentit/arkkitehtuuri?demo=1").text


def test_tuntematon_ja_kelvoton_tunniste_404():
    c = asiakas()
    assert c.get("/hub/dokumentit/ei-ole?demo=1").status_code == 404
    assert c.get("/hub/dokumentit/ISO?demo=1").status_code == 404


def test_ilman_esimerkkitilaa_lahdetta_ei_ole():
    r = asiakas().get("/hub/dokumentit")
    assert r.status_code == 200 and "Dokumentit eivät ole saatavilla" in r.text


def test_asetuksissa_aktiivinen_ja_linkki_asetuksista():
    c = asiakas()
    for polku in ("/hub/dokumentit?demo=1", "/hub/dokumentit/arkkitehtuuri?demo=1"):
        nykyinen = BeautifulSoup(c.get(polku).text, "html.parser").select('nav a[aria-current="page"]')
        assert [a.get_text() for a in nykyinen] == ["Asetukset"]
    assert 'href="/hub/dokumentit?demo=1"' in c.get("/hub/asetukset?demo=1").text


def test_vanha_saantosivu_ohjautuu_dokumentteihin():
    r = asiakas().get("/hub/saannot?demo=1", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/hub/dokumentit?demo=1"
