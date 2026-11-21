"""Browser checks through ASGI interception: no listening TCP server."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
from ilmari_ui.keskustelu import ESIMERKKI

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api", reason="Asenna valinnainen browser-kehitysryhmä.")
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        pytest.skip("Järjestelmän Chromiumia ei ole asennettu.")
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(executable_path=chromium, headless=True, args=["--no-sandbox", "--disable-background-networking"])
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce", service_workers="block")
    client = TestClient(create_app(Settings(demo_enabled=True)), base_url="https://ilmari.local", client=None)
    failures, external = [], []
    tab = context.new_page()
    tab.on("pageerror", lambda error: failures.append(str(error)))

    def forward(route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.hostname != "ilmari.local":
            external.append(request.url)
            route.abort()
            return
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        response = client.request(request.method, path, headers={**request.headers, "host": "ilmari.local"}, follow_redirects=False)
        route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)

    tab.route("**/*", forward)
    yield tab
    assert not failures, failures
    assert not external, external
    context.close()
    client.close()


def assert_no_overflow(page):
    metrics = page.evaluate("({width: innerWidth, content: document.documentElement.scrollWidth})")
    assert metrics["content"] <= metrics["width"] + 1, metrics


PAGES = ["/hub", "/hub/keskustelu", "/hub/keskustelu?lista=1", "/hub/kehita", "/hub/kehita/41", "/hub/kehita/98",
         "/hub/asetukset", "/hub/dokumentit", "/hub/dokumentit/arkkitehtuuri", "/hub/kehotteet",
         "/hub/kehotteet/jarjestelma"]


@pytest.mark.parametrize("width", [320, 390, 768, 1280])
@pytest.mark.parametrize("path", PAGES)
def test_all_views_have_usable_layout(page, path, width):
    page.set_viewport_size({"width": width, "height": 960})
    response = page.goto(f"https://ilmari.local{path}{'&' if '?' in path else '?'}demo=1")
    assert response.status == 200
    assert page.get_by_role("main").is_visible()
    assert page.locator("h1").count() == 1
    assert page.locator("script").count() == 0
    assert page.get_by_role("navigation", name="Päävalikko").locator("a").count() == 4
    assert_no_overflow(page)
    if width in (390, 1280):
        output = Path("artifacts/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        name = path.strip("/").replace("/", "-").replace("?", "-").replace("=", "") or "hub"
        page.screenshot(path=str(output / f"{name}-{'puhelin' if width == 390 else 'tyopoyta'}.png"), full_page=True)


def test_keyboard_skip_link_and_local_font(page):
    page.goto("https://ilmari.local/hub?demo=1")
    page.keyboard.press("Tab")
    assert page.locator(".skip-link").evaluate("element => element === document.activeElement")
    outline = page.locator(".skip-link").evaluate("element => getComputedStyle(element).outlineStyle")
    assert outline not in ("none", "hidden")
    assert "IBM Plex Mono" in page.locator("body").evaluate("element => getComputedStyle(element).fontFamily")


def test_two_hundred_percent_layout_and_touch_targets(page):
    # 1440 device pixels at 200% browser zoom produce a 720 CSS-pixel viewport.
    page.set_viewport_size({"width": 720, "height": 480})
    page.goto("https://ilmari.local/hub?demo=1")
    assert_no_overflow(page)
    targets = page.locator("main button").evaluate_all("items => items.map(e => e.getBoundingClientRect().height)")
    assert targets and all(height >= 44 for height in targets)


def in_view(locator) -> bool:
    return locator.evaluate("e => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight + 1; }")


@pytest.mark.parametrize("width,height,page_fits", [(390, 844, True), (1280, 900, True), (320, 568, True),
                                                     (390, 450, False)])
def test_conversation_scrolls_inside_its_box_newest_at_bottom(page, tmp_path, monkeypatch, width, height, page_fits):
    """21.11.2026: 40 messages do not lengthen the page. Only the message box scrolls, it starts at the newest
    message (column-reverse, no script), and the writing box stays in view. Lähetä sits beside the field, so it is in
    view whenever the field is, also with the keyboard open (390x450, where the demo note may scroll the page a little).
    On a narrow phone the two actions share one row."""
    demo = tmp_path / "keskustelu"
    demo.mkdir()
    source = ESIMERKKI
    data = json.loads((source / "viestit.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    data["viestit"] = [{"id": n, "aika": (now + timedelta(seconds=n)).isoformat(timespec="seconds"),
                        "lahettaja": "elias" if n % 2 else "ilmari", "teksti": f"Viesti {n}: " + "sana " * (n % 7 * 6),
                        "saie": data["saie"]["id"]} for n in range(1, 41)]
    data["viimeisin"] = 40
    (demo / "viestit.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (demo / "saikeet.json").write_bytes((source / "saikeet.json").read_bytes())
    monkeypatch.setattr("ilmari_ui.keskustelu.ESIMERKKI", demo)
    page.set_viewport_size({"width": width, "height": height})
    assert page.goto("https://ilmari.local/hub/keskustelu?demo=1").status == 200
    box = page.locator(".chat-scroll")
    metrics = box.evaluate("e => ({top: e.scrollTop, scroll: e.scrollHeight, client: e.clientHeight})")
    assert metrics["scroll"] > metrics["client"] + 100, metrics      # the box scrolls instead of the page growing
    assert abs(metrics["top"]) <= 1, metrics                          # column-reverse: starts at the newest message
    last = page.locator(".chat > .msg").last
    assert "Viesti 40" in last.inner_text()
    assert last.evaluate("(e) => { const r = e.getBoundingClientRect(), b = e.closest('.chat-scroll').getBoundingClientRect();"
                         " return r.bottom <= b.bottom + 1 && r.bottom > b.top; }")
    assert not page.locator(".chat > .msg").first.evaluate(
        "(e) => { const r = e.getBoundingClientRect(), b = e.closest('.chat-scroll').getBoundingClientRect();"
        " return r.bottom > b.top; }")                                 # the oldest is above, reached by scrolling up
    assert_no_overflow(page)
    field, send = page.locator("#viesti"), page.get_by_role("button", name="Lähetä", exact=True)
    rect = "e => { const r = e.getBoundingClientRect(); return [r.top, r.bottom]; }"
    (field_top, field_bottom), (send_top, send_bottom) = field.evaluate(rect), send.evaluate(rect)
    assert send_top < field_bottom and send_bottom > field_top        # same row: visible together
    new, listing = page.get_by_text("+ Uusi keskustelu"), page.get_by_role("link", name="Keskustelut")
    assert abs(new.evaluate(rect)[0] - listing.evaluate(rect)[0]) <= 1
    if page_fits:
        assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1")
        assert in_view(field) and in_view(last) and in_view(new) and in_view(send)
    field.scroll_into_view_if_needed()                                 # what the browser does when the field is focused
    assert in_view(field) and in_view(send)
