# Ilmari Hub: käyttöliittymän määrittely ja toteutuksen rajat

Päiväys 13.10.2026, Europe/Helsinki. Tämä dokumentti määrittelee käyttäjän pyytämän uuden `ilmari_UI`-repon käyttöliittymän, turvallisen eristetyn lukukerroksen ja tuotantointegraation ehdot. Tuotantoliitäntä kuvataan erikseen [ADR-ehdotuksessa](../adr/0001-hub-integration-proposal.md) ja [ennakkotarkistuksissa](../INTEGRAATIO.md).

## Lähtötila ja lähteiden etusija

Repo oli käyttäjän mukaan tarkoituksella tyhjä. Käyttäjän uusi pyyntö valtuuttaa UI:n koodaamisen sinne; se ratkaisee kehityksen toimituspaikan. Tämän checkoutin alussa ei ollut `AGENTS.md`:tä, aiops-alustan koodia, sen ADR:ien hyväksyttyjä tiedostoja tai `apps/ilmari-selain/MUODOT.md`:tä.

Kolme luettua liitettä ovat käyttöliittymän toimeksianto, 8.10. Ilmari-ready-luonnos ja 13.10. aiops-tilannekuva. Ajantasainen päivätty alun päivitys menee tilannekuvan vanhojen historiakohtien edelle. Sen mukaan ADR-0011 v5 on hyväksytty ja `/ilmari`-puhelinohjaus käytössä. Sen perusteella ei oleteta yleistä keskustelu-/istuntorajapintaa tai sovellusten julkaisujärjestelmää. Nykyisen alustan koodi ja hyväksytyt ADR:t määräävät lopullisen tuotanto-adapterin.

| Kokonaisuus | Toimituksen tila ja lähde | Tuotannossa puuttuva näyttö |
| --- | --- | --- |
| Hubin sivut ja skinit | Uuden repon palvelinrenderöity toteutus | Työaseman julkaisu nykyisen vartijan alla |
| Ajotulosten turvallinen luku | Rajattu tiedostolukija; eristetyt fixturet | MUODOT-semanttiikka, julkaisija, oikeudet ja todellinen julkaisu |
| Sovelluskortit | Tiukka `ilmari.card.v1`-ehdotus ja lukija | Hyväksytyt julkaisijat/dataluokat ja jokaisen sovelluksen lupa |
| Puhelinohjaus ja WebAuthn | Taustadokumentin mukaan aiops-alustalla käytössä | Nykykoodin ja asennetun kärjen tarkistus; Hubiin ei kopioida kirjoitusreittejä |
| Keskustelu ja istunnot | Visuaalinen ei-aktiivinen näkymä | Hyväksytty, testattu ja asennettu agenttirajapinta |
| Järjestelmä ja budjetti | Selkeä ei-saatavilla-tila | Sallittu, päivätty vain luku -julkaisu; ei root-kirjanpidon lukuoikeutta |

Isäntätilaa ei ole mitattu tästä pilviympäristöstä. Tässä repossa ei ole tehty isäntämuutosta, deployta tai Git-julkaisua.

## Tuotekokemus ja näkymäkartta

Hub on rauhallinen suomenkielinen henkilökohtainen operointinäkymä. Se näyttää lähteen ja päivityksen luotettavuuden lähellä tietoa. Sivun käyttö ei saa antaa ulkoasun perusteella vaikutelmaa hyväksyntä- tai mallivallasta.

| Näkymä | GET-polku | Käyttäjän polku | Puuttuvan lähteen tila |
| --- | --- | --- | --- |
| Koti | `/hub` | Tilannekuva → viimeisimmän ajon raportti → valitut sovellukset | Kehitysympäristö; ei tekaistua live-tilaa |
| Keskustelu | `/hub/keskustelu` | Näe tulevan keskustelun rakenne ja aktivointiehto | Keskustelu tulee käyttöön hyväksytyn ja asennetun agenttirajapinnan jälkeen |
| Ajot ja raportit | `/hub/ajot` | Julkaisut → `/hub/ajot/ajotunnus` → raportti, ehdotukset, Sol ja diff | Julkaisua ei saatavilla / tyhjä / virhe / osittainen julkaisu |
| Hyväksynnät | `/hub/hyvaksynnat` | Näe hyväksynnän turvallisuusperiaate; myöhemmin todennettu työkohtainen linkki | Ei liitettyä hyväksyntälistaa; ei hyväksyntäpainiketta |
| Sovellukset | `/hub/sovellukset` | Katalogi → `/hub/sovellukset/ravintopolku`, `/unicafe`, `/ideat` tai `/jarvis` saman prefiksin alla | Ei yhdistetty / tietoa ei saatavilla / virhe |
| Ideat ja projektit | `/hub/ideat` | Kolmen idean ongelma–hypoteesi–koe-vertailu | Ei vielä ideoita; ei keksittyä markkinafaktaa |
| Järjestelmä | `/hub/jarjestelma` | Näe todellisen mittausjulkaisun vaatimus ja budjetin omistaja | Mittareita ja budjettia ei saatavilla |
| Asetukset ja ulkoasu | `/hub/asetukset` | Valitse skin, Koti-kortit ja järjestys; palaa sivuille | GET-mieltymykset toimivat ilman taustapalvelua |

Sovellusten tarkat polut ovat `/hub/sovellukset/ravintopolku`, `/hub/sovellukset/unicafe`, `/hub/sovellukset/ideat` ja `/hub/sovellukset/jarvis`. Virheellinen sovellustunnus, ajotunnus tai reitti tuottaa turvallisen 404-näkymän.

Työpöydällä sivunavigaatio, joustava pääsisältö ja Kotisivun kontekstipalsta tukevat kerroksittaista lukemista. Tabletilla sisältö tiivistyy; puhelimessa kortit ovat yhdessä sarakkeessa. Viiden kohdan alapalkki näyttää Koti, Keskustelu, Ajot, Hyväksynnät ja Sovellukset. Muu navigaatio on saavutettavassa sovellusvalikossa. Sivua ei vaihdeta automaattisesti.

## Design system ja neljä skiniä

Semanttinen HTML, yhteinen layout ja paikallinen CSS ovat kaikille skineille samat. `html[data-skin]` valitsee värit. Teemarekisteri on `src/ilmari_ui/themes.py`, tokenit `src/ilmari_ui/static/themes.css`. Käyttöliittymä on ilman JavaScriptiä ja käyttää järjestelmäfonttipinoa. Skin valitaan näkyvästä Ulkoasu-asetuksesta myös puhelimella.

| Skin | ID | Luonne |
| --- | --- | --- |
| Arctic Command | `arctic-command` | Oletus: yönsininen, jäinen minttu, hillitty sininen |
| Slate Electric | `slate-electric` | Grafiitti, vaaleansininen, kupari |
| Nordic Paper | `nordic-paper` | Vaalea paperi, havunvihreä, tumma teksti |
| Aurora Lab | `aurora-lab` | Indigo, laventeli, turkoosi |

Kriittiset tokeniryhmät:

| Käyttö | Tokenit |
| --- | --- |
| Pinnat | `--il-bg`, `--il-surface`, `--il-surface-raised` |
| Teksti | `--il-text`, `--il-text-muted`, `--il-text-subtle` |
| Rajat | `--il-border`, `--il-border-strong` |
| Korostus ja fokus | `--il-accent`, `--il-accent-text`, `--il-accent-soft`, `--il-secondary`, `--il-focus` |
| Semanttiset tilat | `--il-success`, `--il-success-soft`, `--il-warning`, `--il-warning-soft`, `--il-danger`, `--il-danger-soft` |
| Kaaviot | `--il-chart-1`, `--il-chart-2`, `--il-chart-grid` |
| Kerrokset | `--il-shadow`, `--il-overlay` |

Värin lisäksi jokaisella tilalla on teksti. Minttu ei yksin merkitse onnistumista tai hyväksyntää. Koristereuna ei kanna lomakkeen merkitystä; `border-strong` ja fokus tokenit ovat merkityksellisten rajojen lähtökohta. Testit mittaavat normaalin tekstin kontrastin vähintään 4,5:1 ja merkityksellisen grafiikan/fokuksen 3:1. Paletin kattavuus tarkistetaan kaikista skineistä.

Lisää uusi skin määrittelemällä koko tokenijoukko uutena `[data-skin="uusi-id"]`-lohkona ja rekisteröimällä ID, nimi ja lyhyt kuvaus `SKINS`-rekisteriin. Sama tokenilohko toimii sivun `html`-elementissä ja asetusten palettiesikatselussa; erillistä esikatseluluokkaa ei tarvita. Komponentteihin ei lisätä uutta teemahaaraa. Tokeni-/kontrastitesti estää puuttuvat tokenit. Tuntematon skin palautuu `arctic-command`:iin.

Teema on GET-parametri `skin`. Linkit säilyttävät sen koko Hubissa. Koti-korttien näkyvyys ja järjestys kulkevat `home_cards`-parametrissa tunnettujen sovellustunnusten listana. Tuntemattomat arvot ja duplikaatit suodatetaan. Ravintopolun `days` on vain 7, 30 tai 90. Valintojen säilyvyys tarkoittaa tässä URL:n ja selaimen historian säilyvyyttä: ei istuntoevästettä tai localStoragea. Käyttäjä voi tallentaa valitun osoitteen kirjanmerkiksi. Esitysmieltymys ei myönnä tietojen lukuoikeutta.

## Ajotulosten lukusopimus

`RunReader` lukee vain ylläpitäjän valitseman absoluuttisen julkaisujuuren. Tuotannon tavoite on `/srv/aiops/ilmari/ajot`. Selaimen URL ei valitse juurta tai tiedostonimeä. Ajotunnus on ASCII-muotoa `[0-9]{8}-[0-9]{6}-yo-[a-z0-9]{1,32}` ja tarkistetaan koko merkkijonosta; se on tekninen nimi, ei todistettu aloitusaika.

| Sallittu tiedosto | Enimmäiskoko | Esitys ja validaatio |
| --- | ---: | --- |
| `meta.json` | 64 KiB | JSON-olio; turvallinen metadatan tarkastus |
| `raportti.md` | 512 KiB | UTF-8-teksti escapettuna; ei HTML-Markdown-renderöintiä |
| `ehdotukset.jsonl` | 512 KiB | Enintään 512 JSON-oliota, 16 KiB/rivi; ei tyhjiä rivejä |
| `sol-tulos.json` | 256 KiB | JSON-olio tai lista; turvallinen tekstiesitys |
| `luonnos.patch` | 1 MiB | Escapettu teksti; ei soveltamista tai suoritusta |

JSON torjuu päällekkäiset avaimet, NaN/Infinityn, yli 12-tasoisen rakenteen, yli 4096 rakennealkiota, yli 64-kenttäisen olion, yli 1024-alkioisen listan, liian pitkät avaimet/tekstit, ylisuuria lukuja ja kiellettyjä ohjaus-/suunnanohjausmerkkejä. Kokoraja tarkistetaan ennen lukua ja kasvun aikana. Vain tavalliset yhden hardlinkin tiedostot sallitaan. Hakemistot ja kaikki esi-isät avataan fd-suhteisesti `O_NOFOLLOW`-lipulla; tiedostot myös `O_NONBLOCK`:lla putkia vastaan. Inode-/laitetunnus ja tiedoston snapshot tarkistetaan ennen ja jälkeen luvun. Aikaraja on oletuksena sekunti; listaus näyttää enintään 100 ajoa ja skannaa enintään 2000 merkintää.

Aikaraja on yhteistyöllinen lukusilmukan raja, ei keskeytys jumittuneelle kernelin I/O-kutsulle. Käyttö edellyttää luotettua paikallista tiedostojärjestelmää. Julkaistun snapshotin kaikki tiedostot eivät saa muuttua lukemisen aikana; tuotannon julkaisija huolehtii atomisesta valmistumisesta. Symlink-/inode-suojat eivät yksin todenna julkaisijan henkilöä tai tietoluokkaa.

Puuttuva yksittäinen tiedosto on osittainen julkaisu ja näkyy nimettynä virheenä; toisen turvallisesti luetun tiedoston sisältö säilyy. Juuren vaihtumisen tulokset hylätään. Virheteksteihin ei vuoda absoluuttisia sisäisiä polkuja. UI ei tarjoa mielivaltaista tiedostolatausreittiä.

**Semantiikan tärkeä raja:** MUODOT.md:n puuttuessa lukija ei tulkitse oikean meta.json:n kenttiä malliksi, ajoajaksi, työn tilaksi tai Sol-tuomioksi. Oikea julkaisu voidaan näyttää turvallisena tekstinä/metadatana. Erilliset kehitysfixturet käyttävät `demo_`-kenttiä, jotka eivät ole tuotannon skeema. Yhteensopivuus vaatii nykyisen MUODOT.md:n ja koodin katselmoinnin; tämä toimitus ei toteuta yöajon vientiä eikä väitä sitä asennetuksi.

## Sovelluskorttien sopimusehdotus

Täydet kentät, julkaisutiedostojen rakenne ja esimerkki: [korttien julkaisusopimus](../card-publication.md).

Tiedostokohtainen `schema_version` on `ilmari.card.v1`. Sopimus sisältää `app_id`, `card_id`, `kind`, `title`, `data_class`, `published_at`, `observed_until`, `fresh_until`, `source`, `units` ja tietotyypin mukaan tarkasti rajatun `data`:n. Kaikki tuntemattomat kentät hylätään. Aikaleima sisältää aikavyöhykkeen ja järjestys on havaittu ≤ julkaistu ≤ tuoreuteen saakka. Käyttöliittymän ajat näytetään Europe/Helsinki-ajassa.

| Tyyppi | Säännöt |
| --- | --- |
| `metric` | Äärellinen numero tai `null`; huomautus erillisenä tekstinä; bool/numerojono ei kelpaa luvuksi |
| `time_series` | Enintään 366 päivää ja pistettä, oikeat kalenteripäivät, nouseva yksilöllinen järjestys, jakson sisällä, viimeiseen havaintopäivään asti |
| `recommendation_list` | Täsmällinen `for_date`, eksplisiittiset kriteerit, enintään 30 annosta ja 12 kriteeriä/tietotagia |
| `idea_list` | Täsmälleen kolme eri ideatunnusta, ongelma, ratkaisu, oletus ja seuraava koe; vaihe `idea`, `hypothesis` tai `tested` |
| `update_feed` | Enintään 30 yksilöllistä päivitystä; ajallinen lähde ja havaintorajaus; rajattu sallittu tarkempi teksti |

Yksi kortti on enintään 64 KiB, sovellus julkaisee enintään kahdeksan korttia ja hakemistossa voi olla enintään 32 merkintää. Lyhyt teksti on enintään 160 merkkiä, kuvaava teksti 1000, tarkempi päivitysteksti 4000 ja yksikkö 32. Numeroon ei voi syöttää boolia, numerojonoa, NaN/Infinityä tai itseisarvoltaan yli `1e15`:n lukua.

Polku on ylläpitäjän valitseman julkaisujuuren alla `app_id/card_id.json`. Identiteetti ja dataluokka verrataan luotettuun palvelinasetukseen; julkaisu ei itse määritä lukuoikeuttaan. `restricted`-koosteet hylätään. Yksityinen kortti vaatii sovellustunnuksen erillisen palvelinpuolen luvan. Virhe eristetään sovelluksen tasolle, eikä yksi viallinen kortti kaada Koti-sivua. Luotettu julkaisija ja muuttumattomaksi julkaistu snapshot ovat myös korttien prerequisites.

Sallitut lähdeviitteet ovat HTTPS-osoitteita julkiseen hostnameen ilman tunnuksia tai muita portteja kuin 443; IP-osoitteet, paikalliset nimet, ohjausmerkit ja `javascript:`/`data:`/`file:`-skeemat torjutaan. Host pitää erikseen sallia palvelimella. Lähteen URL ei valtuuta fetchiä, eikä Hub tee verkkohakua. Sisältö renderöidään Jinja-autoescapingilla tekstinä.

Kortin tilat ovat `ajantasainen`, `vanhentunut`, `ei yhdistetty`, `tietoa ei saatavilla`, `virhe` ja vain erikseen sallitussa kehityksessä `esimerkkidata`. Kortti näyttää lähteen, havaintojakson/havaintoon asti -ajan, julkaisuajan ja tuoreuden. Vanhentunut julkaisu merkitään näkyvästi. Tulevaisuuden päiväkohtainen ruokalista ei muutu tämän päivän tiedoksi.

### Neljän sovelluksen tuoterajat

Ravintopolussa puuttuva päivä on `null` tai jätetty havainto, joka täydennetään puuttuvaksi. SVG-viiva katkeaa puuttuvalla kohdalla eikä interpoloi tai muuta sitä nollaksi. Esitetään kcal, kattavuus ja 7/30/90 päivän rajaus. Tavoitteita tai terveystulkintoja ei päätellä.

UniCafe näyttää päivätyn julkaistun listan ja eksplisiittiset kriteerit, mikäli lähde on saatavilla. Eilinen ruokalista on vanhentunut tieto; sitä ei nimetä tämän päivän listaksi. Ensimmäinen oikea hakija on tuleva erillinen palvelu, eikä gatewayn verkkoa avata.

Ideat näyttää täsmälleen kolmen lähteistetyn idean vertailun, tai rehellisen tyhjän tilan. Hypoteesi ja fakta erotetaan tekstillä. `tested`-merkintä on julkaisijan luokitus, ei riippumattomaksi todisteeksi ylennetty AI-väite.

Jarvis näyttää vain Joonaksen nimenomaisesti jakamat julkaisut hyväksytyn tuontikanavan jälkeen. Tämän repon oletus on ei yhdistetty. Kehityksen esimerkkisyöte on keksittyä tuotteen esityksen testausta, ei Joonaksen oikea päivitys tai lupa.

## Paikallinen käyttö ja luottamusraja

Sovellus tehdään `create_app(Settings(...))`-tehtaalla. Asetusten julkaisujuuret, dataluokkakartta, yksityisten sovellusten lupa ja lähdehostit ovat ylläpitäjän koodiasetuksia, eivät query-parametreja. `cards_dir=None` tarkoittaa yhdistämättömiä sovelluksia. CLI ei myönnä yksityisten sovellusten lupaa tai yhdistä niiden julkaisujuurta. Ajolukijan oletuskohteen puuttuminen näyttää ei-saatavilla-tilan.

CLI avaa vain Unix-soketin, jonka hakemisto on käyttäjän omistama 0700 ja soketti 0600. Ei TCP-optiota tai kehitys-previewn tunnelia. Paikallinen HTTP-vartija vaatii täsmälleen `Host: ilmari.local`, hylkää ei-Unix-ASGI-kutsujan (`scope.client` ei saa sisältää TCP-osoitetta), Funnel-otsakkeen, cross-site-kutsun, väärän Originin sekä muut metodit kuin GET/HEAD. Se ei käytä Tailscale-otsaketta käyttäjän todennuksena. Tämä vartija täytyy erikseen sovittaa nykyisen gatewayn luottamusketjuun ennen tuotantoliitäntää; appin suora mount ei sellaisenaan ole hyväksytty adapteri.

Paikallisen demon käynnistys ja Unix-soketin lukusavukoe uuden repon juuresta:

```bash
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen
uv run --frozen ilmari-ui --demo --socket .runtime/hub.sock
```

Toisessa komentoterminaalissa samasta hakemistosta:

```bash
curl --unix-socket .runtime/hub.sock -H 'Host: ilmari.local' 'http://ilmari.local/hub?demo=1'
```

Demon käyttö edellyttää sekä palvelimen `--demo`-valintaa että URL:n `demo=1`:tä. Tavallinen `/hub` jää ilman esimerkkidataa myös demon sallivassa prosessissa. Otsake ja kortit näyttävät **DEMO – ESIMERKKIDATA**. Demon päivämäärät ovat fixtureiden havaintoaikoja, eivät nykyisiä mittauksia. Käynnistys ei ota tuotantoyhteyksiä.

CSP kieltää skriptit ja verkkokutsut; kaikki resurssit ovat paikallisia. Vastaukset ovat `Cache-Control: no-store`, `nosniff`, kehystys kielletty ja kameran/mikrofonin/sijainnin luvat pois. Hubin oma Referrer-Policy on no-referrer, koska se ei tee nykyisten POST-sivujen kaltaisia kirjoituksia. Nykyisen WebAuthn-/ohjausgatewayn same-origin Referrer-Policyyn ei muuteta mitään.

## Saavutettavuus ja testauksen näyttö

Tavoite on WCAG 2.2 AA. Toteutus käyttää hyppylinkkiä, otsikkohierarkiaa, näkyvää näppäimistöfokusta, lomakkeiden labeleita, tekstimuotoisia tiloja, vähintään 44 CSS-pikselin kosketuskohteita, paikallisesti vieritettävää raportti-/diff-aluetta ja reduced-motion-valinnan huomiointia. Kaavio tarjoaa myös tekstimuotoisen kattavuuden ja havainnot. Responsiivisuuden kohdeleveydet ovat 320, 375, 412, 768, 1024 ja 1440 px sekä 200 % zoomaus.

Automaattisiin tarkistuksiin kuuluvat skin-tokenit ja kontrastit, kaikki navigointisivut ja skinien säilyminen, puuttuvat/vanhat/virheelliset lähteet, eri sovellusten virheiden eristys, Unix-/metodi-/alkuperävartija, ei kirjoitusreittejä, escapettu haitallinen teksti, tiedostopolkujen ja kokorajojen kielteiset kokeet sekä tiukka korttivalidaatio. Selaintarkistuksissa voidaan käyttää eristettyä ASGI-vastauksiin perustuvaa offline-sisältöä ilman TCP-palvelimen käynnistystä tai tuotantoyhteyksiä.

`UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --group browser pytest -q` läpäisi kaikki 472 testiä ilman ohituksia; mukana 65 Chromium-tarkistusta. Tarkka kattavuus, kahdeksan kuvakaappausta ja 200 % zoomausta vastaavan CSS-viewportin testiraja on kirjattu [TILANNE.md:n alkuun](../TILANNE.md). Ympäristön asennusskriptin `bash -n` ja ShellCheck läpäisivät. Aiops-alustan alkuperäisiä regressiotestejä ei voi ajaa tässä UI-repossa ilman aiops-lähdekoodia.

## Toimitus ja myöhempi aktivointi

Toimitus on tarkistettavat repo-tiedostot ja [PR-kuvaus](../PR-KUVAUS.md). Käyttäjän jatkopyyntö toteutuksen näkymisestä GitHubissa käynnisti toimituksen `ilmari-hub`-haaralle. Etärepo oli vielä tyhjä, joten PR:n vertailulle ei ollut olemassa olevaa perushaaraa. Työaseman muutokset, tuotantointegraatio ja sen arkkitehtuuripäätös ovat edelleen erillinen työ.

Tuotannossa tarvitaan erikseen C2/C3:n ratkaisu, nykyisen gatewayn guardin adapteri, MUODOT-semanttiikka ja atominen vienti sekä sovelluskohtaiset julkaisupäätökset. Keskustelu aktivoidaan vasta agentin hyväksytyn ja asennetun rajapinnan jälkeen. UI ei luo itselleen hyväksyntä-, mallinjohto-, GPU-, politiikka- tai budjettivaltaa.
