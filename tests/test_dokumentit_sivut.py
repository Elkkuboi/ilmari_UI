"""Dokumentit-näkymä (aiops istunto 2): lista, haku, dokumentti, escapetus ja 404."""

from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_lista_ja_haku_esimerkkitilassa():
    c = asiakas()
    r = c.get("/hub/dokumentit?demo=1")
    assert r.status_code == 200 and "Esimerkkiarkkitehtuuri" in r.text and "ADR-0099: Esimerkkipäätös" in r.text
    assert "Esimerkkitila" in r.text and 'href="/hub/dokumentit/adr-0099-esimerkki?' in r.text
    r = c.get("/hub/dokumentit?demo=1&q=periaate")
    assert r.status_code == 200 and "Haku: periaate" in r.text and "1 osuma" in r.text


def test_dokumentti_piirretaan_ilman_raakaa_htmlaa():
    r = asiakas().get("/hub/dokumentit/adr-0099-esimerkki?demo=1")
    assert r.status_code == 200 and "<script>alert" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<pre" in r.text and "koodilohko" in r.text


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
    assert r.status_code == 200 and "Dokumenttien lähdettä ei ole määritetty" in r.text


def test_valikossa_on_dokumentit():
    assert 'href="/hub/dokumentit' in asiakas().get("/hub?demo=1").text
