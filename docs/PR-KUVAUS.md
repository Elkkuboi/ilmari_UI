# Ilmari Hub: suomenkielinen lukukäyttöliittymä ja neljä skiniä

Tyhjästä erillisestä `ilmari_UI`-reposta syntyy palvelinrenderöity Ilmari Hub, jossa käyttäjä voi navigoida kahdeksaan näkymään, vaihtaa neljää skiniä ja tarkastella turvallisesti erikseen julkaistuja ajotuloksia. Julkaisematon tieto näkyy rehellisenä tyhjänä tai yhdistämättömänä tilana. Valmis keskustelunäkymä on ei-aktiivinen, kunnes agenttirajapinta on erikseen hyväksytty, testattu ja asennettu.

## Käyttäjälle näkyvä muutos

- Arctic Command oletuksena; Slate Electric, Nordic Paper ja Aurora Lab käyttävät samaa yhteistä komponentistoa ja semanttisia väritokeneita.
- Koti, Keskustelu, Ajot ja raportit, Hyväksynnät, Sovellukset, Ideat ja projektit, Järjestelmä sekä Asetukset/Ulkoasu ovat omia navigoitavia sivuja.
- Työpöydän sivunavigaatio ja puhelimen viiden kohdan alapalkki; näkyvä näppäimistöfokus, tekstimuotoiset tilat, luettavat raportit ja kosketuskohteet.
- GET-pohjainen teemanvalinta sekä Koti-korttien näkyvyys/järjestys säilyvät Hubin linkeissä. Ei JavaScriptiä tai istuntoevästettä.
- Ravintopolun 7/30/90 päivän kalorikomponentti käsittelee puuttuvan päivän puuttuvana; UniCafe vaatii päivätyn listan; kolme ideaa erottavat oletuksen ja kokeen; Jarvis vaatii omistajan jakamisluvan.
- Eristetty opt-in-demo näyttää selvästi **DEMO – ESIMERKKIDATA**. Oletus ei esitä demoajoja, mittareita, budjettia tai sovellusyhteyksiä todellisena.

## Toteutus ja tiedostokokonaisuudet

| Kokonaisuus | Tiedostot ja tarkoitus |
| --- | --- |
| Python/uv-projekti | `pyproject.toml`, `uv.lock`, `.python-version`, README ja Git-ignore |
| SSR-sovellus | `src/ilmari_ui/app.py`, `cli.py` ja yhteiset Jinja-pohjat |
| Design system | `themes.py`, paikallinen tokeni-/layout-CSS ja paikalliset kuvakkeet |
| Ajolukija | `runs.py`: kiinteä julkaisujuuri, viisi sallittua tiedostoa, descriptor-pohjainen polku-/snapshot-suojaus ja lukurajat |
| Sovelluskortit | `cards.py`: tiukasti tyypitetty `ilmari.card.v1`-ehdotus, luotettu julkaisija/dataluokka, private opt-in ja restricted-kielto |
| Kehitysfixturet | `src/ilmari_ui/demo`: synteettiset julkaisut vain erikseen sallitussa demoajossa |
| Testit | `tests/`: UI-/skin-/turvaraja-, julkaisu- ja korttivalidaation kokeet sekä eristetyt selaintarkistukset |
| Dokumentaatio | UI-määrittely, integraation ADR-ehdotus, ennakkotarkistukset, korttisopimus ja tämä PR-kuvaus |
| Lähdehistoria | Alkuperäinen `docs/ilmari-ready.md` kokonaisena; `docs/TILANNE.md` uutena UI-päivityksenä ja täydellisenä muuttamattomana aiops-taustana |

Tiedostokokonaisuudet kuvaavat tarkistettavaa toteutusta. Täsmällinen lopullinen lisäyslista saadaan komennolla `git status --short` ja työpuun diffistä. Tyhjässä lähtörepossa ei ole main-koodia, johon näitä uusia tiedostoja voisi regressiovertailuna verrata.

## Turvallisuus ja oikean datan raja

Hub hyväksyy vain paikallisen Unix-soketin lukupyynnöt tarkalla kehityksen Host/Origin/Fetch-vartijalla. CLI:ssä ei ole TCP- tai tunnelivaihtoehtoa. Tailscale-otsakkeisiin ei luoteta tässä standalone-sovelluksessa käyttäjätunnistuksena; tuotannossa reitit liitetään nykyisen aiops-gatewayn vartijan alle erillisellä tarkistetulla adaptaatiolla.

Ajolukija käyttää vain hyväksyttyä julkaisujuurta. Se ei saa pääsyä agentin työkopioon, kotihakemistoon, `/srv/aiops/data`:an tai alustan tietokantaan. Raportti/diff on escapettua tekstiä. Symlinkit, hardlinkit, erikoistiedostot, traversal, lukuhetken muutokset, virheellinen JSON/JSONL ja liian suuret syötteet torjutaan. Aikarajat edellyttävät luotettua paikallista tiedostojärjestelmää.

MUODOT.md puuttui tämän uuden repon lähtöaineistosta, joten oikean meta.json:n ja Sol-tuloksen semantiikkaa ei arvata. Lukija esittää julkaistun JSON:n turvallisesti, ja fixtureiden `demo_`-kenttiä tulkitaan vain demossa. Tuotantoadapteri ja ajotulosten atominen vienti tehdään nykyisen korjatun MUODOT.md:n ja alustan koodin perusteella.

Korttijulkaisu ei saa määritellä itselleen dataluokkaa tai lähdehostia. Private-lähteet vaativat palvelinpuolen sovelluskohtaisen luvan; restricted-koosteita ei lueta. URL-viite ei aiheuta verkkokutsua. Jokainen sovellusyhteys hyväksytään erikseen. UI ei lue API-/hyväksyjäavaimia, tee GPU-kutsuja, kirjoita kantaa, muuta politiikkaa, hyväksy töitä tai lähetä terveystietoa ulkoiseen palveluun.

Nykyisen aiops-alustan `/ilmari`-, WebAuthn- ja työreitit eivät sisälly tähän lähdecheckoutiin eikä niitä ole muutettu. Tämän repon testit eivät todista alkuperäisen gatewayn/dispatcherin regressioita. Ne ajetaan myöhemmässä aiops-integraatiotyössä nykyistä haaraa vastaan.

## Validointi

**472 testiä läpäisi**, ei epäonnistumisia tai ohituksia. Näistä 65 on eristettyjä Chromium-tarkistuksia. Yksi riippuvuuden Starlette/TestClient-deprekaatiovaroitus. Todellinen Unix-HTTP, SIGTERM-lopetus ja uudelleenkäynnistys sekä rakennetun wheel-paketin resurssit ja renderöinti on varmennettu.

```bash
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen --group browser
uv run --frozen --group browser pytest -q
```

Selaimessa Koti tarkistettiin neljällä skinillä ja leveyksillä 320/375/412/768/1024/1440 px; kaikki 13 sivutyyppiä 320/768/1440 px. Ei sivun vaakavieritystä tai kolmannen osapuolen verkkopyyntöjä. Näppäimistö, näkyvä fokus, puuttuvan havainnon taulukko, kosketuskohteet ja 200 % zoomausta vastaava 720 CSS-pikselin asettelu tarkistettiin. Kahdeksan kuvakaappausta syntyi `artifacts/screenshots/`-hakemistoon. Muut tietoturva-, julkaisu- ja virhelähdekokeet läpäisivät. Ympäristön tallennetun asennusskriptin `bash -n` ja ShellCheck läpäisivät. Tämä ei todista alkuperäisen aiops-gatewayn tai dispatcherin regressioita.

## Tuotantokäyttöönoton ehdot

Koodaus erilliseen repoon on käyttäjän valtuuttama. Tuotantoliitännän [ADR-UI-0001](adr/0001-hub-integration-proposal.md) on **ehdotus**, ei hyväksytty päätös. C2/C3 ovat avoimet: oma vähimmäisoikeusmalli, vanhempien traversal, kovennus ja nykyisen gatewayn suojattu liikennepolku. Hubia ei kytketä uuteen TCP-porttiin tai suoraan Serve-julkaisuun.

[Vain lukevat ennakkotarkistukset](INTEGRAATIO.md) ovat kopioitavia ilman paikkamerkkejä. Ne vahvistavat aiops-mainin, PR #22:n/MUODOT-PR:n, todellisen julkaisusopimuksen, asennetun kärjen, oikeudet ja Serve-/gateway-tilan. Tässä toimituksessa ei ole asennettava systemd-palvelua eikä deploy-/sudo-komentoa, koska oikea C2/C3-ratkaisu ei ole päätetty.

Muutoksessa ei ole SQLite-migraatiota. Myöhemmän gateway-mountin palautus on tarkistetun UI-integraation koodipalautus; alustan kanta, budjetti, hyväksyjäavaimet ja ajotulokset jäävät alkuperäisen omistajan hallintaan. Tuotannon konfiguraatiopalautus kirjoitetaan valitun integraation rinnalle. Tässä työssä ei ole isäntämuutosta tai muutoslokimerkintää. Käyttäjän GitHub-toimitusta koskevan jatkopyynnön perusteella toteutus commitoidaan ja toimitetaan `ilmari-hub`-haaralle. Etärepo oli tyhjä, joten PR:n vertailulle ei ollut vielä perushaaraa; tämä kuvaus säilyy myöhemmän integraation katselmointia varten.
