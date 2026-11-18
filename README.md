# Ilmari Hub

Suomenkielinen, responsiivinen Ilmari UI. Python 3.12, FastAPI, Jinja2 ja paikallinen CSS. Yksi tyyli: vaalea paperi, tumma muste ja tasalevyinen IBM Plex Mono (OFL, `static/fonts/`). Ei teemoja, JavaScriptiä, CDN:ää, tietokantaa tai mallikutsuja.

Hub on Ilmarin juuri ja Eliaksen ohjauspaikka. Valikossa on neljä sivua: **Nyt** (`/hub`: tila, Töihin nyt, Seis ja Jatka, mikä odottaa sinua, viimeisin raportti, teot ja linkit Ravintopolkuun ja Hahmoon), **Keskustelu**, **Työt** (`/hub/kehita`: toiveet, Ilmarin omat työt ja työn sivu) ja **Asetukset** (yöajo, tavoitteet, pysyvät ohjeet, aivot, rajatesti, kone, dokumentit). Jokainen muutos on lomake gatewaylle samassa alkuperässä; Hubissa ei ole POST-reittejä. Vanhat osoitteet (`/hub/ilmari`, `/hub/mallit`, `/hub/jarjestelma`, `/hub/saannot`, `/hub/ajot`, `/hub/sovellukset`, `/hub/hyvaksynnat`, `/hub/ideat`) ohjautuvat uusiin.

## Hae toteutus omalle koneelle

Toteutuksen toimitushaara on `ilmari-hub`. Kloonaa se omaksi kehityskopioksi:

```bash
git clone --branch ilmari-hub https://github.com/Elkkuboi/ilmari_UI.git
cd ilmari_UI
uv sync --frozen
uv run --frozen ilmari-ui --demo --socket .runtime/hub.sock
```

Komennot ovat Unix-kehitysympäristölle. Toisessa terminaalissa samasta repon juuresta:

```bash
curl --fail --silent --show-error --unix-socket .runtime/hub.sock \
  -H 'Host: ilmari.local' 'http://ilmari.local/hub?demo=1'
```

Esimerkkikuvat: [Nyt työpöydällä](docs/kuvat/nyt-tyopoyta.png) ja [puhelimessa](docs/kuvat/nyt-puhelin.png). Molemmissa näkyvä aineisto on synteettistä esimerkkidataa.

## Käynnistä Codex-pilviympäristössä

```bash
cd /workspace/ilmari_UI
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen
uv run --frozen ilmari-ui --demo --socket .runtime/hub.sock
```

Palvelin kuuntelee vain Unix-soketissa. Hakemiston oikeudet ovat 0700, soketin 0600. TCP-käynnistysvaihtoehtoa ei ole. Selaimen avaaminen suoraan localhostiin ei kuulu tähän ratkaisuun. Sivut voidaan katselmoida eristetyssä selaintestissä ilman verkkoporttia.

Toisessa komentotulkissa:

```bash
cd /workspace/ilmari_UI
curl --fail --silent --show-error --unix-socket .runtime/hub.sock \
  -H 'Host: ilmari.local' 'http://ilmari.local/hub?demo=1'
```

`/hub` näyttää kehitysympäristössä, ettei tietoja ole saatavilla. `--demo` sallii erikseen valittavan `/hub?demo=1`-esimerkkitilan. Sen aineisto on synteettistä ja merkitty jokaisen sivun alussa; napit eivät tee mitään eikä lomakkeita ole. Esimerkkitilassa ei ole henkilökohtaisia tietoja eikä palveluyhteyksiä. Esimerkkitila kulkee GET-osoitteessa, ei evästeessä.

## Tarkista

```bash
cd /workspace/ilmari_UI
UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen pytest -q
```

Selaintestit käyttävät erillistä kehitysryhmää ja järjestelmään asennettua Chromiumia:

```bash
UV_CACHE_DIR=/workspace/.cache/uv uv sync --frozen --group browser
UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --group browser pytest -q -m browser
```

Selaimen pyynnöt ohjataan testissä suoraan ASGI-sovellukseen. Yhtään HTTP-palvelinporttia ei avata. Kuvat syntyvät ohitettuun `artifacts/`-hakemistoon. Selaintestit kertovat ohituksen syyn, jos Playwright tai Chromium puuttuu.

## Julkaistut tiedot ja tuotantoliitäntä

Hub lukee vain kiinteitä hakemistoja `/srv/aiops/ilmari/` alla (toiminta, keskustelu, kehitys, kayttoonotot, mallit, roolit, jarjestelma, dokumentit), jotka gateway, dispatcher tai asennus julkaisee. Yhteinen lukija (`lukija.py`) torjuu symboliset linkit, erikoistiedostot, liian suuret sisällöt, väärät omistajat ja polkujen vaihtokilpailut; teksti näytetään koodattuna. Ajot ja raportit, sovelluskortit, Säännöt-sivu ja teemat poistettiin 18.11.2026 (Hub juureksi); niiden vanhat kuvaukset (`docs/run-publication.md`, `docs/card-publication.md`) ovat historiaa. Konfiguraation avaimet `julkaisut` ja `peruskirja` hyväksytään yhä, mutta niitä ei käytetä.

Tämä kehityspalvelin **ei ole tuotannon Tailscale-tunnistusta toteuttava gateway**. Se hylkää TCP-asiakkaat ja sallii vain paikallisen Unix-soketin lukupyynnöt. Aiops-integraation käyttäjä, tiedosto-oikeudet ja reititys nykyisen suojatun gatewayn kautta vaativat katselmoinnin ja arkkitehtuuripäätöksen. Älä julkaise sokettia Tailscale Servellä tämän ohjeen perusteella.

Katso [UI-määrittely](docs/valmistelu/ilmari-hub-ui.md), [ajojulkaisut](docs/run-publication.md), [korttisopimus](docs/card-publication.md), [integraatio ja ennakkotarkistukset](docs/INTEGRAATIO.md), [ADR-ehdotus](docs/adr/0001-hub-integration-proposal.md) ja [tilannekuva](docs/TILANNE.md). Tämä toteutus toimitetaan käyttäjän jatkopyynnön perusteella `ilmari-hub`-haaralle. Isäntäkoneeseen ei ole tehty muutoksia; tuotantointegraatio ja asennus odottavat erillistä päätöstä.

## Tuotanto työasemalla (aiops ADR-0013)

Tuotantotila käynnistetään konfiguraatiolla: `ilmari-ui --config /etc/ilmari-hub/hub.toml --socket /run/ilmari-hub/hub.sock`.
Silloin Hub hyväksyy vain Tailscale Serven kautta tulevat pyynnöt sallituilta tunnuksilta, lukee julkaisut konfiguraation
hakemistoista ja palauttaa Serven poistaman `/hub`-etuliitteen. Esimerkkitila ei ole käytössä.

- Palvelutiedosto: `config/systemd/ilmari-hub.service` (käyttäjä ilmari-hub, ei verkkoa, `/srv`:stä näkyy vain julkaisu).
- Konfiguraation malli: `config/hub.toml.esimerkki`.
- Asennus repon juuresta: `sudo scripts/asenna.sh "$(command -v uv)"` (vain commitoitu koodi, kohde `/opt/ilmari-hub`).

Käyttäjän, ryhmän, konfiguraation ja Serve-polun luonti ovat isäntämuutoksia. Ne tehdään ja kirjataan aiops-repon
muutoslokiin, eivät tämän repon skripteissä.

### Sovelluksena puhelimessa ja koneella

Avaa `https://TYÖASEMA/hub` Chromessa ja valitse valikosta **Asenna sovellus** (puhelimessa myös **Lisää aloitusnäyttöön**).
Sovellus avautuu omaan ikkunaansa ja pitää gatewayn sivut (passkey-hyväksynnät) samassa ikkunassa. Hub ei toimi ilman
yhteyttä työasemaan, koska siinä ei ole service workeria.
