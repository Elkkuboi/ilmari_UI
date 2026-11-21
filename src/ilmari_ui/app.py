"""Ilmari Hub: Eliaksen ohjauspaikka ja Ilmarin tila yhdellä sivustolla, palvelinrenderöitynä ja vain lukevana.

Neljä sivua: Nyt (/hub, juuri), Keskustelu, Työt ja Asetukset, sekä Dokumentit Asetusten alla. Hub lukee gatewayn ja
asennuksen julkaisemat tiedostot; jokainen muutos on lomake, joka lähetetään gatewaylle samassa alkuperässä
(paluu=hub), eikä Hubissa ole yhtään POST-reittiä.

Palvelin toimii vain Unix-soketissa. Kehitystilassa (ei identiteettiasetusta) se hyväksyy vain Host-nimen
ilmari.local eikä todista Tailscale-identiteettiä. Tuotantotilassa (aiops ADR-0013) Tailscale Serve ohjaa polun /hub
Hubin sokettiin, ja Hub toistaa gatewayn vartijan säännöt: vain GET ja HEAD, osoite X-Forwarded-Hostista, ei
Funnel-pyyntöjä ja vain sallitut Tailscale-tunnukset. Serve poistaa etuliitteen /hub ennen välitystä, joten
tuotantotilassa se palautetaan ennen reititystä.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import dokumentit as dokumentit_lukija
from . import jarjestelma as jarjestelma_lukija
from . import kehitys
from . import kehotteet as kehotteet_lukija
from . import keskustelu as keskustelu_lukija
from . import mallit as mallit_lukija
from . import toiminta as toiminta_lukija
from .config import HubConfig

PACKAGE_DIR = Path(__file__).parent
HELSINKI = ZoneInfo("Europe/Helsinki")
TOIMINTA_DEMO_NYT = datetime(2026, 11, 19, 14, 10, tzinfo=timezone.utc)  # esimerkin työvuoro käynnissä (16.10 Helsingissä)
JARJESTELMA_DEMO_NYT = datetime(2026, 10, 30, 12, 0, 20, tzinfo=timezone.utc)
SERVE_PREFIX = "/hub"
# Muut sovellukset työasemalla omissa Serve-porteissaan samalla nimellä kuin Hub (aiops ADR-0026: Hahmo). Hub ei kutsu
# niitä (PrivateNetwork), vaan linkittää niihin.
RAVINTOPOLKU_PORTTI = 8443
HAHMO_PORTTI = 8444
VALIKKO = (("nyt", "/hub", "Nyt"), ("keskustelu", "/hub/keskustelu", "Keskustelu"), ("tyot", "/hub/kehita", "Työt"),
           ("asetukset", "/hub/asetukset", "Asetukset"))
TEKOJA_NAKYVISSA = 12
ODOTTAA_MAX = 5
NYT_PAIVITYS = "30"
TYOT_PAIVITYS = "15"
KESKUSTELU_PAIVITYS = "5"
# Sivu, jolla on muokattava kenttä, ei päivity itsestään: selain tyhjentää kesken kirjoitetun tekstin (19.11.2026).
# Itsestään päivittyy vain odotus- tai seurantatila ilman kenttää; kentän saa näkyviin parametrilla kirjoita=1.
MUOKATTAVA = re.compile(rb'<textarea\b|<select\b|<input\b(?![^>]*\btype="hidden")', re.IGNORECASE)
# Eliaksen viestiä tuoreempi: Ilmari vastaa vielä. 10 min = aiops ceo.py:n VASTAUS_AIKARAJA_S; mallin lataus (GPU
# varattu) voi yksin kestää 5 min. Ilmari lähettää vastauksen myös virheestä, joten odotus päättyy yleensä siihen.
VASTAUS_ODOTUS = timedelta(minutes=10)
KELLON_VARA = timedelta(minutes=1)      # tulevaisuuteen merkitty viesti ei jätä sivua odottamaan
# Vanhat osoitteet (ennen 18.11.2026) ohjataan uusiin; kyselyosa säilyy ja ankkuri tulee sen perään. Vanha gateway
# palaa lomakkeiden jälkeen vielä osoitteisiin /hub/ilmari (myös ?toihin=rajatesti) ja /hub/mallit (aivot).
VANHAT_OSOITTEET = {
    "/hub/ilmari": "/hub", "/hub/mallit": "/hub/asetukset#aivot", "/hub/jarjestelma": "/hub/asetukset#kone",
    "/hub/saannot": "/hub/dokumentit", "/hub/ajot": "/hub", "/hub/ajot/{x}": "/hub", "/hub/hyvaksynnat": "/hub",
    "/hub/sovellukset": "/hub", "/hub/sovellukset/{x}": "/hub", "/hub/ideat": "/hub",
}


@dataclass(frozen=True)
class Vari:
    """Väriyhdistelmä: tunniste (evästeen arvo ja <html data-vari>), näkyvä nimi, kuvaus, sivun taustaväri
    (selaimen theme-color) ja onko yhdistelmä tumma (color-scheme). Värit itse ovat app.css:n lohkoissa."""

    tunniste: str
    nimi: str
    kuvaus: str
    tausta: str
    tumma: bool


VARIT = (Vari("paperi", "Paperi", "vaalea, lämmin", "#f1ead9", False),
         Vari("liitu", "Liitu", "vaalea, viileä", "#ecece6", False),
         Vari("terminaali", "Terminaali", "tumma, meripihka", "#17140f", True),
         Vari("fosfori", "Fosfori", "tumma, vihreä", "#0e1411", True))
VARIT_TUNNISTEELLA = {v.tunniste: v for v in VARIT}
OLETUSVARI = VARIT_TUNNISTEELLA["paperi"]
# Sama eväste ohjaa myös gatewayn sivuja (sama alkuperä, Path=/). Gateway vain lukee sen; vain Hub asettaa sen.
VARI_EVASTE = "ilmari_vari"
VARI_IKA_S = 365 * 24 * 3600


def vari(arvo: Any) -> Vari:
    """Rekisterin väriyhdistelmä tunnisteelle; kaikelle muulle (puuttuva, tuntematon, muu tyyppi) oletus."""
    return VARIT_TUNNISTEELLA.get(arvo, OLETUSVARI) if isinstance(arvo, str) else OLETUSVARI


@dataclass(frozen=True)
class Settings:
    """Tietolähteet ovat kiinteitä polkuja (moduulien OLETUS); selain ei valitse niitä."""

    demo_enabled: bool = False
    identity: HubConfig | None = None  # tuotantotila: Tailscale-tunnistus ja Serven etuliite (ADR-0013)

    def __post_init__(self) -> None:
        if self.identity is not None and self.demo_enabled:
            raise ValueError("Esimerkkitila ei ole sallittu tuotantotilassa.")


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


def _aika(value: Any) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed.astimezone(HELSINKI) if parsed.tzinfo is not None else None


def format_time(value: Any) -> str:
    """Aikavyöhykkeellinen aika Helsingin aikana (14.10.2026 klo 01.05); ilman vyöhykettä ei arvata."""
    parsed = _aika(value)
    return parsed.strftime("%d.%m.%Y klo %H.%M") if parsed else "Ei saatavilla"


def paiva(value: Any) -> str:
    """Päivä ja kuukausi (18.11.) tai tyhjä."""
    parsed = _aika(value)
    return f"{parsed.day}.{parsed.month}." if parsed else ""


def kello(value: Any) -> str:
    """Kellonaika (04.55) tai tyhjä."""
    parsed = _aika(value)
    return parsed.strftime("%H.%M") if parsed else ""


def lyhyt_aika(value: Any) -> str:
    """Tänään kellonaika (klo 22.29), muuten päivä ja kellonaika (18.11. klo 22.29). Sitovat välilyönnit: aika ei
    katkea kahdelle riville, eikä pelkkää kellonaikaa lueta päivämääräksi (20.05 ≠ 20.5.)."""
    parsed = _aika(value)
    if parsed is None:
        return ""
    kellonaika = f"klo {parsed.strftime('%H.%M')}"
    if parsed.date() == datetime.now(HELSINKI).date():
        return kellonaika
    return f"{parsed.day}.{parsed.month}. {kellonaika}"


def koneen_ika(kone: Any) -> str:
    """Koneen mittareiden ikä ymmärrettävästi: tuore sekunteina, vanhentunut minuutteina, tunteina tai päivänä."""
    ika = kone.ika_s
    if ika is None:
        return "päivitysaika ei tiedossa"
    if not kone.vanhentunut:
        return f"päivitetty {ika} s sitten"
    if ika < 3600:
        return f"päivitetty {ika // 60} min sitten"
    if ika < 86400:
        return f"päivitetty {ika // 3600} h sitten"
    return f"päivitetty {paiva(kone.paivitetty)} klo {kello(kone.paivitetty)}"


def kohtaa(n: int) -> str:
    return f"{n} {'kohta' if n == 1 else 'kohtaa'}"


def paivity(response, sekunnit: str):
    """Automaattinen päivitys (Refresh), mutta ei koskaan sivulle, jolla on muokattava kenttä."""
    if not MUOKATTAVA.search(response.body):
        response.headers["Refresh"] = sekunnit
    return response


def kirjoitus(request: Request) -> bool:
    """Kenttä näkyviin ja päivitys pois: vain vakioarvo kirjoita=1 kelpaa, eikä arvoa näytetä sivulla."""
    return request.query_params.get("kirjoita") == "1"


def listanakyma(request: Request) -> bool:
    """Keskustelujen lista (lista=1): vain vakioarvo kelpaa, eikä arvoa näytetä sivulla."""
    return request.query_params.get("lista") == "1"


def odottaa_vastausta(k: Any, nyt: datetime) -> bool:
    """Aktiivisen säikeen viimeisin viesti on Eliaksen ja alle 10 minuuttia vanha: Ilmari ei ole vielä vastannut."""
    if k is None or k.tila != "ready" or not k.viestit or k.viestit[-1]["lahettaja"] != "elias":
        return False
    aika = _aika(k.viestit[-1]["aika"])
    return aika is not None and -KELLON_VARA <= nyt - aika < VASTAUS_ODOTUS


def osoitteet(demo: bool):
    """Hubin sisäinen osoite; esimerkkitila kulkee mukana kyselyssä (ei evästeitä)."""
    def url(path: str, **query: Any) -> str:
        params = {"demo": "1"} if demo else {}
        params.update({key: value for key, value in query.items() if value is not None})
        return path + ("?" + urlencode(params) if params else "")
    return url


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Ilmari Hub", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    templates.env.globals.update(format_time=format_time, paiva=paiva, kello=kello, lyhyt_aika=lyhyt_aika,
                                 koneen_ika=koneen_ika, kohtaa=kohtaa, muutosrivi=kehitys.muutosrivi,
                                 testirivi=kehitys.testirivi, ilman_aikaleimoja=kehitys.ilman_aikaleimoja)
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
            # Ei "no-referrer": silloin selain lähettää Hubin lomakkeet (roolin ja aivoprofiilin vaihto gatewayhin)
            # otsakkeella Origin: null, ja gateway hylkää ne (29.10.). same-origin: Origin lähetetään, Referer ei
            # vuoda muualle. Sama valinta kuin gatewayn omilla sivuilla.
            "Referrer-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "X-Frame-Options": "DENY",
        })
        return response

    if settings.identity is not None:
        app.add_middleware(RestorePrefix)  # viimeisenä lisätty on uloin: polku palautetaan ennen vartijaa ja reititystä

    # --- Yhteiset osat ------------------------------------------------------------------------------------------

    def esimerkki(request: Request) -> bool:
        return settings.demo_enabled and request.query_params.get("demo") == "1"

    def gateway(polku: str, demo: bool) -> str:
        """Gatewayn sivu samassa alkuperässä (Tailscale Serve: gateway juuressa, Hub polussa /hub); muuten #."""
        return settings.identity.origin + polku if settings.identity is not None and not demo else "#"

    def render(request: Request, sivu: str, otsikko: str, aktiivinen: str | None, status_code: int = 200,
               **extra: Any):
        demo = esimerkki(request)
        ulkoasu = vari(request.cookies.get(VARI_EVASTE))
        context = {
            "request": request, "demo": demo, "otsikko": otsikko, "aktiivinen": aktiivinen, "valikko": VALIKKO,
            "vari": ulkoasu.tunniste, "ulkoasu": ulkoasu, "varit": VARIT,
            "url": osoitteet(demo), "gateway": lambda polku: gateway(polku, demo),
            "gateway_url": settings.identity.origin if settings.identity is not None else None,
            "ymparisto": "esimerkkitila" if demo else ("työasema" if settings.identity else "kehitysympäristö"),
            "haettu": datetime.now(HELSINKI).strftime("%H.%M"),
        }
        context.update(extra)
        return templates.TemplateResponse(request=request, name=f"{sivu}.html", context=context,
                                          status_code=status_code)

    def lue_toiminta(demo: bool) -> tuple[toiminta_lukija.Toiminta | None, datetime]:
        if demo:
            return toiminta_lukija.lue_toiminta(toiminta_lukija.ESIMERKKI), TOIMINTA_DEMO_NYT
        if settings.identity is not None:
            return (toiminta_lukija.lue_toiminta(toiminta_lukija.OLETUS, omistajat=kehitys.sallitut_omistajat()),
                    datetime.now(timezone.utc))
        return None, datetime.now(timezone.utc)

    def lue_keskustelu(demo: bool) -> keskustelu_lukija.Keskustelu | None:
        if demo:
            return keskustelu_lukija.lue_keskustelu(keskustelu_lukija.ESIMERKKI)
        if settings.identity is not None:
            return keskustelu_lukija.lue_keskustelu(keskustelu_lukija.OLETUS, omistajat=kehitys.sallitut_omistajat())
        return None

    def mallin_tila(k: keskustelu_lukija.Keskustelu | None) -> dict[str, Any] | None:
        """Ilmarin mallin tila keskustelun julkaisusta (tila, käynnissä oleva työ, yöajo) tai None."""
        return k.malli if k is not None and k.tila == "ready" else None

    def kehitystyot(demo: bool) -> tuple[tuple[kehitys.Kehitystyo, ...] | None, bool]:
        """(työt uusin ensin tai None, onko lähde määritetty)."""
        if demo:
            return kehitys.lue_kehitystyot(kehitys.ESIMERKKI), True
        if settings.identity is not None:
            return kehitys.lue_kehitystyot(kehitys.OLETUS, omistajat=kehitys.sallitut_omistajat()), True
        return None, False

    def kesken(tyot: tuple[kehitys.Kehitystyo, ...] | None) -> bool:
        """Onko jokin uusimmista töistä (Eliaksen tai Ilmarin) vielä kesken: sivu päivittyy itsestään."""
        if not tyot:
            return False
        eliaksen = [t for t in tyot if not t.ilmarin][:5]
        ilmarin = [t for t in tyot if t.ilmarin][:5]
        return any(t.meta.get("tila") not in kehitys.LOPULLISET for t in eliaksen + ilmarin)

    # --- Nyt: Hubin juuri ---------------------------------------------------------------------------------------

    def odottaa_sinua(toiminta, tyot, lahde, url) -> list[dict[str, Any]]:
        """Asiat, joissa Eliaksella on päätettävää: työn hyväksyntä, käyttöönotto tai käsin sulkeminen, epäonnistunut
        rajatesti ja lukuvirheet (tila tai työt). Enintään ODOTTAA_MAX riviä, tärkein ensin."""
        rivit: list[dict[str, Any]] = []
        if toiminta is not None and toiminta.tila != "ready":
            rivit.append({"href": url("/hub"), "nro": "!", "teksti": "Ilmarin tilaa ei voi lukea", "tag": "päivitä",
                          "savy": "stop", "ala": toiminta.viesti or ""})
        elif toiminta is not None:
            r = (toiminta.tilanne or {}).get("rajatesti")
            if r is not None and not r["lapi"]:
                rivit.append({"href": url("/hub/asetukset") + "#rajatesti", "nro": "!", "teksti": "Rajatesti ei mennyt läpi",
                              "tag": "ei läpi", "savy": "stop",
                              "ala": f"{kohtaa(len(r['hylatyt']))} ei läpi · {lyhyt_aika(r['aika'])}"})
            for virhe in toiminta.virheet:
                rivit.append({"href": url("/hub"), "nro": "!", "teksti": "Osaa tilasta ei voi lukea", "tag": "päivitä",
                              "savy": "warn", "ala": virhe})
        if lahde and tyot is None:
            rivit.append({"href": url("/hub/kehita"), "nro": "!", "teksti": "Töitä ei voi lukea", "tag": "päivitä",
                          "savy": "warn", "ala": ""})
        for t in tyot or ():
            tag, savy = t.tagi
            if tag not in kehitys.ODOTTAVAT:
                continue
            testit = (t.meta.get("tulos") or {}).get("testit")
            osat = ["Ilmarin työ" if t.ilmarin else "Sinun toiveesi", t.meta.get("lahde") or "aiops"]
            if testit:
                osat.append("testit läpi" if testit.get("paluukoodi") == 0 else "testit epäonnistuivat")
            if lyhyt_aika(t.meta.get("paivitetty") or t.meta.get("luotu")):
                osat.append(lyhyt_aika(t.meta.get("paivitetty") or t.meta.get("luotu")))
            rivit.append({"href": url(f"/hub/kehita/{t.tyo}"), "nro": t.tyo,
                          "teksti": t.meta.get("toive", "").split("\n")[0][:120] or "Toive puuttuu",
                          "tag": tag, "savy": savy, "ala": " · ".join(osat)})
        return rivit[:ODOTTAA_MAX]

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/hub", status_code=307)

    @app.get("/hub", response_class=HTMLResponse)
    async def nyt_sivu(request: Request):
        """Ilmarin tila ja ohjaus (Töihin nyt, Seis, Jatka), mitä odottaa Eliasta, viimeisin raportti ja teot.
        Lomakkeet menevät gatewaylle (paluu=hub); gateway palaa tänne ?toihin=rajatesti, kun Töihin nyt ajaa ensin
        rajatestin. Päivittyy itsestään vain, kun vuoro tai työ on käynnissä."""
        demo = esimerkki(request)
        toiminta, nyt = lue_toiminta(demo)
        malli = mallin_tila(lue_keskustelu(demo))
        tyot, lahde = kehitystyot(demo)
        tilarivi = toiminta_lukija.tilarivi(toiminta, nyt)
        valmis = toiminta is not None and toiminta.tila == "ready"
        teot = (toiminta.teot or ()) if valmis else ()
        dsh_tyo = (malli or {}).get("dsh_tyo")
        response = render(
            request, "nyt", "Nyt", "nyt", toiminta=toiminta, tilarivi=tilarivi, malli=malli,
            asetukset=toiminta.asetukset if valmis else None,
            raportti=toiminta.raportti if valmis else None,
            rajatesti_kaynnissa=toiminta_lukija.rajatesti_kaynnissa(toiminta, dsh_tyo),
            toihin_rajatesti=request.query_params.get("toihin") == "rajatesti",
            odottaa=odottaa_sinua(toiminta, tyot, lahde, osoitteet(demo)),
            teot=teot[:TEKOJA_NAKYVISSA], vanhat_teot=teot[TEKOJA_NAKYVISSA:],
            muualle=(("Ravintopolku", muualle(RAVINTOPOLKU_PORTTI, demo)), ("Hahmo", muualle(HAHMO_PORTTI, demo)))
            if demo or settings.identity is not None else ())
        if (tilarivi or {}).get("kaynnissa") or dsh_tyo or kesken(tyot):
            paivity(response, NYT_PAIVITYS)
        return response

    def muualle(portti: int, demo: bool) -> str:
        """Toinen sovellus työasemalla omassa Serve-portissaan; esimerkkitilassa ei linkkiä."""
        return f"https://{settings.identity.rp_id}:{portti}/" if settings.identity is not None and not demo else "#"

    # --- Keskustelu ---------------------------------------------------------------------------------------------

    @app.get("/hub/keskustelu", response_class=HTMLResponse)
    async def keskustelu_sivu(request: Request):
        """Gatewayn julkaisema keskustelu; lomakkeet menevät gatewaylle samassa alkuperässä (paluu=hub). Kun Ilmari
        vastaa vielä, sivu odottaa ilman viestikenttää ja päivittyy itsestään; muuten kenttä näkyy eikä sivu päivity.

        Keskustelu täyttää ruudun, ja vain viestilaatikko vierii (21.11.2026). Uusi keskustelu ja linkki listaan
        näkyvät aina, myös odottaessa. Lista (lista=1) näyttää keskustelut kansioittain sekä nykyisen keskustelun
        nimen, kansion ja arkistoinnin; se ei päivity koskaan, joten päivitys ei sulje avattua kansiota."""
        k = lue_keskustelu(esimerkki(request))
        if listanakyma(request):
            return render(request, "keskustelut", "Keskustelut", "keskustelu", keskustelu=k)
        odottaa = odottaa_vastausta(k, datetime.now(timezone.utc)) and not kirjoitus(request)
        response = render(request, "keskustelu", "Keskustelu", "keskustelu", keskustelu=k, odottaa=odottaa,
                          runko="chat-sivu")
        if odottaa:
            paivity(response, KESKUSTELU_PAIVITYS)
        return response

    # --- Työt (Kehitä): Hub näyttää, gateway toimii -------------------------------------------------------------

    @app.get("/hub/kehita", response_class=HTMLResponse)
    async def tyot_sivu(request: Request):
        """Uusi toive gatewaylle (paluu=hub), Eliaksen toiveet ja Ilmarin omat työt omina listoinaan ja
        käyttöönottojen historia. Kun jokin uusimmista töistä on kesken, sivu seuraa sitä ilman toivekenttää ja
        päivittyy itsestään; kenttä tulee näkyviin linkistä (kirjoita=1) tai esitäytetyn toiveen kanssa."""
        demo = esimerkki(request)
        tyot, lahde = kehitystyot(demo)
        if demo:
            historia = kehitys.lue_kayttoonotot(kehitys.ESIMERKKI_KAYTTOONOTOT, omistaja=None)
        elif settings.identity is not None:
            historia = kehitys.lue_kayttoonotot(kehitys.OLETUS_KAYTTOONOTOT, omistaja=0)
        else:
            historia = None
        toive = request.query_params.get("toive", "")[:4000]
        seuranta = kesken(tyot) and not kirjoitus(request) and not toive
        response = render(
            request, "tyot", "Työt", "tyot", lahde=lahde, tyot_luettu=tyot is not None,
            eliaksen=[t for t in tyot if not t.ilmarin] if tyot else [],
            ilmarin=[t for t in tyot if t.ilmarin] if tyot else [],
            historia=historia, malli=mallin_tila(lue_keskustelu(demo)), lahteet=kehitys.LAHTEET,
            toive=toive, seuranta=seuranta)
        if seuranta:
            paivity(response, TYOT_PAIVITYS)
        return response

    @app.get("/hub/kehita/{tyo}", response_class=HTMLResponse)
    async def tyo_sivu(request: Request, tyo: str):
        demo = esimerkki(request)
        if demo:
            juuri, omistajat = kehitys.ESIMERKKI, None
        elif settings.identity is not None:
            juuri, omistajat = kehitys.OLETUS, kehitys.sallitut_omistajat()
        else:
            juuri, omistajat = None, None
        t = (kehitys.lue_kehitystyo(juuri, int(tyo), omistajat=omistajat)
             if juuri is not None and kehitys._TYO.fullmatch(tyo) else None)
        if t is None:
            return virhe(request, 404, "Työtä ei löydy", "Työtä ei ole tai sitä ei voi lukea.")
        # Sulkuviesti ja muutospyyntö ovat tekstikenttiä: niiden kanssa sivu ei päivity itsestään.
        paivittyy = t.kesken and not (t.toimet["sulje"] or t.toimet["muutos"])
        response = render(request, "tyo", f"Työ {t.tyo}", "tyot", t=t, meta=t.meta, tulos=t.meta.get("tulos"),
                          toimet=t.toimet, paivittyy=paivittyy,
                          diffit=kehitys.jaa_diff(t.tekstit["muutos.diff"]) if "muutos.diff" in t.tekstit else [])
        if paivittyy:
            paivity(response, TYOT_PAIVITYS)
        return response

    # --- Asetukset ----------------------------------------------------------------------------------------------

    @app.get("/hub/asetukset", response_class=HTMLResponse)
    async def asetukset_sivu(request: Request):
        """Yöajo, tavoitteet, pysyvät ohjeet, aivot (profiili, roolit, rekisteri), rajatesti, kone ja muut linkit
        (promptit ja säännöt, dokumentit).
        Ei automaattista päivitystä: se tyhjentäisi kesken kirjoitetut lomakkeet."""
        demo = esimerkki(request)
        toiminta, _ = lue_toiminta(demo)
        valmis = toiminta is not None and toiminta.tila == "ready"
        malli = mallin_tila(lue_keskustelu(demo))
        if demo:
            rekisteri, ylikirjoitus = mallit_lukija.lue_mallit(mallit_lukija.ESIMERKKI, omistaja=None), {"kuva_tulkki": ""}
            kone = jarjestelma_lukija.lue_jarjestelma(jarjestelma_lukija.ESIMERKKI, now=JARJESTELMA_DEMO_NYT)
        elif settings.identity is not None:
            rekisteri = mallit_lukija.lue_mallit(mallit_lukija.OLETUS, omistaja=0)
            ylikirjoitus = mallit_lukija.lue_ylikirjoitus(mallit_lukija.OLETUS_ROOLIT, omistajat=kehitys.sallitut_omistajat())
            kone = jarjestelma_lukija.lue_jarjestelma(jarjestelma_lukija.OLETUS,
                                                      omistajat=jarjestelma_lukija.sallitut_omistajat())
        else:
            rekisteri, ylikirjoitus, kone = None, None, None
        mallit_valmis = rekisteri is not None and rekisteri.tila == "ready"
        return render(
            request, "asetukset", "Asetukset", "asetukset", toiminta=toiminta, valmis=valmis,
            asetukset=toiminta.asetukset if valmis else None, tilanne=toiminta.tilanne if valmis else None,
            tavoitteet=toiminta.tavoitteet if valmis else None, ohjeet=toiminta.ohjeet if valmis else None,
            malli=malli, mallit=rekisteri, ylikirjoitus=ylikirjoitus,
            nykyinen=rekisteri.nykyinen_profiili(ylikirjoitus) if mallit_valmis else None,
            vapaa_ram_gb=mallit_lukija.vapaa_ram_gb() if mallit_valmis else None,
            ram_marginaali=mallit_lukija.RAM_MARGINAALI_GB,
            kone=kone if kone is not None and kone.tila == "ready" else None)

    @app.get("/hub/ulkoasu/{tunniste}", include_in_schema=False)
    async def ulkoasu_valinta(request: Request, tunniste: str):
        """Väriyhdistelmän valinta Asetusten näytteestä: linkki (ei lomaketta, ei skriptiä) asettaa evästeen ja palaa
        Asetuksiin. Palvelimella ei muutu mitään. Evästeen arvo tulee rekisteristä, ei pyynnöstä."""
        valittu = VARIT_TUNNISTEELLA.get(tunniste)
        if valittu is None:
            return virhe(request, 404, "Sivua ei löydy", "Tarkista osoite.")
        response = RedirectResponse(osoitteet(esimerkki(request))("/hub/asetukset") + "#ulkoasu", status_code=303)
        response.set_cookie(VARI_EVASTE, valittu.tunniste, max_age=VARI_IKA_S, path="/", samesite="Lax", httponly=True,
                            secure=settings.identity is not None)
        return response

    # --- Dokumentit (Asetusten alla) ----------------------------------------------------------------------------

    def dokumenttikokoelma(request: Request):
        """Asennetun commitin dokumentit (aiops istunto 2). Tuotannossa vain rootin julkaisema kelpaa (ADR-0013)."""
        if esimerkki(request):
            return dokumentit_lukija.lue_dokumentit(dokumentit_lukija.ESIMERKKI, omistaja=None)
        if settings.identity is not None:
            return dokumentit_lukija.lue_dokumentit(dokumentit_lukija.OLETUS, omistaja=0)
        return None

    @app.get("/hub/dokumentit", response_class=HTMLResponse)
    async def dokumentit_sivu(request: Request):
        kokoelma = dokumenttikokoelma(request)
        valmis = kokoelma is not None and kokoelma.tila == "ready"
        kysely = (request.query_params.get("q") or "").strip()[:100]
        return render(request, "dokumentit", "Dokumentit", "asetukset", kokoelma=kokoelma, kysely=kysely,
                      ryhmat=dokumentit_lukija.ryhmittain(kokoelma) if valmis else [],
                      osumat=dokumentit_lukija.hae(kokoelma, kysely) if valmis and kysely else [])

    @app.get("/hub/dokumentit/{tunniste}", response_class=HTMLResponse)
    async def dokumentti_sivu(request: Request, tunniste: str):
        kokoelma = dokumenttikokoelma(request)
        dokumentti = (dokumentit_lukija.etsi(kokoelma, tunniste)
                      if kokoelma is not None and kokoelma.tila == "ready" else None)
        if dokumentti is None:
            return virhe(request, 404, "Dokumenttia ei löydy", "Dokumenttia ei ole asennetussa versiossa.")
        lohkot, syy = dokumentit_lukija.piirrettava(dokumentti)
        if lohkot is None:
            return virhe(request, 422, "Dokumenttia ei voi näyttää", syy or "Dokumentti on liian suuri.")
        if lohkot and lohkot[0]["tyyppi"] == "otsikko" and lohkot[0]["taso"] == 1 and \
                "".join(teksti for _, teksti in lohkot[0]["osat"]).strip().lower() == dokumentti["otsikko"].strip().lower():
            lohkot = lohkot[1:]   # sama otsikko on jo sivun otsikkona
        return render(request, "dokumentti", dokumentti["otsikko"], "asetukset", kokoelma=kokoelma,
                      dokumentti=dokumentti, lohkot=lohkot)

    # --- Promptit ja säännöt (Asetusten alla) -------------------------------------------------------------------

    def lue_kehotteet(request: Request):
        """Gatewayn julkaisema luettelo kaikista mallille menevistä teksteistä (aiops 21.11.2026)."""
        if esimerkki(request):
            return kehotteet_lukija.lue_kehotteet(toiminta_lukija.ESIMERKKI)
        if settings.identity is not None:
            return kehotteet_lukija.lue_kehotteet(toiminta_lukija.OLETUS, omistajat=kehitys.sallitut_omistajat())
        return None

    @app.get("/hub/kehotteet", response_class=HTMLResponse)
    async def kehotteet_sivu(request: Request):
        """Promptit ryhmittäin, lukko (saako Ilmari muokata käsikirjaansa), Eliaksen omat ohjeet (linkit Asetuksiin) ja
        säännöt (asennetut dokumentit)."""
        luettelo = lue_kehotteet(request)
        valmis = luettelo is not None and luettelo.tila == "ready"
        toiminta, _ = lue_toiminta(esimerkki(request))
        omat = None
        if valmis and toiminta is not None and toiminta.tila == "ready":
            omat = {"ohjeita": len(toiminta.ohjeet) if toiminta.ohjeet is not None else None,
                    "tavoitteita": len(toiminta.tavoitteet["rivit"]) if toiminta.tavoitteet is not None else None}
        kokoelma = dokumenttikokoelma(request)
        saannot = []
        if kokoelma is not None and kokoelma.tila == "ready":
            saannot = [d for d in (dokumentit_lukija.etsi(kokoelma, t) for t in kehotteet_lukija.SAANTODOKUMENTIT) if d]
        return render(request, "kehotteet", "Promptit ja säännöt", "asetukset", luettelo=luettelo, omat=omat,
                      ryhmat=kehotteet_lukija.ryhmittain(luettelo) if valmis else [], saannot=saannot)

    @app.get("/hub/kehotteet/{tunniste}", response_class=HTMLResponse)
    async def kehote_sivu(request: Request, tunniste: str):
        """Yksi prompti: teksti sellaisena kuin malli sen saa. Muokattavalla lomake gatewaylle (paluu=hub) ja aiemmat
        versiot palautusnappeineen."""
        luettelo = lue_kehotteet(request)
        k = kehotteet_lukija.etsi(luettelo, tunniste) if luettelo is not None and luettelo.tila == "ready" else None
        if k is None:
            return virhe(request, 404, "Promptia ei löydy", "Tällaista promptia ei ole.")
        return render(request, "kehote", k["otsikko"], "asetukset", k=k, korkeus=kehotteet_lukija.korkeus(k["teksti"]))

    # --- Vanhat osoitteet ja virheet ----------------------------------------------------------------------------

    def ohjaus(kohde: str):
        polku, _, ankkuri = kohde.partition("#")

        async def ohjaa(request: Request):
            kysely = request.url.query
            return RedirectResponse(polku + ("?" + kysely if kysely else "") + ("#" + ankkuri if ankkuri else ""),
                                    status_code=307)
        return ohjaa

    for vanha, kohde in VANHAT_OSOITTEET.items():
        app.add_api_route(vanha, ohjaus(kohde), methods=["GET"], include_in_schema=False)

    def virhe(request: Request, code: int, title: str, message: str):
        return render(request, "virhe", title, None, status_code=code, viesti=message, koodi=code)

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return virhe(request, 404, "Sivua ei löydy", "Tarkista osoite.")

    return app
