"""Kehitä-näkymä (aiops ADR-0024): lista, työ, linkit gatewayhin, escapetus, 404 ja lähteettömyys."""

from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import parse_config


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def test_lista_esimerkkitilassa():
    r = asiakas().get("/hub/kehita?demo=1")
    assert r.status_code == 200 and "Kehitystyöt" in r.text and 'href="/hub/kehita/41?' in r.text
    assert "Otettu käyttöön" in r.text and "Käynnissä" in r.text and "Hylätty" in r.text and "Esimerkkitila" in r.text
    assert "Yöajon ehdotukset" in r.text and "Käyttöönotot" in r.text and "Testit epäonnistuivat" in r.text
    assert 'href="https://claude.ai/code"' in r.text and 'action="' not in r.text  # ei lomaketta gatewaylle esimerkkitilassa
    assert "<script" not in r.text.replace("<script>alert", "")  # ei skriptejä (CSP)
    assert "· ravintopolku" in r.text and r.text.count("· aiops") == 0  # lähde (aiops ADR-0030), oletusta ei toisteta


def test_tyon_lahde_nakyy_otsikossa():
    c = asiakas()
    assert "· LÄHDE RAVINTOPOLKU" in c.get("/hub/kehita/42?demo=1").text
    assert "LÄHDE" not in c.get("/hub/kehita/41?demo=1").text  # vanha työ ilman lähdettä


def test_tyo_ja_escapetus():
    r = asiakas().get("/hub/kehita/41?demo=1")
    assert r.status_code == 200 and "Otettu käyttöön" in r.text and "Yhdistetty mainiin" in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<script>alert" not in r.text
    assert "&lt;b&gt;ei html&lt;/b&gt;" in r.text and "Koko diff" in r.text and "Työn loki" in r.text
    assert "2300 passed, 2 skipped" in r.text and 'href="#esimerkkitila"' in r.text  # gatewayn linkki ei esimerkkitilassa


def test_tuntematon_tyo_404_ja_lahteettomyys():
    c = asiakas()
    assert c.get("/hub/kehita/999?demo=1").status_code == 404
    assert c.get("/hub/kehita/abc?demo=1").status_code == 404
    assert c.get("/hub/kehita/41").status_code == 404  # ei esimerkkitilaa eikä tuotantoa: ei lähdettä
    r = c.get("/hub/kehita")
    assert r.status_code == 200 and "lähdettä ei ole määritetty" in r.text


def test_valikossa_on_kehita():
    assert 'href="/hub/kehita' in asiakas().get("/hub?demo=1").text


def test_tuotannossa_linkit_gatewayn_alkuperaan(tmp_path):
    """Serve poistaa /hub-etuliitteen (RestorePrefix): tuotannossa pyyntö /kehita on selaimen /hub/kehita."""
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/kehita", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                           "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    assert r.status_code == 200 and 'action="https://tyoasema.test/kehita"' in r.text
    assert "Kehitystö" in r.text  # testikoneella /srv/aiops/ilmari/kehitys puuttuu tai ei ole luettavissa


def test_eteneminen_diff_ja_toimet_sivuilla():
    """31.10.: eteneminen käynnissä olevalle työlle, diff tiedostoittain, palautus ja päivitys kesken olevalle."""
    c = asiakas()
    r = c.get("/hub/kehita/42?demo=1")
    assert r.status_code == 200 and "Ilmari nyt" in r.text and "Suunnittelen SearXNG" in r.text
    assert r.headers.get("Refresh") == "15" and "päivittyy itsestään" in r.text
    r = c.get("/hub/kehita/41?demo=1")
    assert "Refresh" not in r.headers and "Muutokset tiedostoittain" in r.text and "diff-line--add" in r.text
    assert "<code>docs/TILANNE.md</code>" in r.text and "edellinen <code>cccccccccccc</code>" in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    r = c.get("/hub/kehita?demo=1")
    assert "Nyt: Suunnittelen SearXNG" in r.text and r.headers.get("Refresh") == "15"
    assert 'action="' not in r.text  # esimerkkitilassa ei lomaketta gatewaylle


def test_tuotannossa_lomakkeet_gatewaylle(tmp_path):
    """Hub ensisijaiseksi: toive, muutospyyntö ja hylkäys ovat lomakkeita gatewaylle (paluu=hub), passkey-toimet linkkejä."""
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/kehita", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github",
                                           "x-forwarded-proto": "https", "x-forwarded-for": "100.67.5.28"})
    assert r.status_code == 200 and 'action="https://tyoasema.test/kehita"' in r.text
    assert 'name="paluu" value="hub"' in r.text and 'name="lahde"' in r.text and "ravintopolku" in r.text
    assert "Kehitystö" in r.text


def test_kehita_on_puhelimen_alapalkissa():
    r = asiakas().get("/hub?demo=1")
    alapalkki = r.text.split('class="bottom-nav"')[1].split("</nav>")[0]
    assert 'href="/hub/kehita' in alapalkki and "Kehitä" in alapalkki
