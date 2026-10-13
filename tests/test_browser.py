"""Browser checks through ASGI interception: no listening TCP server."""

from pathlib import Path
import shutil
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ilmari_ui.app import Settings, create_app
from ilmari_ui.themes import SKINS

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


@pytest.mark.parametrize("width", [320, 375, 412, 768, 1024, 1440])
@pytest.mark.parametrize("skin", [skin["id"] for skin in SKINS])
def test_home_skins_and_responsive_layout(page, skin, width):
    page.set_viewport_size({"width": width, "height": 960})
    response = page.goto(f"https://ilmari.local/hub?demo=1&skin={skin}")
    assert response.status == 200
    assert page.locator("html").get_attribute("data-skin") == skin
    assert page.locator("h1").count() == 1
    assert page.locator(".demo-banner").is_visible()
    assert page.locator("script").count() == 0
    assert_no_overflow(page)
    if width in (375, 1440):
        output = Path("artifacts/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / f"{skin}-{'mobile' if width == 375 else 'desktop'}.png"), full_page=True)
    if width < 768:
        assert page.get_by_role("navigation", name="Puhelimen päänavigaatio").is_visible()
        page.locator(".mobile-menu summary").click()
        assert page.get_by_role("navigation", name="Kaikki osiot").is_visible()


PAGES = ["/hub", "/hub/keskustelu", "/hub/ajot", "/hub/hyvaksynnat", "/hub/sovellukset", "/hub/ideat", "/hub/jarjestelma", "/hub/asetukset", "/hub/sovellukset/ravintopolku", "/hub/sovellukset/unicafe", "/hub/sovellukset/ideat", "/hub/sovellukset/jarvis", "/hub/ajot/20261013-001914-yo-demo"]


@pytest.mark.parametrize("width", [320, 768, 1440])
@pytest.mark.parametrize("path", PAGES)
def test_all_views_have_usable_layout(page, path, width):
    page.set_viewport_size({"width": width, "height": 960})
    response = page.goto(f"https://ilmari.local{path}?demo=1")
    assert response.status == 200
    assert page.get_by_role("main").is_visible()
    assert page.locator("h1").count() == 1
    assert_no_overflow(page)


def test_keyboard_theme_navigation_and_chart_data(page):
    page.goto("https://ilmari.local/hub?demo=1")
    page.keyboard.press("Tab")
    assert page.locator(".skip-link").evaluate("element => element === document.activeElement")
    outline = page.locator(".skip-link").evaluate("element => getComputedStyle(element).outlineStyle")
    assert outline not in ("none", "hidden")
    page.keyboard.press("Enter")
    assert page.locator("#main").evaluate("element => element === document.activeElement")
    page.goto("https://ilmari.local/hub/asetukset?demo=1")
    page.get_by_role("link", name="Nordic Paper", exact=False).first.click()
    assert page.locator("html").get_attribute("data-skin") == "nordic-paper"
    page.goto("https://ilmari.local/hub/sovellukset/ravintopolku?demo=1&skin=nordic-paper")
    assert page.get_by_role("img", name="Kalorimäärä", exact=False).count() >= 1
    page.get_by_text("Näytä kaavion tiedot taulukkona", exact=True).click()
    assert page.get_by_role("cell", name="Puuttuva tieto", exact=True).is_visible()
    assert_no_overflow(page)


def test_two_hundred_percent_layout_and_touch_targets(page):
    # 1440 device pixels at 200% browser zoom produce a 720 CSS-pixel viewport.
    page.set_viewport_size({"width": 720, "height": 480})
    page.goto("https://ilmari.local/hub/asetukset?demo=1")
    assert_no_overflow(page)
    targets = page.locator(".bottom-nav a").evaluate_all("items => items.map(e => ({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))")
    assert targets and all(item["width"] >= 44 and item["height"] >= 44 for item in targets)
