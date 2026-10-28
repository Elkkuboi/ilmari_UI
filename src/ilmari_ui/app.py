"""Lukevan Hubin ASGI-sovellus.

Palvelin toimii vain Unix-soketissa. Kehitystilassa (ei identiteettiasetusta) se hyväksyy vain Host-nimen
ilmari.local eikä todista Tailscale-identiteettiä. Tuotantotilassa (aiops ADR-0013) Tailscale Serve ohjaa polun /hub
Hubin sokettiin, ja Hub toistaa gatewayn vartijan säännöt: vain GET ja HEAD, osoite X-Forwarded-Hostista, ei
Funnel-pyyntöjä ja vain sallitut Tailscale-tunnukset. Serve poistaa etuliitteen /hub ennen välitystä, joten
tuotantotilassa se palautetaan ennen reititystä.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .cards import load_cards
from . import muodot
from .config import HubConfig
from .dokumentit import (ESIMERKKI as DOKUMENTIT_ESIMERKKI, OLETUS as DOKUMENTIT_OLETUS, etsi as etsi_dokumentti,
                         hae as hae_dokumentit, lue_dokumentit, piirrettava, ryhmittain)
from .peruskirja import lue_peruskirja
from .runs import ReadFailure, RunReader
from .themes import SKINS, normalize_skin

PACKAGE_DIR = Path(__file__).parent
HELSINKI = ZoneInfo("Europe/Helsinki")
DEMO_NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
APP_CATALOG = (
    {"id": "ravintopolku", "name": "Ravintopolku", "description": "Kirjauksista julkaistu ravintokooste. Puuttuvat päivät säilyvät puuttuvina.", "data_class": "private", "icon": "leaf"},
    {"id": "unicafe", "name": "UniCafe", "description": "Päivätty ruokalista, valitut kriteerit ja alkuperäinen lähde.", "data_class": "public", "icon": "food"},
    {"id": "ideat", "name": "Kolme business-ideaa", "description": "Ongelma, hypoteesi ja seuraava koe. Tilaa harkitulle ideoinnille.", "data_class": "private", "icon": "idea"},
    {"id": "jarvis", "name": "Joonaksen Jarvis", "description": "Vain omistajan erikseen hyväksymät ja jakamat päivitykset.", "data_class": "private", "icon": "feed"},
)
APP_IDS = tuple(app["id"] for app in APP_CATALOG)
SERVE_PREFIX = "/hub"
RUN_COUNT_LIMIT = 200
ALIASES = {"/": "/hub", "/chat": "/hub/keskustelu", "/runs": "/hub/ajot", "/approvals": "/hub/hyvaksynnat", "/apps": "/hub/sovellukset", "/ideas": "/hub/ideat", "/system": "/hub/jarjestelma", "/rules": "/hub/saannot", "/settings": "/hub/asetukset"}


@dataclass(frozen=True)
class Settings:
    """Tietolähteet ovat ylläpitäjän asetuksia, eivät selaimen syötteitä."""

    runs_dir: Path | None = None
    cards_dir: Path | None = None
    rules_dir: Path | None = None  # kehitystila; tuotannossa peruskirjan polku tulee konfiguraatiosta
    demo_enabled: bool = False
    app_classes: dict[str, str] = field(default_factory=lambda: {app["id"]: app["data_class"] for app in APP_CATALOG})
    allowed_private_apps: frozenset[str] = frozenset()
    allowed_source_hosts: frozenset[str] = frozenset()
    identity: HubConfig | None = None  # tuotantotila: Tailscale-tunnistus ja Serven etuliite (ADR-0013)

    def __post_init__(self) -> None:
        for root in (self.runs_dir, self.cards_dir, self.rules_dir):
            if root is not None and (not root.is_absolute() or root == Path("/") or ".." in root.parts):
                raise ValueError("Julkaisujuuren pitää olla yksilöity absoluuttinen hakemistopolku ilman '..'-osia.")
        if self.identity is not None:
            if self.demo_enabled:
                raise ValueError("Esimerkkitila ei ole sallittu tuotantotilassa.")
            if self.runs_dir != self.identity.runs_dir:
                raise ValueError("Tuotantotilan julkaisujuuri tulee konfiguraatiosta.")
            if self.rules_dir is not None and self.rules_dir != self.identity.rules_dir:
                raise ValueError("Tuotantotilan peruskirjan polku tulee konfiguraatiosta.")


class RestorePrefix:
    """Palauttaa etuliitteen, jonka Tailscale Serve poistaa ennen välitystä Unix-sokettiin.

    Todettu 14.10.2026 koepolulla: selaimen osoite /hub-koe/ajot/x saapui muodossa /ajot/x ja /hub-koe muodossa /.
    Reitit, linkit ja staattiset tiedostot käyttävät selaimen näkemää /hub-osoitetta, joten etuliite lisätään
    jokaisen pyynnön polkuun ennen reititystä. Asiakkaan X-Forwarded-Prefix-otsaketta ei käytetä: Serve päästää
    sen läpi sellaisenaan.
    """

    def __init__(self, app, prefix: str = SERVE_PREFIX) -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            path = scope.get("path") or "/"
            raw = scope.get("raw_path") or path.encode("utf-8")
            scope = dict(scope)
            scope["path"] = self.prefix if path == "/" else self.prefix + path
            scope["raw_path"] = self.prefix.encode("ascii") + (b"" if raw == b"/" else raw)
        await self.app(scope, receive, send)


def _header_values(headers: list, name: bytes) -> list[bytes]:
    return [value for key, value in headers if key.lower() == name]


def production_rejection(request: Request, identity: HubConfig) -> tuple[int, str] | None:
    """Gatewayn vartijan säännöt (aiops ADR-0010 ja sen tarkennukset) tiukennettuina lukupalvelulle.

    Palauttaa (tilakoodi, selitys) tai None, jos pyyntö kelpaa. Otsakkeiden toistot hylätään yksikäsitteisyyden vuoksi.
    Sokettiin pääsevät vain tailscaled ja root, joten Serven kirjoittamat X-Forwarded-Host ja Tailscale-User-Login
    ovat luotettavia. Serve korvaa asiakkaan omat arvot ja poistaa asiakkaan Tailscale-Funnel-Request-otsakkeen
    (todettu 14.10.2026).
    """
    headers = request.scope.get("headers", [])
    if request.scope.get("client") is not None:
        return 403, "Hub palvelee vain Unix-soketin kautta."
    if request.method not in ("GET", "HEAD"):
        return 405, "Hub vain lukee: vain GET ja HEAD ovat sallittuja."
    forwarded = _header_values(headers, b"x-forwarded-host")
    hosts = _header_values(headers, b"host")
    if len(forwarded) > 1 or len(hosts) > 1:
        return 421, "Osoite ei ole yksikäsitteinen."
    host = (forwarded or hosts or [b""])[0].decode("latin-1").lower()
    if host not in (identity.rp_id, f"{identity.rp_id}:443"):
        return 421, f"Väärä osoite: Hub vastaa vain nimellä {identity.rp_id}."
    if _header_values(headers, b"tailscale-funnel-request"):
        return 403, "Funnel-pyyntöjä ei palvella (ADR-0004)."
    logins = _header_values(headers, b"tailscale-user-login")
    if len(logins) != 1 or logins[0].decode("latin-1") not in identity.users:
        return 403, "Ei pääsyä: Tailscale-tunnus puuttuu tai sitä ei ole sallittu."
    sites = _header_values(headers, b"sec-fetch-site")
    if len(sites) > 1:
        return 403, "Ei pääsyä toisen sivuston kautta."
    if sites and sites[0] not in (b"none", b"same-origin"):
        # Kotinäytön sovellus ja linkit muualta (aiops istunto 2, 28.10.2026): ylätason navigointi dokumenttiin
        # kelpaa, koska Hub vain lukee (GET/HEAD) eikä sitä voi kehystää (frame-ancestors 'none'). Sama kuin
        # gatewayssa, joka tarkistaa alkuperän vain lomakkeissa. Upotukset ja haut toiselta sivustolta hylätään.
        if not (_header_values(headers, b"sec-fetch-mode") == [b"navigate"]
                and _header_values(headers, b"sec-fetch-dest") == [b"document"]):
            return 403, "Ei pääsyä toisen sivuston kautta."
    origins = _header_values(headers, b"origin")
    if len(origins) > 1 or (origins and origins[0] != identity.origin.encode("ascii")):
        return 403, "Ei pääsyä toisesta alkuperästä."
    return None


def format_time(value: Any) -> str:
    if value is None:
        return "Ei saatavilla"
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return "Ei saatavilla"
        return parsed.astimezone(HELSINKI).strftime("%d.%m.%Y klo %H.%M")
    except (ValueError, TypeError, OverflowError):
        return "Ei saatavilla"


def format_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return "Ei saatavilla"


def series_chart(card: dict[str, Any] | None, days: int = 7) -> dict[str, Any] | None:
    """Katkaise viiva puuttuvan havainnon kohdalla; älä interpoloi tietoa."""
    if not card or card["kind"] != "time_series":
        return None
    data = card["data"]
    end = date.fromisoformat(data["period_end"])
    cutoff = date.fromordinal(max(1, end.toordinal() - days + 1))
    start = max(date.fromisoformat(data["period_start"]), cutoff)
    observed = {point["date"]: point["value"] for point in data["points"]}
    samples = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    values = [observed.get(day) for day in samples]
    known = [float(value) for value in values if value is not None]
    low = (min(known) * 1.15 if min(known) < 0 else max(0, min(known) * .85)) if known else 0
    high = (max(known) * .85 if max(known) < 0 else max(known) * 1.1) if known else 1
    if high <= low:
        high = low + 1
    segments, current, points = [], [], []
    for index, (day, value) in enumerate(zip(samples, values, strict=True)):
        x = round(36 + index * 574 / max(1, len(samples) - 1), 2)
        y = round(170 - (float(value) - low) * 135 / (high - low), 2) if value is not None else None
        points.append({"x": x, "y": y, "missing": value is None, "label": format_date(day), "value": value})
        if value is None:
            if current:
                segments.append(" ".join(current))
                current = []
        else:
            current.append(f"{x},{y}")
    if current:
        segments.append(" ".join(current))
    return {"segments": segments, "points": points, "coverage": len(known), "total": len(samples), "range_label": f"{format_date(start)} – {format_date(end)}", "min": round(low), "max": round(high)}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Ilmari Hub", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    templates.env.globals.update(format_time=format_time, format_date=format_date, chart_for=series_chart)
    app.mount("/hub/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if settings.identity is not None:
            rejection = production_rejection(request, settings.identity)
            if rejection is None:
                request.state.user = settings.identity.users[request.headers["tailscale-user-login"]]
                return secure(await call_next(request))
            code, reason = rejection
            return secure(HTMLResponse(f"<!doctype html><html lang='fi'><title>Pääsy estetty</title><h1>Pääsy estetty</h1><p>{reason}</p></html>", status_code=code))
        headers = request.scope.get("headers", [])
        hosts = [value for name, value in headers if name.lower() == b"host"]
        origins = [value for name, value in headers if name.lower() == b"origin"]
        fetch_sites = [value for name, value in headers if name.lower() == b"sec-fetch-site"]
        rejected = (
            request.scope.get("client") is not None
            or hosts != [b"ilmari.local"]
            or "tailscale-funnel-request" in request.headers
            or request.headers.get("sec-fetch-site") not in (None, "none", "same-origin")
            or len(origins) > 1
            or len(fetch_sites) > 1
            or (origins and origins != [f"{request.url.scheme}://ilmari.local".encode()])
            or request.method not in ("GET", "HEAD")
        )
        if rejected:
            response = HTMLResponse("<!doctype html><html lang='fi'><title>Pääsy estetty</title><h1>Pääsy estetty</h1><p>Hub toimii vain paikallisessa Unix-soketissa ja hyväksyy lukupyynnöt omalta alkuperältä.</p></html>", status_code=403)
        else:
            response = await call_next(request)
        return secure(response)

    def secure(response):
        """Sama turvaotsakkeiden joukko jokaiseen vastaukseen, myös hylkäyksiin ja staattisiin tiedostoihin.

        Tuotannossa Hub jakaa alkuperän gatewayn kanssa, joten skriptitön CSP on osa gatewayn suojaa (ADR-0013 kohta 5).
        """
        response.headers.update({
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; manifest-src 'self'; script-src 'none'; connect-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "X-Frame-Options": "DENY",
        })
        return response

    if settings.identity is not None:
        app.add_middleware(RestorePrefix)  # viimeisenä lisätty on uloin: polku palautetaan ennen vartijaa ja reititystä

    def context(request: Request, page: str, title: str) -> dict[str, Any]:
        skin = normalize_skin(request.query_params.get("skin"))
        demo = settings.demo_enabled and request.query_params.get("demo") == "1"
        selection = request.query_params.get("home_cards", ",".join(APP_IDS))
        if any(f"slot{index}" in request.query_params for index in range(1, 5)):
            selection = ",".join(request.query_params.get(f"slot{index}", "") for index in range(1, 5))
        home_cards = list(dict.fromkeys(item for item in selection.split(",") if item in APP_IDS))
        days = int(request.query_params.get("days", "7")) if request.query_params.get("days") in ("7", "30", "90") else 7

        def url(path: str, **query: Any) -> str:
            path = ALIASES.get(path, path)
            params: dict[str, Any] = {"skin": skin}
            if demo:
                params["demo"] = "1"
            if home_cards != list(APP_IDS):
                params["home_cards"] = ",".join(home_cards)
            params.update(query)
            params = {key: value for key, value in params.items() if value is not None}
            return path + ("?" + urlencode(params) if params else "")

        configured_classes = {app["id"]: app["data_class"] for app in APP_CATALOG} | settings.app_classes
        card_states = load_cards(
            PACKAGE_DIR / "demo" / "cards" if demo else settings.cards_dir,
            app_classes=configured_classes,
            allowed_private_apps=frozenset(APP_IDS) if demo else settings.allowed_private_apps,
            allowed_source_hosts=frozenset({"example.org"}) if demo else settings.allowed_source_hosts,
            now=DEMO_NOW if demo else None,
            demo=demo,
        )
        cards, apps = [], []
        for entry in APP_CATALOG:
            state = card_states[entry["id"]]
            apps.append({**entry, "status": state.status, "status_label": state.status, "message": state.message})
            for card in state.cards:
                item = card.model_dump(mode="json")
                item.update(status=state.status, status_label=state.status)
                cards.append(item)

        reader = RunReader(PACKAGE_DIR / "demo" / "runs" if demo else settings.runs_dir or Path("/srv/aiops/ilmari/ajot"))
        listing = reader.list_runs()
        runs = [run_view(run.run_id, run.meta, run.errors, demo) for run in listing.runs]
        return {
            "request": request, "skin": skin, "skins": SKINS, "demo": demo,
            "demo_enabled": settings.demo_enabled, "current_page": page, "page_title": title, "url": url,
            "cards": cards, "apps": apps, "home_cards": home_cards,
            "home_card_items": [next((card for card in cards if card["app_id"] == app_id), None) for app_id in home_cards],
            "runs": runs, "runs_state": listing.state, "runs_errors": listing.errors,
            "runs_truncated": listing.truncated, "reader": reader, "days": days,
            "approval_items": [], "system_metrics": [], "budget": None,
            "source_state": "esimerkkidata" if demo else ("julkaisut" if settings.identity else "kehitysympäristö"),
            "mode_label": "Esimerkkitila" if demo else ("Työasema" if settings.identity else "Kehitysympäristö"),
            "gateway_connected": False,
        }

    def render(request: Request, page: str, title: str, **extra: Any):
        data = context(request, page, title)
        data.update(extra)
        return templates.TemplateResponse(request=request, name=f"{page}.html", context=data)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/hub", status_code=307)

    @app.get("/hub", response_class=HTMLResponse)
    async def home(request: Request):
        return render(request, "home", "Koti")

    @app.get("/hub/keskustelu", response_class=HTMLResponse)
    async def chat(request: Request):
        return render(request, "chat", "Keskustelu")

    @app.get("/hub/ajot", response_class=HTMLResponse)
    async def runs(request: Request):
        data = context(request, "runs", "Ajot ja raportit")
        if not data["demo"]:
            for run in data["runs"][:RUN_COUNT_LIMIT]:  # ehdotusmäärät ja tuomiot vaativat ajon tiedostot
                try:
                    detail = data["reader"].read_run(run["run_id"])
                except ReadFailure:
                    continue
                run.update(proposal_count=len(detail.proposals), verdicts=muodot.verdict_counts(detail.sol_result))
        return templates.TemplateResponse(request=request, name="runs.html", context=data)

    @app.get("/hub/ajot/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str):
        data = context(request, "run_detail", "Ajon raportti")
        try:
            detail = data["reader"].read_run(run_id)
        except ReadFailure:
            return templates.TemplateResponse(request=request, name="error.html", context={**data, "message": "Ajoa ei löydy tai julkaisua ei voi lukea turvallisesti.", "error_title": "Ajo ei ole saatavilla", "status_code": 404}, status_code=404)
        run = run_view(detail.run_id, detail.meta, detail.errors, data["demo"])
        if not data["demo"]:
            run.update(proposal_count=len(detail.proposals), verdicts=muodot.verdict_counts(detail.sol_result))
        data.update(run=run, meta=detail.meta or {}, report=detail.report, suggestions=detail.proposals,
                    proposals=muodot.proposals(detail.proposals, detail.sol_result), sol_summary=muodot.sol_summary(detail.sol_result),
                    verdict_labels=muodot.VERDICT_LABELS,
                    sol=json.dumps(detail.sol_result, ensure_ascii=False, indent=2) if detail.sol_result is not None else None,
                    patch=detail.patch, run_errors=detail.errors if data["demo"] else muodot.relevant_errors(detail.errors))
        return templates.TemplateResponse(request=request, name="run_detail.html", context=data)

    @app.get("/hub/hyvaksynnat", response_class=HTMLResponse)
    async def approvals(request: Request):
        return render(request, "approvals", "Hyväksynnät")

    @app.get("/hub/sovellukset", response_class=HTMLResponse)
    async def apps(request: Request):
        return render(request, "apps", "Sovellukset")

    @app.get("/hub/sovellukset/{app_id}", response_class=HTMLResponse)
    async def app_detail(request: Request, app_id: str):
        if app_id not in APP_IDS:
            return render_error(request, 404, "Sovellusta ei löydy", "Tätä sovellusta ei ole Hubin katalogissa.")
        data = context(request, "app_detail", next(app["name"] for app in APP_CATALOG if app["id"] == app_id))
        cards = [card for card in data["cards"] if card["app_id"] == app_id]
        card = cards[0] if cards else None
        data.update(app=next(app for app in data["apps"] if app["id"] == app_id), cards=cards, card=card, chart=series_chart(card, data["days"]))
        return templates.TemplateResponse(request=request, name="app_detail.html", context=data)

    @app.get("/hub/ideat", response_class=HTMLResponse)
    async def ideas(request: Request):
        return render(request, "ideas", "Ideat ja projektit")

    @app.get("/hub/jarjestelma", response_class=HTMLResponse)
    async def system(request: Request):
        return render(request, "system", "Järjestelmä")

    @app.get("/hub/saannot", response_class=HTMLResponse)
    async def rules(request: Request):
        """Peruskirja vain luku -tilassa (aiops ADR-0017). Tuotannossa vain rootin julkaisema kelpaa (ADR-0013)."""
        data = context(request, "rules", "Säännöt")
        if data["demo"]:
            kirja = lue_peruskirja(PACKAGE_DIR / "demo" / "peruskirja", omistaja=None)
        elif settings.identity is not None:
            kirja = lue_peruskirja(settings.identity.rules_dir, omistaja=0)
        elif settings.rules_dir is not None:
            kirja = lue_peruskirja(settings.rules_dir, omistaja=None)
        else:
            kirja = None
        data.update(kirja=kirja)
        return templates.TemplateResponse(request=request, name="rules.html", context=data)

    def dokumenttikokoelma(request: Request):
        """Asennetun commitin dokumentit (aiops istunto 2). Tuotannossa vain rootin julkaisema kelpaa (ADR-0013)."""
        if settings.demo_enabled and request.query_params.get("demo") == "1":
            return lue_dokumentit(DOKUMENTIT_ESIMERKKI, omistaja=None)
        if settings.identity is not None:
            return lue_dokumentit(DOKUMENTIT_OLETUS, omistaja=0)
        return None

    @app.get("/hub/dokumentit", response_class=HTMLResponse)
    async def documents(request: Request):
        kokoelma = dokumenttikokoelma(request)
        valmis = kokoelma is not None and kokoelma.tila == "ready"
        kysely = (request.query_params.get("q") or "").strip()[:100]
        return render(request, "documents", "Dokumentit", kokoelma=kokoelma, kysely=kysely,
                      ryhmat=ryhmittain(kokoelma) if valmis else [],
                      osumat=hae_dokumentit(kokoelma, kysely) if valmis and kysely else [])

    @app.get("/hub/dokumentit/{tunniste}", response_class=HTMLResponse)
    async def document_detail(request: Request, tunniste: str):
        kokoelma = dokumenttikokoelma(request)
        dokumentti = etsi_dokumentti(kokoelma, tunniste) if kokoelma is not None and kokoelma.tila == "ready" else None
        if dokumentti is None:
            return render_error(request, 404, "Dokumenttia ei löydy",
                                "Dokumenttia ei ole asennetussa versiossa. Palaa dokumenttilistaan.")
        lohkot, virhe = piirrettava(dokumentti)
        if lohkot is None:
            return render_error(request, 422, "Dokumenttia ei voi näyttää", virhe or "Dokumentti on liian suuri.")
        return render(request, "document", dokumentti["otsikko"], kokoelma=kokoelma, dokumentti=dokumentti,
                      lohkot=lohkot)

    @app.get("/hub/asetukset", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return render(request, "settings", "Asetukset ja ulkoasu")

    def render_error(request: Request, code: int, title: str, message: str):
        data = context(request, "error", title)
        return templates.TemplateResponse(request=request, name="error.html", context={**data, "message": message, "error_title": title, "status_code": code}, status_code=code)

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return render_error(request, 404, "Sivua ei löydy", "Tarkista osoite tai palaa etusivulle.")

    return app


def run_view(run_id: str, meta: dict | None, errors: tuple, demo: bool) -> dict:
    """Ajon yhteenveto. Oikeat julkaisut tulkitaan MUODOT.md:n mukaan (muodot.py); esimerkkidata omilla demo-kentillään."""
    result = {"run_id": run_id, "title": run_id, "status": "partial" if errors else "published", "status_label": "Osittainen julkaisu" if errors else "Julkaistu", "started_at": None, "ended_at": None, "model": None, "proposal_count": None, "verdicts": None, "facts": None}
    if demo and meta:
        result.update(title=meta.get("demo_title", run_id), status="demo", status_label="Esimerkkijulkaisu", started_at=meta.get("demo_started_at"), ended_at=meta.get("demo_ended_at"), model=meta.get("demo_model"), proposal_count=meta.get("demo_proposal_count"), verdicts=meta.get("demo_verdicts"))
    elif not demo:
        facts = muodot.run_facts(run_id, meta)
        partial = bool(muodot.relevant_errors(errors))
        result.update(title=facts["title"], started_at=facts["started_at"], ended_at=facts["ended_at"], model=facts["model"], facts=facts,
                      status="partial" if partial else "published", status_label="Osittainen julkaisu" if partial else "Julkaistu")
    return result
