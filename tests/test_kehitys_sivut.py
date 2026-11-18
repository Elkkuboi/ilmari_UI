"""Kehitä-näkymä (aiops ADR-0024): lista, työ, linkit gatewayhin, escapetus, 404 ja lähteettömyys."""

from bs4 import BeautifulSoup
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


def test_ilmarin_oma_tyo_listassa_ja_sivulla():
    """18.11. (aiops ADR-0032): gateway julkaisee myös Ilmarin omat dsh-työt (ilmari-dsh); työtilan työ näkyy ilman
    päätöstä ja linkkiä gatewayn kehitystyösivulle."""
    c = asiakas()
    r = c.get("/hub/kehita?demo=1")
    # Pala 1b: Ilmarin työ omassa listassaan, ei Eliaksen kehitystöissä
    sivu = BeautifulSoup(r.text, "html.parser")
    eliaksen, ilmarin = (sivu.find("section", attrs={"aria-labelledby": n}) for n in ("dev-jobs", "dev-ilmari"))
    assert r.status_code == 200 and ilmarin.find("a", href=lambda h: h.startswith("/hub/kehita/43?"))
    assert "· oma" in ilmarin.get_text() and "Ilmarin omat työt 1" in " ".join(ilmarin.h2.get_text().split())
    assert not eliaksen.find("a", href=lambda h: h.startswith("/hub/kehita/43?"))
    assert eliaksen.find("a", href=lambda h: h.startswith("/hub/kehita/41?"))
    r = c.get("/hub/kehita/43?demo=1")
    assert r.status_code == 200 and "ILMARIN OMA TYÖ" in r.text and "LÄHDE OMA" in r.text
    assert "Ilmarin oma pysyvä työtila" in r.text and "päätöstä ei tarvita" in r.text
    assert "Katso diff ja testit alta ja päätä" not in r.text and "Työn sivu gatewayssa" not in r.text


def test_tuotannossa_tyotilan_tyolle_ei_hyvaksyntaa(tmp_path, monkeypatch):
    """Kielletty suunta: työtilan (oma) työlle ei Hyväksy-, Hylkää- eikä muutoslomaketta. Sallittu suunta: Ilmarin
    aiops-työlle sama Hyväksy-linkki kuin Eliaksen toiveelle."""
    import json
    import os
    juuri = tmp_path / "kehitys"
    for tyo, lahde in ((43, "oma"), (44, "aiops")):
        (juuri / str(tyo)).mkdir(parents=True)
        (juuri / str(tyo) / "meta.json").write_text(json.dumps({
            "tyo": tyo, "toive": "Ilmarin tehtävä", "jatka": None, "luotu": "2026-11-18T12:00:00+00:00",
            "jattaja": "aiops-ceo", "lahde": lahde, "tila": "succeeded", "valmis": True, "tiedostot": [],
            "tulos": {"paluukoodi": 0, "haara": f"ilmari/{tyo}", "paa": "b" * 40, "commiteja": 1}}))
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({os.getuid()}))
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    otsakkeet = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        oma, aiops = client.get("/kehita/43", headers=otsakkeet), client.get("/kehita/44", headers=otsakkeet)
    assert oma.status_code == 200 and aiops.status_code == 200
    assert "/kehitys/43/hyvaksy" not in oma.text and "/kehitys/43/hylkaa" not in oma.text and 'name="jatka"' not in oma.text
    assert 'href="https://tyoasema.test/kehitys/44/hyvaksy?paluu=hub"' in aiops.text and "ILMARIN OMA TYÖ" in aiops.text


def test_tuotannossa_kaksi_listaa(tmp_path, monkeypatch):
    """Pala 1b: Eliaksen toive näkyy Kehitystöissä, vaikka Ilmari on tehnyt sen jälkeen 60 omaa työtä; Ilmarin työt
    omassa listassaan (50 uusinta). Käynnissä oleva Ilmarin työ päivittää sivun kuten Eliaksenkin."""
    import json
    import os
    juuri = tmp_path / "kehitys"

    def kirjoita(tyo, jattaja, tila="succeeded"):
        (juuri / str(tyo)).mkdir(parents=True)
        (juuri / str(tyo) / "meta.json").write_text(json.dumps({
            "tyo": tyo, "toive": f"Työ {tyo} <b>x</b>", "jatka": None, "luotu": "2026-11-18T12:00:00+00:00",
            "jattaja": jattaja, "lahde": "oma" if jattaja == "aiops-ceo" else "aiops", "tila": tila, "valmis": True,
            "tiedostot": []}))
    kirjoita(5, "elias")
    for tyo in range(10, 70):
        kirjoita(tyo, "aiops-ceo", "running" if tyo == 69 else "succeeded")
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({os.getuid()}))
    root = tmp_path / "ajot"
    root.mkdir()
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(root), "kayttajat": {"elias@github": "elias"}}})
    with TestClient(create_app(Settings(runs_dir=config.runs_dir, identity=config)), base_url="http://localhost",
                    client=None) as client:
        r = client.get("/kehita", headers={"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"})
    sivu = BeautifulSoup(r.text, "html.parser")
    eliaksen, ilmarin = (sivu.find("section", attrs={"aria-labelledby": n}) for n in ("dev-jobs", "dev-ilmari"))

    def numerot(osio):
        return [int(a["href"].split("?")[0].rsplit("/", 1)[1]) for a in osio.find_all("a", href=True)
                if "/kehita/" in a["href"]]
    assert r.status_code == 200 and numerot(eliaksen) == [5]
    assert numerot(ilmarin) == list(range(69, 19, -1)) and r.headers.get("Refresh") == "15"
    assert "&lt;b&gt;x&lt;/b&gt;" in r.text and not sivu.find_all("b")
