"""Browser checks through ASGI interception: no listening TCP server."""

from pathlib import Path
import shutil
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app

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


PAGES = ["/hub", "/hub/keskustelu", "/hub/kehita", "/hub/kehita/41", "/hub/kehita/98", "/hub/asetukset",
         "/hub/dokumentit", "/hub/dokumentit/arkkitehtuuri", "/hub/kehotteet", "/hub/kehotteet/jarjestelma"]


@pytest.mark.parametrize("width", [320, 390, 768, 1280])
@pytest.mark.parametrize("path", PAGES)
def test_all_views_have_usable_layout(page, path, width):
    page.set_viewport_size({"width": width, "height": 960})
    response = page.goto(f"https://ilmari.local{path}?demo=1")
    assert response.status == 200
    assert page.get_by_role("main").is_visible()
    assert page.locator("h1").count() == 1
    assert page.locator("script").count() == 0
    assert page.get_by_role("navigation", name="Päävalikko").locator("a").count() == 4
    assert_no_overflow(page)
    if width in (390, 1280):
        output = Path("artifacts/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        name = path.strip("/").replace("/", "-") or "hub"
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
