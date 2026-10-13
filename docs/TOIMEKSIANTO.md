# Codex-toimeksianto: Ilmari Hub — valmis responsiivinen UI ja vaihdettavat skinit

## 0. Roolisi ja tehtäväsi

Toimi kokeneena tuotesuunnittelijana, käyttöliittymäsuunnittelijana, saavutettavuusasiantuntijana, Python/FastAPI-kehittäjänä ja turvallisena järjestelmäarkkitehtina. Työskentelet Ilmari/aiops-projektissa. Toteuta laadukas, oikeasti navigoitava ja testattu **Ilmari Hub** -käyttöliittymä työaseman selaimelle ja puhelimelle. Kyseessä on henkilökohtainen AI-operaatiokeskus, ei geneerinen admin-teema eikä kopio ChatGPT:stä.

**Visuaalinen oletustyyli on ARCTIC COMMAND.** Arkkitehtuurin pitää kuitenkin tukea valmiita vaihdettavia skinejä: **Arctic Command**, **Slate Electric**, **Nordic Paper** ja **Aurora Lab**. Kaikkien pitää toimia samoilla komponenteilla ja näkymillä ilman koodin haarauttamista teeman perusteella.

Tavoitteena on rakentaa mahdollisimman valmis tuotelaatuinen UI, **ei** antaa vain ehdotusta, Figma-kuvia, irrallista HTML-mockupia tai keskeneräisiä komponentteja. Tee toimivat sivut, navigaatio, responsiivisuus, saavutettavuus, skinit, realistiset tyhjät tilat, testit ja dokumentaatio. Integroi oikea data vain sellaisiin nykyjärjestelmän lukurajapintoihin, jotka voit todentaa repossa. Älä keksi taustapalveluja tai ohita turvallisuusrajoja vain siksi, että UI näyttäisi valmiilta.

Vastaa ja kirjoita käyttöliittymän oletustekstit **suomeksi**. Käytä ymmärrettävää termistöä. Käyttäjä on tekninen, mutta käyttöliittymän pitää olla yhtä selkeä puhelimessa kuin työasemalla.

## 1. Aloita lukemalla todellinen nykytila — älä arvaa

Käyttäjä voi antaa erillisinä tiedostoina `TILANNE.md` ja `ilmari-ready.md`. Niitä on käsiteltävä projektin tausta-aineistona, mutta tarkista aina **avaamasi repon** ajantasaiset tiedostot ja mahdolliset erot. Lue ennen suunnittelua:

1. `AGENTS.md`, `README.md` ja `docs/TILANNE.md`.
2. Kaikki hyväksytyt `docs/adr/`-päätökset, erityisesti ADR-0001, 0002, 0003, 0004, 0007, 0008, 0009, 0010 ja **hyväksytty ADR-0011**.
3. `docs/ilmari-ready.md`, jos repossa; muutoin käyttäjän antama `ilmari-ready.md`.
4. `docs/muutosloki.md` ja siihen liittyvät nykyiset systemd-/gateway-/deploy-tiedostot.
5. Mahdolliset `apps/ilmari-selain/MUODOT.md`, `SUUNNITELMA.md`, `docs/valmistelu/` sekä UI-dokumentit ja aiemmat demot, jos ne on annettu.
6. Koodista nykyiset gateway-reitit, Jinja2-pohjat, staattiset tiedostot, autentikointivartijat, CSP, WebAuthn-polku, testit, julkaisuformaatit ja ajon nykyinen tilatiedosto.

**Huomaa dokumenttien aikaero:** 8.10. päivätty `ilmari-ready.md` on osittain luonnos ja viittaa tuolloin keskeneräiseen ADR-0011:een. 13.10. päivätyn `TILANNE.md`:n mukaan ADR-0011 v5 on jo hyväksytty. Älä käytä vanhaa kohtaa B nykytilan totuutena. Hyväksytyt ADR:t ja tarkastettu nykykoodi määräävät; TILANNE:n alun päivätty päivitys on tärkeämpi kuin sen historiakohdat.

Aloita vain lukevilla tarkistuksilla. Tutki Git-tila ja avoimet PR:t ilman isäntämuutoksia; varmista, onko T1:n PR #22 ja MUODOT-PR yhdistetty, sekä mitä `apps/ilmari-selain` oikeasti sisältää. Älä oleta, että jokin PR on mainissa. Selvitä ja kirjaa ennen muutoksia, mitkä ominaisuudet ovat (a) käytössä, (b) toteutettu mutta asentamatta, (c) luonnos, (d) tulevaa suunnittelua. Codex ei näe Eliaksen isäntäkonetta, joten isäntätilan vahvistus tehdään myöhemmin Eliaksen vain luku -tulosteista.

13.10.2026 toimitetun tilannekuvan mukaan käytössä ovat mm. gatewayn nykyiset työ- ja WebAuthn-hyväksyntäsivut, `/ilmari`-puhelinohjaus ja vain lukevat tilatiedot; agentin yleinen keskustelu- ja istuntorajapinta sekä yleinen sovellustietojen julkaisujärjestelmä eivät vielä ole käytössä. Ensimmäiseksi oikeaksi jatkotoiminnoksi on sovittu **vain lukeva ajotulosten selain**, joka lukee erillistä julkaisuhakemistoa `/srv/aiops/ilmari/ajot`. Älä tee tästä ehdotuksesta jälkikäteen väitettä, että selain olisi jo asennettu.

## 2. Tuotekonsepti: yksi Hub, kolme käyttötapaa

**Ilmari Hub** yhdistää:

- **Keskustelu ja tehtävät:** tulevaisuudessa Ilmarille luonnollisella suomen kielellä esitetyt pyynnöt, suunnitelmat ja vastaukset.
- **Operaatiokeskus:** ajot, raportit, hyväksyntää odottavat tehtävät, mallit, GPU/CPU/RAM, auditoitavuus sekä todellinen pilvibudjetti.
- **Henkilökohtainen sovelluskooste:** muiden käyttäjän valitsemien sovellusten julkaisemaa hyödyllistä tilastotietoa — ilman, että Hubista tulee niiden kaikkien tietokantojen pääkäyttäjä.

Käyttöliittymän pitää tuntua **rauhalliselta, täsmälliseltä, laadukkaalta pohjoismaiselta ohjelmistolta**. Inspiraatio: hillitty tekninen komentokeskus, ei neonilla täytetty sci-fi-näyttö, ei kryptopörssin dashboard. Sisältö on tärkeämpää kuin koristelu. Suuret tietomäärät piilotetaan selkeän kerroksellisen esityksen taakse.

## 3. Visuaalinen identiteetti: Arctic Command ja skin-arkkitehtuuri

### Arctic Command (oletus)

Värit lähtöarvoina, joita saat hienosäätää kontrastimittausten perusteella:

- Päätausta `#0B1018` — syvä yönsininen.
- Sivupalkit ja suuret pinnat `#101823`.
- Kortit `#141C29`, korotetut pinnat `#1B2635`.
- Pääteksti `#EDF3FC`, toissijainen teksti noin `#A8B7CC`.
- Ensisijainen korostus `#8EE9CD` — jäinen minttu.
- Toissijainen korostus `#A2BCFF` — viileä sininen.
- Hillityt reunaviivat `#2A3545`.
- Varoitus, onnistuminen, epäonnistuminen ja hyväksyntää odottava tila saavat **omat semanttiset** värinsä ja aina tekstiselitteen. Älä käytä brändin minttuväriä ainoana turvallisuustilan merkkinä.

Ulkonäkö: tummat, matalat pintakerrokset, selkeät yhden pikselin rajaukset, kohtuulliset pyöristykset (kortit noin 12–16 px), selkeä väljyys, rajatut pehmeät varjot, hienovarainen statuspiste ja erittäin vähäinen koristegradientti. Ei raskasta lasiefektiä, jatkuvia hohkuanimaatioita, liukuvia videotaustoja tai keinotekoista futuristista kohinaa. Sovellus tuntuu nopealta ja luettavalta myös puhelimen päivänvalossa.

### Muut valmiit skinit

- **Slate Electric:** grafiittipohja `#101318`, kortit `#1E232B`, vaaleansininen `#B6C9FF`, lämmin kupari `#ECA979`, teksti `#F4F6F9`. Tekninen ja terävä.
- **Nordic Paper:** päätausta `#F5F2E9`, kortit `#FFFEFA`, havunvihreä `#28695B`, messinki `#C78E43`, tumma teksti `#222D29`. Lämmin vaalea lukuteema.
- **Aurora Lab:** tausta `#111324`, kortit `#1D2037`, laventeli `#B3A1FF`, turkoosi `#57D2CB`, teksti `#F2EFFF`. Luovempi, mutta yhtä käytettävä.

### Skinien toteutuksen ehdottomat vaatimukset

1. Tee **yksi yhteinen design system**, ei neljää kopioitua sivustoa. Käytä semanttisia CSS-muuttujia, esimerkiksi `--il-bg`, `--il-surface`, `--il-surface-raised`, `--il-text`, `--il-text-muted`, `--il-border`, `--il-accent`, `--il-accent-text`, `--il-focus`, `--il-success`, `--il-warning`, `--il-danger`, `--il-chart-1` jne.
2. Kaikki komponentit, myös kaaviot, lomakkeet, hover-, focus-, disabled- ja tyhjät tilat, käyttävät **tokeneita**. Älä kovakoodaa Arctic-värejä komponentteihin.
3. Skinin vaihto onnistuu yhdestä näkyvästä **Ulkoasu**-asetuksesta työpöydällä ja puhelimessa. Oletus on Arctic Command. Näytä teemojen nimet ja pienet esikatselusävyt. Valittu skin koskee koko Hubia, ei vain yhtä sivua.
4. Säilyvyys: teema-asetus saa olla vain selaimen paikallinen, ei-arkaluonteinen asetus (esim. `localStorage`), **jos** kyseisen sivun hyväksytty CSP sallii tähän tarvittavan paikallisen JavaScriptin. Jos nykyinen ADR-0010/CSP estää sen, älä avaa skriptirajoitusta hiljaisesti: toteuta toimiva, turvallinen palvelinrenderöity GET-pohjainen teeman valinta tai dokumentoi tarkkarajainen ADR-muutos ennen JS-toteutuksen aktivointia. Älä lisää istuntoevästeitä.
5. Käytä `prefers-reduced-motion`-asetusta, selkeitä fokuskehyksiä ja testaa luettavuus/kontrastit jokaisessa skinissä. WCAG 2.2 AA on tavoitetaso; normaali teksti vähintään 4,5:1 ja merkityksellinen käyttöliittymägrafiikka vähintään 3:1.
6. Käytä mieluiten järjestelmäfonttipinoa tai lisenssiltään sopivaa, paikallisesti toimitettua fonttia. Ei Google Fonts -verkkolatauksia, ikoni-CDN:iä eikä ulkoisia skriptejä.
7. Lisää skinin voi myöhemmin luoda **pelkällä teematokenien määrittelyllä** ja tarvittavalla nimen/esikatselun rekisteröinnillä. Dokumentoi prosessi ja tee testi, joka estää puuttuvat kriittiset tokenit.

## 4. Navigaatio ja näytöt

Toteuta yhteinen navigaatio, jonka keskeiset kohdat ovat:

1. **Koti**
2. **Keskustelu**
3. **Ajot ja raportit**
4. **Hyväksynnät**
5. **Sovellukset**
6. **Ideat ja projektit**
7. **Järjestelmä**
8. **Asetukset / Ulkoasu**

Näytöt voivat toimia jo tässä vaiheessa, vaikka osa taustatoiminnoista olisi merkitty **Ei vielä käytettävissä**. Silloin näyttö ei saa esittää tekaistua tietoa todellisena tai näyttää toimivaa toimintapainiketta, joka ei tee mitään.

### Koti — henkilökohtainen Mission Control

Pöytäkoneella yläosa: Ilmari-brändi, yhteyden luotettavuuden ilmaisu, nykyisen tilan lähde ja päivitysaika, nopea navigointi. Kolme kokonaisuutta:

- **Vasemman reunan navigaatio**: selkeä, tarvittaessa supistettava.
- **Keskipaneeli**: tervehdys/tilannekuva, "Mitä haluat tehdä?" -kehote (vain jos keskustelutoiminto oikeasti sallittu; muuten informatiivinen esikatselu), viimeisimmät ajot, tärkeimmät tapahtumat.
- **Oikea kontekstipaneeli**: odottavat hyväksynnät, mallin tila, budjetti ja pienet sovelluskortit, kun todelliset tiedot ovat saatavilla.

Käyttäjä voi valita, mitkä sovelluskortit näkyvät etusivulla, sekä järjestää niitä (aloita vain paikallisista ei-arkaluonteisista esitysmieltymyksistä). Näytä tavallisesti 4–6 huolellisesti kuratoitua korttia, ei 20 pientä ja lukukelvotonta mittaria.

### Keskustelu

Suunnittele valmis, uskottava keskusteluruutu: viestivirta, viestin kirjoitusalue, aiheen otsikko, vastausten lähteet, työehdotukset, suorituksen vaiheistus ja erotus "Ilmarin ehdotus" vs "koodin vahvistama tila". Varaudu vaihtuvaan johtajamalliin (paikallinen/Sol) näyttämällä **todennettu** tila, mutta älä anna UI:n muuttaa mallia tai budjettia ilman erikseen sallittua rajapintaa.

**Kriittinen toteutusraja:** ADR-0010 hylkäsi keskustelunäkymän alkuperäisestä V1:stä. ADR-0011:n agentti/istuntokytkennän todellinen tila pitää tarkistaa. Toteuta tarvittaessa valmis mutta **ei-aktiivinen** keskustelunäkymä ja tekstillä "Keskustelu tulee käyttöön, kun agenttirajapinta on hyväksytty ja asennettu". Älä lähetä kehotteita salaa nykyiselle `/ilmari`-lisäohjekentälle, äläkä keksi uutta API:a. Aktivointi vasta erillisen ADR-/toteutuspäätöksen ja testatun rajapinnan jälkeen.

### Ajot ja raportit — ensimmäinen tuotantokelpoinen toiminto

Näytä ajolista, tilat, aloitus/lopetusaika, mahdollinen malli, raportti, ehdotukset, Solin tuomiot T/O/V/E ja tekstimuotoinen diff. Ensimmäinen **oma** ajotulosten selain on vain lukeva. Kohde on sovittu: `/srv/aiops/ilmari/ajot`, **ei** `~/ilmari-yo`, ei agentin työkopio eikä suora pääsy repoon tai `/srv/aiops/data`-hakemistoon.

Tarkista repon `apps/ilmari-selain/MUODOT.md`:n todella olemassa oleva ja korjattu määrittely. Suunnitellut julkaistavat tiedostot: `meta.json`, `raportti.md`, `ehdotukset.jsonl`, `sol-tulos.json`, `luonnos.patch`. Noudata todellisia kenttiä, älä aiemman keskeneräisen `SUUNNITELMA.md`:n mahdollisia virheitä. Raportti voidaan näyttää alkuun turvallisesti **tekstinä**, ei renderöitynä raakaa HTML:ää hyväksyvänä Markdownina. Solin T/O/V/E tarkoittaa tarkastajan luokitusta, ei automaattista totuutta.

Suunnittele ja tarkista erillisen selaimen käyttäjä, hakemistojen oikeudet, symlink-suojaus, `dir_fd`/`O_NOFOLLOW`, tunnetut reitit, ajotunnuksen tiukka tarkistus (nykyinen suunnitelma `^\d{8}-\d{6}-yo-[a-z0-9]+$`, jos todelliset nimet noudattavat sitä), tavallisten tiedostojen vaatimus, JSON/JSONL:n validaatio, tiedostojen ja rivien kokorajat, aikakatkaisut ja virhetilat. Eri käyttäjän sovellus ei saa automaattisesti päästä aiops-ryhmän kaikkiin tietoihin. Määrittele vähimmäisoikeudet erikseen.

Selvitä **ennen verkkoreittejä**, miten erillinen selaimen palvelu liitetään nykyiseen ainoaan Tailscale Serve 443 → gateway Unix-soketti -malliin. Älä oleta, että uusi portti tai uusi suora Serve-julkaisu on sallittu. Mikäli turvallinen reititys vaatii muutoksen ADR-0010:een tai uuteen sovellus-ADR:ään, tee se erilliseksi ehdotukseksi ja jätä asentaminen odottamaan hyväksyntää.

### Hyväksynnät

Näytä odottavat hyväksynnät, työn nimi, riskiperuste/politiikkaluokka, pyytäjä vain jos todennettu, allekirjoitettavan määrityksen tiiviste, voimassaolon tiedot ja työkohtainen linkki **olemassa olevaan hyväksyntäsivuun**. Varsinainen hyväksyntä tehdään **nykyisellä WebAuthn-passkeyllä**, jonka dispatcher tarkistaa. Älä rakenna vaihtoehtoista "Hyväksy yhdellä klikkauksella" -reittiä tai kopioi salaista avainta selaimeen. Vaara- ja peruutustoimissa erillinen vahvistus, jotta puhelimella ei tule vahinkopainalluksia. Säilytä nykyiset toimivat WebAuthn-sivut ja niiden tiukka CSP.

### Sovellukset — omien tietojen keskus

Sovelluskatalogi korteilla: kuvake, nimi, lyhyt kuvaus, yhdistämistila, päivitysaika, dataluokka ja linkki sovelluksen sisäiseen näkymään. Kortteja voi suosia etusivulle. Tärkeä yhteinen sääntö: sovelluksen kortti **julkaisee rajatun valmiiksi lasketun yhteenvedon**, Hub ei saa suoraa yleislukuoikeutta kaikkien sovellusten sisäisiin kantoihin.

Tee neljän esimerkkisovelluksen tuotelaatuinen UI ja rehellinen tietotila:

**A. Ravintopolku**
- Koti-kortti: viimeisen 7 päivän kalorimäärän aikasarja (kcal), havaittujen päivien määrä, viimeinen kirjauspäivä ja lähde.
- Syvempi näkymä: 7/30/90 päivän valitsin, kalorikuvaaja, mahdollinen proteiini/hiilihydraatti/rasva jos sovellus oikeasti julkaisee, kattavuus ja aikarajaus.
- Puuttuva päivä on **puuttuva**, ei nolla. Älä keksi tavoitteita, keskiarvoja tai terveystulkintoja.
- Ravinto-/painotiedot ovat sensitiivisiä. Ei automaattista pilvivientiä, sovellusten ristiinhakua tai raakadataa Hubin yleiskäyttäjälle. Ensivaiheessa käytä "Ei yhdistetty" -tilaa ja rakennettavissa olevaa tiukkaa, vain lukevaa julkaisuskeemaa; näytekaavio vain selvästi **DEMO – ESIMERKKIDATA** -merkinnällä kehitystilassa.

**B. UniCafe**
- Käyttäjän tulevaisuudessa valitsemat seurattavat ravintolat, tämän päivän ruokalista, annosten tunnistetut ruokavaliotiedot, suositusperusteet ja suora lähdeviite.
- Käytä vain oikeasti päivättyä lähdetietoa; puuttuvan tämän päivän listan tila on "Tietoa ei saatavilla". Älä näytä eilistä listaa tämän päivän faktana. Älä keksi ruokia, hintoja, ravintoarvoja tai aukioloaikoja.
- Käyttäjän omat suosituskriteerit ovat eksplisiittisiä (esim. ruokavalio, hinta, mieltymykset). Älä päättele niitä.
- Ulkoinen ravintolatiedon haku on oma tuleva rajattu palvelunsa ja vaatii verkkopäätöksen. **Gatewaylle ei avata verkkoa tätä varten.**

**C. Kolme business-ideaa**
- Kotiin täsmälleen kolme selkeää ideakorttia (kun käyttäjällä on lähde): otsikko, ratkaistava ongelma, ehdotettu ratkaisu, tärkein oletus ja seuraava testattava koe.
- Syvempi näkymä: idean kehitysvaihe, lähteet, kokeet, riskit, päätöshistoria ja mahdollisuus vertailla kolmea ideaa.
- Erota ideointi, hypoteesi ja todennettu fakta selvästi. Älä keksi markkinakokoja tai väitä AI-luonnoksia riippumattomiksi todisteiksi. Jos dataa ei vielä ole, anna toimiva "Ei vielä ideoita" -näkymä eikä sepitettyä menestystarinaa.

**D. Joonaksen Jarvis**
- Näytä vain **Joonaksen nimenomaisesti jakamat** päivitykset, päivityspäivä, lähde, lyhyt yhteenveto ja sallittu tarkempi sisältö.
- Ennen lupaa ja erikseen hyväksyttyä tuontitapaa näyttö on "Ei yhdistetty". Ei oletuksia yhteisistä tunnuksista, Jarvis-API:sta, suoria kyselyjä toisen henkilön koneeseen eikä keksittyjä viimeisimpiä tapahtumia.
- Mahdollinen ensimmäinen toteutustapa on ihmisen hyväksymä julkaisutiedosto; muu kanava vaatii oman tietoturva-/verkkopäätöksensä.

Lisää myöhemmille sovelluksille yleinen "uusi korttityyppi" -sopimus ilman plugineja, jotka voivat ajaa omaa JavaScriptiä tai Pythonia Hubin oikeuksilla.

### Ideat ja projektit

Esitä ideaputki, kolmen idean vertailu, suunnitelmat, muistiinpanot, todennettavat kokeet ja lähteet. Vain niiltä osin kuin nykyinen backend tukee. Uusien ideoiden generointi Ilmarilla on erillinen tuleva agenttitoiminto; älä naamioi sitä käyttövalmiiksi ilman mallikytkentää ja oikeussääntöjä.

### Järjestelmä

Kuvaa saatavilla olevat aidot mittarit: CPU, RAM, GPU/VRAM, aktiivinen paikallinen malli, ajot, Solin budjettikirjanpito ja viimeisin tarkistusaika. Älä näytä vanhaa mittausta reaaliaikaisena. Jos budjettipalvelu on vain rootilla ajettava skripti eikä Hubilla ole sallittua lukunäkymää, käytä tilaa "Ei saatavilla" tai ehdota pientä erikseen hyväksyttävää read-only-julkaisua. Älä anna gatewaylle pääsyä API-avaimeen tai budjettikirjanpidon kirjoitukseen.

## 5. Työpöytä- ja mobiilikokemus

**Työpöytä (noin ≥ 1200 px):** 220–248 px sivunavigaatio, joustava pääsisältö ja tarvittaessa 290–340 px oikea kontekstipalsta. Pääsisällössä selkeä lukuleveys (raporteille n. 70–85 merkkiä/rivi), kaavioille enemmän. Näytä toimintoihin liittyvä konteksti ilman turhaa välilehtien vaihtelua.

**Tabletti (n. 768–1199 px):** kapea navigaatio tai saavutettava avautuva valikko, yksi tai kaksi saraketta sisällön mukaan; oikea sivupaneeli siirtyy sisällön jälkeen.

**Puhelin (320–767 px):** yläosaan otsikko, yhteyden tila ja aukeava valikko; alas helposti peukalolla käytettävä enintään viiden kohdan päänavigaatio: **Koti, Keskustelu, Ajot, Hyväksynnät, Sovellukset**. Muut kohdat sovellusvalikkoon. Kortit yhdessä sarakkeessa, kaaviot toimivat kapeasti, turvalliset hyväksyntätoiminnot eivät osu vahingossa. Huomioi `safe-area-inset-bottom`, käyttö 320, 375 ja 412 px leveydellä, pitkät suomenkieliset sanat ja 200 % zoomaus.

Toimintojen kosketuskohteet vähintään noin 44×44 CSS-pikseliä, teksti luettavaa ilman zoomausta, koodiblokit/tulosteet vieritettävissä omassa rajatussa alueessa. Näkymissä tulee olla skeleton/odotus, tyhjä, vanhentunut, virhe, ei käyttöoikeutta, ei yhdistetty ja valmis -tilat. Ei vilkkuvia tilapäivityksiä tai yllätysnavigointia.

## 6. Tietoarkkitehtuuri ja sovelluskorttien julkaisut

Erota neljä asiaa toisistaan:

1. **Raakadata** pysyy omistavassa sovelluksessa ja sen käyttöoikeuksissa.
2. **Julkaistu, validoitu yhteenveto** on erillinen suppea skeema.
3. **Hubin esitys** on turvallinen lukija, ei päätöksentekijä.
4. **Ilmarin malli** saa käyttää vain sellaisia tietoja, joihin agentti-/dataluokkapolitiikka erikseen antaa oikeuden.

Luo ehdotus dokumentoiduksi skeemaksi (`ilmari.card.v1` tai parempi perusteltu nimi), mutta **älä väitä sitä olemassa olevaksi API:ksi**. Vähintään: `schema_version`, `app_id`, `card_id`, `kind`, `title`, `data_class`, `published_at`, `observed_until`, `fresh_until`, `source`, `units` ja tiukasti tyypitetty `data`. Määrittele eri tietotyypeille eri validointisäännöt: `metric`, `time_series`, `recommendation_list`, `idea_list`, `update_feed`. Lisää kokorajat, maksimipituudet, aikaleimojen jäsennys, sarjapisteiden lukurajat, numerotyyppitarkistukset, puuttuvan tiedon mallinnus ja tunnetut kentät.

Jokaisessa kortissa näytä **lähde, havaintojakso, julkaisuhetki ja päivityksen luotettavuustila**. Tilat: `ajantasainen`, `vanhentunut`, `ei yhdistetty`, `tietoa ei saatavilla`, `virhe` ja vain kehityksessä `esimerkkidata`.

Estä riippuvuusrikkomukset: yhteen korttiin tullut virhe ei kaada Koti-sivua. Korteilla ei ole oikeutta kutsua omia URL:eja selaimesta, muuttaa politiikkaa, käynnistää GPU:ta, hyväksyä töitä, lukea salaisuuksia tai lähettää yksityistä dataa pilveen. Ulkoisten lähteiden tekstit ovat epäluotettavia: näytä ne escapettuina tekstinä, älä suorita HTML:ää, skriptejä tai mielivaltaisia linkkiskeemoja. Älä luota kortin itse ilmoittamaan dataluokkaan ilman luotettavaa julkaisijaa ja palvelinpuolen sääntöä.

## 7. Tekninen toteutus ja tiukat turvarajat

Noudata projektin olemassa olevaa teknistä pinoa: **Python, FastAPI, Jinja2, systemd, SQLite, uv ja tarvittaessa kovennettu Docker**. Suosi palvelinrenderöintiä, semanttista HTML:ää ja paikallista CSS:ää. Vältä React/Next.js/Vite/Node-tuotantoalustaa, SPA-rakennetta, uutta tietokantaa ja uusia run-time-palveluja, ellei hyväksytty ADR sitä vaadi. Älä rakenna mikropalveluverkostoa UI:n vuoksi. Pieni paikallinen JS sallitaan **vain**, jos nykyinen hyväksytty CSP ja tietoturvaratkaisu sen nimenomaisesti mahdollistavat; muutoin tee ehdotus ADR-muutoksesta ja toteuta turvallinen ei-JS-vaihtoehto.

**Turvarajat eivät muutu UI-projektissa:**

- Ei `docker -p`, Dockerin julkaisemia portteja, Tailscale Funnelia, Tailscale SSH:ta, yleistä SSH-palvelinta tai julkista Internet-palvelua.
- Tailscale Serve ja nykyinen HTTPS-origini, täsmälliset Host/Origin/Sec-Fetch-Site-vartijat ja sallittujen käyttäjien tarkistus eivät saa heikentyä. Ei suoraa TCP-palvelinta 127.0.0.1:een vain siksi, että se helpottaa kehitystä.
- Gateway on **postinkantaja**, ei hyväksyjä, työnjohtaja, päätöspalvelu, verkkoasiakas tai salaisuuksien lukija. Säilytä `PrivateNetwork`, minimioikeudet ja `InaccessiblePaths=/srv/aiops/data`.
- Ei yksityisen hyväksyjän avaimen lukua, pyytämistä tai esittämistä; ei pilvi-API-avaimia UI:n, JS:n, repositorion tai lokien puolelle. Ei työnantajan dataa Ilmariin.
- WebAuthn-allekirjoitus ja dispatcherin validointi säilyvät ennallaan. Älä tee ohituspolkua, automaattista hyväksyntää tai yhdellä GET-kutsulla muuttuvaa toimintoa.
- Ei GPU-kutsuja tai mallien latauksia käyttöliittymäprosessista. Dispatcher vastaa GPU:n ja ajojen valvonnasta. Pilvikutsuille 10 €/vko koodin valvoma budjetti, ei UI:n arvioon perustuva raja.
- Ei uutta pääsyä `public/private/restricted`-hakemistoihin. `restricted`-tuloksista vain nykyisen politiikan sallimat metatiedot. Ravintopolun yksityisille koosteille ei automaattista jakelua tai pilvi-interpretaatiota.
- Ei käyttäjän tuomaa HTML:ää DOMiin (`innerHTML`), ei `eval`ia, ei dynaamisia etäskriptejä, ei CDN-riippuvuuksia. Linkit URL-skeeman sallittujen listan mukaan. Näytä myös virhetilat turvallisesti escapettuina.
- Ei pysyvää selaimen välimuistia arkaluonteisille tiedoille, ei service worker -offline-tallennusta ilman erillistä hyväksyntää. Ei telemetriaa kolmannelle osapuolelle.
- Jos luot erillisen palvelun, määrittele sen oma palvelukäyttäjä, oikeudet, sokettipääsy, systemd-kovennus ja miten liikenne turvallisesti saavuttaa sen **nykyisen** Serven kautta. Tämä kuuluu hyväksyttävään arkkitehtuuripäätökseen; älä arvaa C1–C5:tä hiljaisesti.

## 8. Työnjako ja vaiheistus — tee mahdollisimman valmis ilman turvarajojen rikkomista

Älä tee yhtä hallitsematonta muutosta. Jaa toteutus tarkistettaviin, yksikäsitteisiin osiin ja tee ensin turvallinen kokonaisuus:

**Vaihe 0: tarkastus ja suunnittelu.** Inventoi nykyiset reitit ja tiedostot. Tee `docs/valmistelu/ilmari-hub-ui.md`, jossa on näkymäkartta, käyttäjäpolut, visuaalisen järjestelmän tokenit, datasopimus ja tarkat integraatiorajat. Nosta esiin vaaditut päätökset etenkin `ilmari-ready` C1, C2, C3, C4, C5 sekä keskustelun V1-raja. Tee ADR-ehdotus **vain jos** toteutus todella muuttaa sitovaa ratkaisua; älä merkitse ehdotusta hyväksytyksi.

**Vaihe 1: aidosti käyttökelpoinen lukevan selaimen kokonaisuus.** Toteuta nykyisen päätöksen mukaan turvallinen ajotulosten listaus ja yksityiskohtasivut, niiden tyhjät/virhetilat ja testit. Hyödynnä `MUODOT.md`-sopimusta. Julkaisuvienti toteutetaan tarvittaessa erillisenä rajattuna osana hyväksytyn suunnitelman mukaan, ei lukuoikeutena raakahakemistoon. Jos puuttuva C1/C3-päätös estää palvelun kytkennän, toteuta ja testaa komponentit sekä lukija erillään ja nimeä käyttöönottoblokkeri; älä avaa porttia ratkaisuksi.

**Vaihe 2: valmis yhtenäinen UI-kuori ja neljä skiniä.** Toteuta kaikki navigointisivut, responsiiviset layoutit, teeman vaihto, kortit, kaaviokomponentit ja kuormitus-/virhetilat. Linkitä nykyisiin oikeasti toimiviin `/ilmari`-, työn ja WebAuthn-sivuihin niiden olemassa olevien reittien kautta. Muut toiminnallisuudet ovat rehellisesti rajattuja ja ei-aktiivisia, eivät toimivia nappeja ilman toteutusta. Pidä käyttöoikeus- ja CSP-muutokset erillään.

**Vaihe 3: sovelluskorttien turvallinen lukusopimus.** Toteuta skeeman validaattori ja testit **eristettyä testijulkaisua** vasten. Tee UI kaikille neljälle sovellustyypille; oikeiden tietojen julkaisu vain erikseen hyväksytyistä lähteistä ja käyttöoikeuksista. UniCafen verkkohaku ja Jarvis-yhteys pysyvät pois päältä, kunnes niille on suunniteltu oma rajattu tietokanava. Ravintopolun henkilökohtaisen datan integrointi vaatii erillisen tietosuojapäätöksen.

**Vaihe 4: keskustelun aktivointi myöhemmin.** Tee visuaalisesti valmis keskustelusivu jo vaiheessa 2, mutta aktivoi lähetys, istunnot, mallinvalinta ja agenttityökalut vasta niiden hyväksytyn ADR:n ja testatun backendin jälkeen. UI ei koskaan itse luo hyväksyntävaltaa eikä ohita dataluokittelua.

Jos käyttäjä haluaa "valmiin UI:n" nyt, tee **todella valmis UI/UX kaikille näkymille** sekä oikea kytkentä niihin toimintoihin, jotka ovat sallittuja ja olemassa. Älä jätä visuaalista toteutusta kesken vain siksi, että jokin myöhempi taustapalvelu puuttuu; näytä sen tila ymmärrettävästi. Älä myöskään väitä keskeneräistä backendia valmiiksi.

## 9. Testaus — hyväksytty ja kielletty suunta

Kirjoita vähintään seuraavat automaattiset testit soveltuvin osin:

- Neljän skinin tokenien kattavuus; vaihtuminen kaikissa sivutyypeissä; oletus Arctic Command; tuntematon skin palautuu turvallisesti oletukseen; ei puutteellisia värejä.
- Responsiivisuus 320, 375, 412, 768, 1024 ja 1440 px; ei koko sivun vaakavieritystä; raporttien pitkät rivit käsitellään erikseen.
- Näppäimistönavigointi, näkyvä focus, `aria`/labelit, kontrastit, `prefers-reduced-motion`, 200 % zoomaus, kosketusalueet.
- Koti toimii, vaikka yksi tai kaikki sovelluskortit puuttuvat, ovat vanhoja tai sisältävät virheen.
- Raporttilukija torjuu `..`, absoluuttiset polut, symlinkit, hakemistojen vaihtokilpailut, poikkeavat ajotunnukset, liian suuret ja virheelliset JSON/JSONL-syötteet, erikoistiedostot ja haitallisen HTML:n; sallittu normaali raportti näkyy oikein.
- XSS-/HTML-injektio testattuna korteissa, raportin tekstissä ja ulkoisissa päivityksissä.
- Olemassa olevien GET/POST-, Tailscale-identiteetti-, Origin-, Host-, Sec-Fetch-Site-, CSP-, WebAuthn- ja politiikkatestien regressio.
- Ilman oikeuksia → 403; eri alkuperästä lähetetty POST → 403; väärä polku → turvallinen hylkäys; WebAuthn-väärennös → dispatcher hylkää. Ei uusia kirjoitusreittejä pelkkien korttien takia.
- Terveysdata ei lähde selaimesta ulkoiseen rajapintaan; ei kolmannen osapuolen verkkopyyntöjä eikä piilotettuja automaattisia sovellushakuja.
- Tyhjät tilat, vanhentuneen datan ilmoitus, kellon aikavyöhyke Europe/Helsinki, todellisen lähteen puuttuminen ja virheelliset syötteet.

Jos ympäristössä voi ajaa selaintestejä, tee Playwright-/Chromium-savukokeet ilman tuotantoyhteyksiä. Ota neljästä skinistä työpöytä- ja mobiilikuvat, vertaa luettavuutta ja korjaa löydetyt ongelmat. Käytä tarvittaessa vain testifixtureitä, jotka on merkitty esimerkkidataksi. Älä lisää turhia riippuvuuksia vain kuvankaappausta varten.

Aja ennen toimitusta `uv run pytest -q`; jos muutat Bash-skriptejä, aja `bash -n` ja `shellcheck`. Vertaa tuloksia **todelliseen nykyiseen haaraan**, älä lukitse 13.10. historiallista testimäärää pysyväksi totuudeksi. Näytä suoritetut komennot, testitulokset, ohitukset ja mahdolliset ympäristön rajoitteet; älä raportoi testaamattomia asioita läpäistyiksi. Pidä ainakin yksi riippumaton käsin kirjoitettu testitotuus, ja testaa sekä onnistuminen että epäonnistuminen.

## 10. Konkreettiset toimitettavat tiedostot

Toteutus ja repo määräävät lopulliset nimet, mutta toimita vähintään:

1. Oikeat UI-sivut/komponentit ja yhteinen navigaatio sekä responsiiviset tyylit.
2. Kaikki neljä valmista, testattua skiniä; Arctic Command oletuksena; tokenien dokumentaatio sekä teemanvalitsin.
3. Ajot ja raportit -osion todellinen vain luku -toteutus siinä laajuudessa kuin nykyarkkitehtuuri ja päätökset sallivat.
4. Koti-, Keskustelu-, Hyväksynnät-, Sovellukset-, Ideat/Projektit-, Järjestelmä- ja Asetukset-näkymät; turvallinen rajaus tuleviin toimintoihin.
5. Ravintopolun kaaviokomponentti, UniCafe-listakomponentti, kolmen idean esityskomponentti ja Jarvis-päivityssyöte — kaikki myös puuttuvan lähteen tilassa.
6. Tiukasti validoitu ehdotus sovelluskorttien julkaisusopimukseksi, mutta ei luvattomia uusia tietoyhteyksiä.
7. Kattavat yksikkö-, integraatio-, tietoturva- ja mahdollisuuksien mukaan selaintestit.
8. `docs/valmistelu/ilmari-hub-ui.md` tai vastaava kokonainen UI-määrittely, käyttöohje, puuttuvien backendien rajat ja myöhempi integraatiopolku.
9. Tarvittavat ADR-**ehdotukset**, jos verkko-, CSP-, käyttäjä-, palvelu- tai tietovirta-arkkitehtuuri muuttuu. Älä hyväksy niitä omin päin.
10. Päivitetty `docs/TILANNE.md` **kokonaisena samassa toimituksessa** ajantasaisine oikeine havaintoineen. `docs/muutosloki.md` vain toteutuneista isäntämuutoksista, joita ei tässä Codex-ympäristössä saa väittää tehdyiksi.

Ei testidataksi naamioituja tosielämän henkilökohtaisia tietoja, ei salaisuuksia eikä koneelta luettuja avaimia. Älä poista nykyisiä hyväksyntä- tai ohjaustoimintoja vain UI-uudistuksen vuoksi.

## 11. Työtapa, PR ja asennus

1. Aloita tiiviillä nykytilataulukolla ja toteutuksen selkeällä vaihejaolla. Sen jälkeen **toteuta**, älä jää vain suunnitteluun.
2. Noudata repon ajantasaisia `AGENTS.md`- ja `TILANNE.md`-työnjakosääntöjä. Elias on aiemmassa tilannekuvassa varannut itselleen commitit, pushit, PR-toimet ja asennukset: **älä tee niitä ilman nimenomaista valtuutusta**. Valmistele tarkistettava muutoshaara/diff ja täydellinen PR-kuvaus; jos Codex-istunnolle on erikseen annettu PR:n luontivaltuus, käytä PR:ää, ei koskaan suoraa pushia mainiin.
3. Älä tee isäntäkoneeseen muutoksia. Erityisesti älä muuta UFW:tä, Serveä, palvelukäyttäjiä, avainten oikeuksia tai systemd-palveluja. Kirjoita mahdolliset tarvittavat muutokset asennusohjeeksi, jossa on ennakkotarkistus, odotettu tulos, muutos, jälkitarkistus ja peruminen.
4. Ennen asennusta anna Eliaksen ajettavat **vain lukevat** tarkistuskomennot ilman `<paikkamerkkejä>` sekä niiden odotetut tulokset. Älä oleta asennettua committia, skeemaversiota tai PR-tilaa tarkistamatta niitä.
5. Asennus tehdään vasta hyväksytyllä ja commitoidulla koodilla projektin sovitulla `sudo scripts/deploy.sh "$(command -v uv)"` -menettelyllä **vain jos** se on sovellettavissa ja nykyisen deploy-skriptin tarkistus osoittaa muutoksen kuuluvan siihen. Uutta erillistä palvelua ei saa 'vain kokeilla' asentamalla.
6. Älä riko mitään nykyisistä 8a-3d:n puhelinohjaus- tai hyväksyntätesteistä. Muutos kerrallaan, tarvittaessa oma PR/ADR per turvallisuusrajaa koskeva päätös.
7. Anna lopuksi: muuttuneiden tiedostojen lista, käyttäjälle näkyvien ominaisuuksien lista, mikä toimii oikealla datalla, mikä on vielä ei-aktiivinen, turvallisuusarvio, testitulokset, avoimet päätökset, käyttöönoton ennakkotarkistukset ja palautusohje.

## 12. Valmistumisen määritelmä

UI on valmis tämän toimeksiannon puitteissa, kun:

- Arctic Command näyttää viimeistellyltä ja toimii oletuksena kaikilla sivuilla.
- Muut kolme skiniä voidaan vaihtaa ilman päällekkäisiä toteutuksia, ja niiden saavutettavuus on testattu.
- Työpöydän ja puhelimen navigaatio sekä kaikki kahdeksan osion näkymää ovat oikeasti olemassa ja käytettäviä.
- Ajotuloksia voidaan lukea hyväksytyistä turvallisista julkaisuista tai tietojen puuttuessa näkyy ymmärrettävä, oikea tilatieto; lukurajat on testattu.
- Sovellukset-osiossa on uskottavat Ravintopolku-, UniCafe-, Ideat- ja Jarvis-näkymät, mutta mitään niistä ei esitetä yhdistettynä ilman todellista tietolähdettä ja lupaa.
- Olemassa olevat hyväksyntä- ja puhelinohjausreitit toimivat ennallaan, ja keskustelu on **selvästi tuleva ominaisuus**, ellei siihen ole jo erikseen hyväksytty ja asennettu turvallista backendia.
- Käyttöliittymä ei tuo yhtään uutta luvatonta tietovirtaa, oikeutta, verkkoporttia, salaisuutta tai ohituspolkua.
- Testit ja dokumentaatio osoittavat, mikä on toteutettu, mikä on suunniteltu ja mikä odottaa Eliaksen päätöstä.

**Keskeinen periaate:** Tee Ilmarista visuaalisesti valmis ja nautittava käyttää heti, mutta älä anna ulkoasun väittää, että turvallisuus-, agentti- tai sovellusintegraatiot olisivat olemassa ennen kuin ne on oikeasti rakennettu ja hyväksytty. LLM ehdottaa — koodi päättää.
