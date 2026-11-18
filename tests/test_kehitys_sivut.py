"""Työt (Kehitä, aiops ADR-0024; Hub juureksi 18.11.2026): lista, työn sivu, linkit ja lomakkeet gatewayhin,
escapetus, 404, lähteettömyys ja automaattinen päivitys."""

import json
import os

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
from ilmari_ui.config import parse_config

UID = os.getuid()
OTSAKKEET = {"x-forwarded-host": "tyoasema.test", "tailscale-user-login": "elias@github"}


def asiakas() -> TestClient:
    return TestClient(create_app(Settings(demo_enabled=True)), base_url="http://ilmari.local", client=None)


def tuotanto(tmp_path) -> TestClient:
    config = parse_config({"hub": {"rp_id": "tyoasema.test", "julkaisut": str(tmp_path / "ajot"),
                                   "kayttajat": {"elias@github": "elias"}}})
    return TestClient(create_app(Settings(identity=config)), base_url="http://localhost", client=None)


def kirjoita(juuri, tyo, jattaja="elias", lahde="aiops", tila="succeeded", **lisat):
    (juuri / str(tyo)).mkdir(parents=True)
    (juuri / str(tyo) / "meta.json").write_text(json.dumps({
        "tyo": tyo, "toive": f"Työ {tyo} <b>x</b>", "jatka": None, "luotu": "2026-11-18T12:00:00+00:00",
        "jattaja": jattaja, "lahde": lahde, "tila": tila, "valmis": True, "tiedostot": [],
        "tulos": {"paluukoodi": 0, "haara": f"ilmari/{tyo}", "paa": "b" * 40, "commiteja": 1}}))
    for nimi, sisalto in lisat.items():
        (juuri / str(tyo) / f"{nimi}.json").write_text(json.dumps(sisalto))


def osio(sivu, otsikko_id):
    return sivu.find("section", attrs={"aria-labelledby": otsikko_id})


def test_lista_esimerkkitilassa():
    r = asiakas().get("/hub/kehita?demo=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and 'href="/hub/kehita/41?demo=1"' in r.text and "Esimerkkitila" in r.text
    tilat = {a["href"].split("?")[0]: a.find(class_="tag").get_text() for a in sivu.select("a.row")}
    assert tilat == {"/hub/kehita/42": "käynnissä", "/hub/kehita/41": "käytössä", "/hub/kehita/40": "hylätty",
                     "/hub/kehita/98": "hyväksy", "/hub/kehita/43": "valmis"}
    assert "Nyt: Suunnittelen SearXNG" in r.text and r.headers.get("Refresh") == "15"   # työ 42 käynnissä
    fold = sivu.find("details", class_="fold")
    assert fold.summary.get_text() == "Käyttöönotot (2)"
    assert "<form" not in r.text and 'action="' not in r.text   # esimerkkitila: ei lomakkeita
    # Hub juureksi: yöajon ehdotukset, Claude Code -linkki ja johdanto pois
    assert "Yöajon ehdotukset" not in r.text and "claude.ai" not in r.text and "Kehitä Ilmaria" not in r.text
    # käyttöönotot listana (ei taulukkoa, joka ei mahdu puhelimeen): tagi, versio, testit suomeksi, loki taittona
    rivit = fold.select("ul.rows > li")
    assert not fold.find("table") and len(rivit) == 2
    assert " ".join(rivit[0].div.get_text(" ").split()) == "28.10. klo 14.45 otettu käyttöön ddddddd"
    assert "testit 2300 läpi, 2 ohitettu" in rivit[0].get_text() and "2026-10-28T" not in fold.get_text()
    assert "testit 1 epäonnistui, 2299 läpi" in rivit[1].get_text() and "failed" not in rivit[1].find("div", class_="small").get_text()
    assert [d.summary.get_text() for d in fold.select("details.fold")] == ["Loki", "Loki"]


def test_tyo_ja_escapetus():
    r = asiakas().get("/hub/kehita/41?demo=1")
    sivu = BeautifulSoup(r.text, "html.parser")
    assert r.status_code == 200 and sivu.find("a", class_="back")["href"] == "/hub/kehita?demo=1"
    assert " ".join(sivu.h1.get_text().split()) == "Työ 41 käytössä" and sivu.h1.find("span", class_="tag ok")
    kv = {dt.get_text(): " ".join(dt.find_next_sibling("dd").get_text(" ").split()) for dt in sivu.select("dl.kv dt")}
    # työkalujen englanninkielinen tuloste suomeksi; raakatuloste jää Testit-taittoon
    assert kv["Muutokset"] == "1 tiedosto, +2 −0" and kv["Testit"] == "läpi 2300 läpi, 2 ohitettu"
    assert "files changed" not in sivu.find("dl", class_="kv").get_text() and "2300 passed, 2 skipped" in r.text
    # Päätös: jokaisesta vaiheesta tagi ja Suomen aika, ei koneen raakaviestiä, ISO-aikaa eikä mainia
    paatos = [" ".join(p.get_text(" ").split()) for p in osio(sivu, "h-paatos").find_all("p", recursive=False)]
    assert paatos == ["hyväksytty 28.10. klo 14.30", "yhdistetty 28.10. klo 14.31",
                      "otettu käyttöön 28.10. klo 14.45 · edellinen ccccccc"]   # hakasulkeet tulevat tyylistä
    assert "main" not in osio(sivu, "h-paatos").get_text() and "2026-10-28T" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<script>alert" not in r.text
    assert "&lt;b&gt;ei html&lt;/b&gt;" in r.text
    taitot = [d.summary.get_text() for d in sivu.select("details.fold")]
    assert taitot == ["Muutokset (1 tiedosto)", "Testit", "Loki"]
    # tiedostokohtainen diff riittää: koko muutos ei toistu, ja taitot ovat samassa pinossa
    assert "Koko muutos" not in r.text and "Koko diff" not in r.text
    assert {d.parent.name for d in sivu.select("details.fold")} == {"div"}
    r98 = asiakas().get("/hub/kehita/98?demo=1")
    assert "Koko muutos" not in r98.text and BeautifulSoup(r98.text, "html.parser").find("button", string="Hylkää")
    diff = sivu.find("pre", class_="diff")
    assert diff.find("span", class_="add") and diff.find("span", class_="hunk")
    assert 'href="#"' in r.text and "Palauta edelliseen puhelimella" in r.text   # esimerkkitila: linkit eivät vie mihinkään
    assert "Refresh" not in r.headers


def test_kaynnissa_oleva_tyo_paivittyy():
    r = asiakas().get("/hub/kehita/42?demo=1")
    assert r.status_code == 200 and "Suunnittelen SearXNG" in r.text and r.headers.get("Refresh") == "15"
    assert "päivittyy itsestään" in r.text


def test_tuntematon_tyo_404_ja_lahteettomyys():
    c = asiakas()
    assert c.get("/hub/kehita/999?demo=1").status_code == 404
    assert c.get("/hub/kehita/abc?demo=1").status_code == 404
    assert c.get("/hub/kehita/41").status_code == 404  # ei esimerkkitilaa eikä tuotantoa: ei lähdettä
    r = c.get("/hub/kehita")
    assert r.status_code == 200 and "Töitä ei ole saatavilla" in r.text and "Refresh" not in r.headers


def test_ilmarin_oma_tyo_listassa_ja_sivulla():
    """Ilmarin omat työt omassa listassaan; työtilan työ näkyy ilman päätöstä ja raakanäkymän linkkiä."""
    c = asiakas()
    sivu = BeautifulSoup(c.get("/hub/kehita?demo=1").text, "html.parser")
    eliaksen, ilmarin = osio(sivu, "h-omat"), osio(sivu, "h-ilmarin")
    numerot = lambda o: [a["href"].split("?")[0].rsplit("/", 1)[1] for a in o.select("a.row")]  # noqa: E731
    assert numerot(eliaksen) == ["42", "41", "40"] and numerot(ilmarin) == ["98", "43"]
    r = c.get("/hub/kehita/43?demo=1")
    assert r.status_code == 200 and "Ilmarin oma työ" in r.text
    assert not osio(BeautifulSoup(r.text, "html.parser"), "h-paatos")   # työtila: ei päätettävää, ei osiota
    assert "Raaka näkymä" not in r.text and "Hyväksy" not in r.text
    r = c.get("/hub/kehita/42?demo=1")                                 # kesken: ei vielä päätettävää
    assert r.status_code == 200 and not osio(BeautifulSoup(r.text, "html.parser"), "h-paatos")


def test_tuotannossa_toivelomake_gatewaylle(tmp_path):
    """Sallittu: toive on lomake gatewaylle (paluu=hub) kohteen valinnalla. Työ kesken: nappi pois käytöstä ja syy."""
    with tuotanto(tmp_path) as client:
        r = client.get("/kehita", headers=OTSAKKEET)
    lomake = BeautifulSoup(r.text, "html.parser").find("form", action="https://tyoasema.test/kehita")
    assert r.status_code == 200 and lomake["method"] == "post"
    assert {k["name"] for k in lomake.find_all(["input", "textarea", "select"])} == {"paluu", "toive", "lahde"}
    assert [o["value"] for o in lomake.find_all("option")] == ["aiops", "ravintopolku"]
    assert not lomake.button.has_attr("disabled") and "Töitä ei voi lukea." in r.text


def test_tuotannossa_toivelomake_pois_kaytosta_kun_tyo_kesken(tmp_path, monkeypatch):
    k = tmp_path / "keskustelu"
    k.mkdir()
    (k / "viestit.json").write_text(json.dumps({"muoto": "aiops-keskustelu-v1", "paivitetty": "2026-11-19T01:00:00+00:00",
                                                "viimeisin": 0, "malli": {"tila": "running", "dsh_tyo": 44}, "viestit": []}))
    monkeypatch.setattr("ilmari_ui.keskustelu.OLETUS", k)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    with tuotanto(tmp_path) as client:
        r = client.get("/kehita", headers=OTSAKKEET)
    lomake = BeautifulSoup(r.text, "html.parser").find("form", action="https://tyoasema.test/kehita")
    assert lomake.button.has_attr("disabled") and "Työ 44 on kesken; yksi työ kerrallaan." in r.text


def test_tuotannossa_toimet_samoilla_linkeilla_ja_lomakkeilla(tmp_path, monkeypatch):
    """Mitään toimintoa ei poisteta työn sivulta: passkey-toimet linkkeinä, hylkäys, sulku ja muutospyyntö lomakkeina."""
    juuri = tmp_path / "kehitys"
    kirjoita(juuri, 50)
    kirjoita(juuri, 51, paatos={"paatos": "hyvaksytty"}, yhdistys={"tila": "yhdistetty"})
    kirjoita(juuri, 52, paatos={"paatos": "hyvaksytty", "kayttoonotto_pyynto": "k"}, yhdistys={"tila": "yhdistetty"},
             kayttoonotto={"tulos": "asennettu", "edellinen": "c" * 40})
    kirjoita(juuri, 53, paatos={"paatos": "hyvaksytty"}, yhdistys={"tila": "ristiriita"})
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    with tuotanto(tmp_path) as client:
        sivut = {n: BeautifulSoup(client.get(f"/kehita/{n}", headers=OTSAKKEET).text, "html.parser") for n in (50, 51, 52, 53)}
    G = "https://tyoasema.test"

    def linkit(s):
        return {a["href"] for a in s.find_all("a", href=True) if a["href"].startswith(G)}

    def lomakkeet(s):
        return {f["action"]: sorted((k["name"], k.get("value", "")) for k in f.find_all(["input", "textarea"]))
                for f in s.find_all("form")}
    assert linkit(sivut[50]) == {f"{G}/kehitys/50/hyvaksy?paluu=hub", f"{G}/kehitys/50"}
    assert lomakkeet(sivut[50]) == {f"{G}/kehitys/50/hylkaa": [("paluu", "hub"), ("toiminto", "hylkaa")],
                                    f"{G}/kehita": [("jatka", "50"), ("paluu", "hub"), ("toive", "")]}
    assert linkit(sivut[51]) == {f"{G}/kehitys/51/kayttoonotto?paluu=hub", f"{G}/kehitys/51"} and not lomakkeet(sivut[51])
    assert linkit(sivut[52]) == {f"{G}/kehitys/52/palauta?paluu=hub", f"{G}/kehitys/52"} and not lomakkeet(sivut[52])
    assert lomakkeet(sivut[53]) == {f"{G}/kehitys/53/sulje": [("paluu", "hub"), ("viesti", "")]}
    assert all(f["method"] == "post" for s in sivut.values() for f in s.find_all("form"))


def test_tuotannossa_tyotilan_tyolle_ei_hyvaksyntaa(tmp_path, monkeypatch):
    """Kielletty suunta: työtilan (oma) työlle ei Hyväksy-, Hylkää- eikä muutoslomaketta. Sallittu suunta: Ilmarin
    aiops-työlle sama Hyväksy-linkki kuin Eliaksen toiveelle."""
    juuri = tmp_path / "kehitys"
    kirjoita(juuri, 43, jattaja="aiops-ceo", lahde="oma")
    kirjoita(juuri, 44, jattaja="aiops-ceo")
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    with tuotanto(tmp_path) as client:
        oma, aiops = client.get("/kehita/43", headers=OTSAKKEET), client.get("/kehita/44", headers=OTSAKKEET)
    assert oma.status_code == 200 and aiops.status_code == 200
    assert "/kehitys/43/hyvaksy" not in oma.text and "/kehitys/43/hylkaa" not in oma.text and 'name="jatka"' not in oma.text
    assert 'href="https://tyoasema.test/kehitys/44/hyvaksy?paluu=hub"' in aiops.text and "Ilmarin oma työ" in aiops.text


def test_tuotannossa_kaksi_listaa(tmp_path, monkeypatch):
    """Eliaksen toive näkyy, vaikka Ilmari on tehnyt sen jälkeen 60 omaa työtä; Ilmarin työt omassa listassaan (50
    uusinta). Käynnissä oleva Ilmarin työ päivittää sivun kuten Eliaksenkin."""
    juuri = tmp_path / "kehitys"
    kirjoita(juuri, 5)
    for tyo in range(10, 70):
        kirjoita(juuri, tyo, jattaja="aiops-ceo", lahde="oma", tila="running" if tyo == 69 else "succeeded")
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    with tuotanto(tmp_path) as client:
        r = client.get("/kehita", headers=OTSAKKEET)
    sivu = BeautifulSoup(r.text, "html.parser")

    def numerot(o):
        return [int(a["href"].rsplit("/", 1)[1]) for a in o.select("a.row")]
    assert r.status_code == 200 and numerot(osio(sivu, "h-omat")) == [5]
    assert numerot(osio(sivu, "h-ilmarin")) == list(range(69, 19, -1)) and r.headers.get("Refresh") == "15"
    assert "&lt;b&gt;x&lt;/b&gt;" in r.text and not sivu.find_all("b")


def test_valmiit_tyot_eivat_paivity(tmp_path, monkeypatch):
    juuri = tmp_path / "kehitys"
    kirjoita(juuri, 5)
    monkeypatch.setattr("ilmari_ui.kehitys.OLETUS", juuri)
    monkeypatch.setattr("ilmari_ui.kehitys.sallitut_omistajat", lambda: frozenset({UID}))
    with tuotanto(tmp_path) as client:
        r = client.get("/kehita", headers=OTSAKKEET)
        t = client.get("/kehita/5", headers=OTSAKKEET)
    assert "Refresh" not in r.headers and "Refresh" not in t.headers
