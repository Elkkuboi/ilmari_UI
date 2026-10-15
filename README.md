# Ilmari Hub

Suomenkielinen, responsiivinen Ilmari UI. Python 3.12, FastAPI, Jinja2 ja paikallinen CSS. Arctic Command on oletus; lisäksi Slate Electric, Nordic Paper ja Aurora Lab. Ei JavaScriptiä, CDN:ää, tietokantaa tai mallikutsuja.

Käyttöliittymässä ovat Koti, Keskustelu, Ajot ja raportit, Hyväksynnät, Sovellukset, Ideat ja projektit, Järjestelmä sekä Asetukset. Ajotulosten lukija ja sovelluskorttien validaattori ovat toimivia. Keskustelu, työn hyväksyntä, isännän mittarit ja oikeat sovellusliitännät odottavat aiops-integraatiota. Niiden tilaa ei esitetä toimivana.

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

Esimerkkikuvat: [Arctic Command työpöydällä](docs/kuvat/arctic-command-desktop.png) ja [puhelimessa](docs/kuvat/arctic-command-phone.png). Molemmissa näkyvä aineisto on synteettistä esimerkkidataa.

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

`/hub` näyttää oikean yhdistämättömän tilan. `--demo` sallii erikseen valittavan `/hub?demo=1`-esimerkkitilan. Kaikki sen julkaisut ovat synteettisiä, merkittyjä esimerkkejä; ne eivät kuvaa aiops-työaseman ajoja, UniCafen ruokalistaa tai Joonaksen viestejä. Esimerkkitilassa ei ole henkilökohtaisia tietoja eikä palveluyhteyksiä.

Teema, korttivalinta ja korttien järjestys kulkevat GET-osoitteessa. Niitä ei tallenneta evästeeseen, istuntoon tai palvelimelle. Ravintopolun 7/30/90 päivän valinta rajaa julkaistua havaintojaksoa; se ei täydennä puuttuvaa dataa.

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

Ajolukijan voi kehityksessä suunnata **erikseen hyväksyttyyn** julkaisuhakemistoon argumentilla `--runs-dir`. Tuotannon sovittu kohde on `/srv/aiops/ilmari/ajot`; raakakansioita, tietokantaa, avaimia tai työkopiota ei saa liittää Hubiin. Tunnetut julkaisutiedostot ovat `meta.json`, `raportti.md`, `ehdotukset.jsonl`, `sol-tulos.json` ja `luonnos.patch`. Lukija torjuu symboliset linkit, erikoistiedostot, liian suuret sisällöt, virheellisen JSONin ja polkujen vaihtokilpailut. Raportti ja patch esitetään tekstinä.

Aiops-lähderepon luku palautti tässä ympäristössä 403. Siksi `MUODOT.md`:n todellista semanttista skeemaa ja gatewayn koodia ei ole tarkastettu: metatiedot ja Sol-tulos näytetään validoituina julkaisutietoina, niiden kenttiä ei tulkita tuotannon ajotilaksi. Esimerkkien `demo_*`-kentät eivät ole tuotantosopimus.

Sovelluskortit noudattavat tämän repon **ehdotettua** `ilmari.card.v1`-sopimusta. Lähde, havaintoaika, julkaisuhetki ja ajantasaisuus näytetään erikseen. Dataluokka tarkistetaan palvelimen luotetusta asetuksesta; julkaisijan oma väite ei riitä. Yksityiset julkaisut ovat oletuksena pois käytöstä ja `restricted`-yhteenvedot torjutaan. URL-viitteitä ei haeta. Ei plugineja, sovellusten raakakantoja, telemetriaa tai automaattista pilvivientiä.

Tämä kehityspalvelin **ei ole tuotannon Tailscale-tunnistusta toteuttava gateway**. Se hylkää TCP-asiakkaat ja sallii vain paikallisen Unix-soketin lukupyynnöt. Aiops-integraation käyttäjä, tiedosto-oikeudet ja reititys nykyisen suojatun gatewayn kautta vaativat katselmoinnin ja arkkitehtuuripäätöksen. Älä julkaise sokettia Tailscale Servellä tämän ohjeen perusteella.

Katso [UI-määrittely](docs/valmistelu/ilmari-hub-ui.md), [ajojulkaisut](docs/run-publication.md), [korttisopimus](docs/card-publication.md), [integraatio ja ennakkotarkistukset](docs/INTEGRAATIO.md), [ADR-ehdotus](docs/adr/0001-hub-integration-proposal.md) ja [tilannekuva](docs/TILANNE.md). Tämä toteutus toimitetaan käyttäjän jatkopyynnön perusteella `ilmari-hub`-haaralle. Isäntäkoneeseen ei ole tehty muutoksia; tuotantointegraatio ja asennus odottavat erillistä päätöstä.

## Tuotanto työasemalla (aiops ADR-0013)

Tuotantotila käynnistetään konfiguraatiolla: `ilmari-ui --config /etc/ilmari-hub/hub.toml --socket /run/ilmari-hub/hub.sock`.
Silloin Hub hyväksyy vain Tailscale Serven kautta tulevat pyynnöt sallituilta tunnuksilta, lukee julkaisut konfiguraation
hakemistosta ja palauttaa Serven poistaman `/hub`-etuliitteen. Esimerkkitila ja `--runs-dir` eivät ole käytössä.

- Palvelutiedosto: `config/systemd/ilmari-hub.service` (käyttäjä ilmari-hub, ei verkkoa, `/srv`:stä näkyy vain julkaisu).
- Konfiguraation malli: `config/hub.toml.esimerkki`.
- Asennus repon juuresta: `sudo scripts/asenna.sh "$(command -v uv)"` (vain commitoitu koodi, kohde `/opt/ilmari-hub`).

Käyttäjän, ryhmän, konfiguraation ja Serve-polun luonti ovat isäntämuutoksia. Ne tehdään ja kirjataan aiops-repon
muutoslokiin, eivät tämän repon skripteissä.
