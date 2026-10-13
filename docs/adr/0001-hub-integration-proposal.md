# ADR-UI-0001: Ilmari Hubin tuotantoliitäntä nykyisen gatewayn alle

- Tila: **ehdotettu; ei hyväksytty eikä asennettu**.
- Päiväys: 13.10.2026, Europe/Helsinki.
- Soveltamisala: erillinen `Elkkuboi/ilmari_UI`-repo ja sen tuleva liitäntä aiops-alustaan.
- Tämä ei korvaa aiops-repon ADR-0001:tä eikä hyväksy muutoksia ADR-0004:ään, ADR-0010:een tai ADR-0011:een.

## Ongelma ja tausta

Käyttäjä valitsi tyhjän erillisen repon Hubin toteutuspaikaksi. Hub tarvitsee turvallisen tavan näyttää julkaistuja ajotuloksia ja myöhemmin erikseen sallittuja sovelluskoosteita. Käyttäjän 13.10. tilannekuva kertoo, että olemassa oleva Tailscale Serve 443 ohjaa gatewayn Unix-sokettiin ja gatewayn tunnistus-, osoite- ja alkuperävartijat suojaavat nykyisiä toimintoja. Alustan koodi, hyväksyttyjen ADR:ien täydelliset tekstit ja korjattu `apps/ilmari-selain/MUODOT.md` eivät olleet tämän uuden repon lähtötilanteessa.

Standalone-kehityksen valmis lukukomponentti ei yksin ole tuotannon todennettu tunnistusraja. Etenkin `Tailscale-User-Login` on tavallinen HTTP-otsake, jonka paikallinen prosessi voi väärentää, ellei vain luotettu Serve-/gateway-ketju pääse sokettiin. Hub ei saa luoda omaa TCP-polkua tämän oletuksen ohi.

8.10. `ilmari-ready.md` on lähteeksi kopioitu luonnos. Sen B-osan ADR-0011-tila on vanhentunut: 13.10. tilannekuvan mukaan v5 on hyväksytty. Hyväksytyn päätöksen olemassaolo ei todista yleisen agentti-/istuntorajapinnan asennusta.

## Ehdotettu ratkaisu

### Liikenne ja tunnistus

Nykyinen HTTPS-origini ja Serve 443 → gatewayn Unix-soketti säilyvät. Hubin GET-näkymät liitetään aiops-gatewayn nykyisen vartijan alle erikseen tarkastettavana adaptaationa. Nykyinen vartija tarkistaa sallitun käyttäjän, Host-/X-Forwarded-Host-arvon, Funnel-kiellon ja soveltuvat alkuperäehdot **ennen** pyyntöjen päätymistä Hubiin. Hubin liikennettä ei julkaista uutena Serve-kohteena, TCP-porttina tai Funnelina.

Integraation toteutustapa päätetään C3:ssa: joko vartioitu ASGI-mount ja julkaisuluku aiops-repon dokumentoiduilla rajauksilla tai gatewayn rajattu välitys erilliseen suojattuun Unix-sokettiin. Jälkimmäinen tarvitsee täsmällisen soketin omistaja-/hakemisto-/ryhmämallin ja gatewayn pääsyn siihen. Kaikki ulkoa saapuvat identiteettiotsakkeet poistetaan tai korvataan luotetussa rajassa; erillinen prosessi ei ota niitä auktoriteettina tuntemattomalta kutsujalta. Nykyisen gatewayn oikeudet eivät laajene raakadataan tai salaisuuksiin.

Hub ei omista hyväksyntävaltaa. Nykyiset `/ilmari`, `/passkey`, `/tyo/ID` ja `/tyo/ID/hyvaksy` ovat aiops-alustan toimintoja. Linkit otetaan käyttöön vain todennettuun olemassa olevaan reittiin; Hub ei kopioi niiden POST-toimintoja eikä lisää uusia ohjaus- tai hyväksyntäreittejä. WebAuthn-sivujen oma tiukka CSP ja dispatcherin allekirjoitustarkistus pysyvät ennallaan.

### Palvelukäyttäjä ja julkaisut

Erillisen prosessin tapauksessa ehdotus on oma `ilmari-ui`-palvelukäyttäjä ja oma vain julkaisulukuun tarkoitettu ryhmä, ilman `aiops`- ja `docker`-ryhmäjäsenyyttä. Nimet ovat ehdotus, eivät luotuja tunnuksia. Julkaisuhakemistoon annetaan vain tarvittava traversal ja luku; omistajaksi jää ihmisen hyväksymä julkaisija, jonka kirjoitusoikeutta UI:lla ei ole.

13.10. tausta-aineiston suunnitteluosassa ehdotettu selaimen `aiops`-ryhmäjäsenyys vaatii uuden tarkastuksen: ryhmä voi nähdä kaikki kolme dataluokkaa ja kirjoittaa kantaan. Pelkkä "vain lukeva sovellus" ei riitä estämään näitä oikeuksia. Vähimmäisoikeuksia ei korvata laajalla ryhmäjäsenyydellä. Lisäksi `/srv/aiops/ilmari`-vanhemman nykyinen 2750-oikeus on tarkistettava: oma julkaisuryhmä ei saa automaattisesti traversal-oikeutta vanhempaan. Ratkaisu voi olla rajattu ACL tai erillinen bind-mount vain julkaisupuulle; siitä päätetään erikseen ja kirjoitetaan täsmällinen palvelumalli ennen asennusta.

Kovennuksen lähtökohta on `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateNetwork=yes`, `RestrictAddressFamilies=AF_UNIX`, `PrivateDevices=yes`, `NoNewPrivileges=yes`, nollattu capability-joukko ja resurssirajat. Koodilla ja julkaisuilla ei ole kirjoitettavia liitoksia. `/srv/aiops/data`, tietokanta, työt, mallit ja credentials-polut ovat saavuttamattomia. RuntimeDirectory saa palvella vain yksilöityä suojattua sokettia. Tähän toimitukseen ei sisälly asennettava systemd-palvelu tai sudo-skripti.

### Ajotulosten sopimus ja vienti

Tuotannon sovittu lähde on `/srv/aiops/ilmari/ajot`, ei kotihakemisto, agentin työkopio tai raakahakemisto. Erillinen julkaisu sisältää vain sallitut `meta.json`, `raportti.md`, `ehdotukset.jsonl`, `sol-tulos.json` ja `luonnos.patch` -tiedostot, jos ne oikeasti syntyvät. Raportti ja diff näytetään escapettuna tekstinä. Solin T/O/V/E on tarkastajan luokitus, ei automaattinen totuus.

Julkaisija ottaa valmistuneesta ajosta rajatun, validoidun snapshotin, kirjoittaa erilliseen valmisteluhakemistoon ja julkaisee kokonaisuuden atomisella uudelleennimeämisellä. UI ei kopioi tiedostoja, muokkaa alkuperäisiä tai kirjoita julkaisuun. Kokorajat, oikeudet ja virhetilat kuuluvat julkaisijan testattuun sopimukseen. Lukijan `dir_fd`/`O_NOFOLLOW`/`O_NONBLOCK`-suojat ovat toinen raja, eivät korvaus luotettavalle julkaisijalle.

Tämän repon lukija toteuttaa rajatun tiedosto- ja JSON/JSONL-turvavalidoinnin ilman väitettä tuotannon semanttisesta skeemasta. MUODOT.md:n puuttuessa meta.json:n tai Sol-tuloksen kenttiä ei pidetä tuotannon kenttinä. Ennen oikean datan kytkentää sovitetaan lähdeformaatti koodin todellisiin kenttiin ja lisätään riippumattomat fixturet. Vienti yöajosta ja `yo_sol.sh`:sta toteutetaan aiops-repon erillisenä tarkistettavana muutoksena.

### Sovelluskortit ja CSP

`ilmari.card.v1` ehdottaa suppeita tietotyyppejä `metric`, `time_series`, `recommendation_list`, `idea_list` ja `update_feed`. Julkaisijat ja kunkin dataluokka hyväksytään palvelimen asetuksissa. Julkaisu ei saa itse ylentää luokkaansa, avata verkkoyhteyttä tai määrätä dynaamista koodia. UI lukee vain erikseen julkaistut yhteenvedot; ei sovellusten sisäisiä kantoja.

Ravintopolun terveystietojen julkaisu tarvitsee erillisen tietosuojapäätöksen. UniCafen päivätty haku vaatii oman rajatun verkkopalvelun, gateway jää verkottomaksi. Jarvis tarvitsee Joonaksen nimenomaisen jakamisluvan ja hyväksytyn tuontikanavan. Ideat ovat hypoteeseja, kunnes lähteet todentavat väitteet.

Hub toimii palvelinrenderöitynä ilman JavaScriptiä. Skinin valinta ja muut esitysmieltymykset kulkevat GET-kyselyparametreina. CSP sallii paikallisen CSS:n ja tarvittavat omat kuvat mutta kieltää skriptit, kehystämisen, objektit, verkkokutsut ja ulkoiset fontit. Ei evästettä, service workeria, pysyvää arkaluonteisen sisällön välimuistia tai telemetriaa. CSP-poikkeusta keskustelun tai teeman vuoksi ei tarvita.

## Avoimet päätökset

| Ilmari-ready-kohta | Tämän toimituksen ratkaisu | Tuotannossa tarvittava päätös |
| --- | --- | --- |
| C1 asema | Käyttäjän valitsema erillinen kehitysrepo | Jakelu-/päivityssuhde aiops-repoon; sen deploy tyhjentää `/opt/aiops`:n |
| C2 oikeudet | Ei palvelukäyttäjää tai isäntämuutosta | Dedikoidut oikeudet, traversal, kovennus ja soketin luottamusraja |
| C3 puhelinreititys | Ei TCP-esikatselua tai suoraa Serve-julkaisua | Nykyisen gatewayn vartioitu mount tai rajattu Unix-sokettivälitys |
| C4 verkko | UI ei tee lähteiden verkkohakuja | UniCafe/tuontipalvelut erillisinä tulevina päätöksinä |
| C5 salaisuudet | UI ei tarvitse tai lue yhtään salaisuutta | Alustan vanhojen credentials-viitteiden ristiriita ratkaistaan aiops-ADR:ssä |
| C6 data | Vain erikseen määritelty julkaisu; oletus ei yhdistetty | Jokainen julkaisija, dataluokka ja yksityisyys hyväksytään erikseen |
| C7 Git-toimet | Tarkistettavat tiedostot ja PR-kuvaus; ei Git-julkaisua | Elias hoitaa commitit, pushin ja PR-toimet taustadokumentin työnjaon mukaan |
| C8 tila | UI ei kirjoita tietokantaa tai pysyvää käyttäjätilaa | Julkaisun säilytys ja varmistus erillisenä päätöksenä tarvittaessa |
| C9 mallit | Keskustelu/mallinvalinta ei aktiivinen | Hyväksytty ja asennettu agenttirajapinta sekä dataluokkapolitiikka |
| C10 imaget | Ei tuotantoimagea | Erillinen toimitusketjupäätös, jos image myöhemmin tarvitaan |

## Seuraukset ja hyväksymisnäyttö

Valmis UI voidaan kehittää ja testata eristetysti nyt. Tuotannon live-dataa ja käyttäjätunnistusta ei väitetä valmiiksi. Integraation hyväksyminen tarvitsee nykyisen aiops-koodin inventoinnin, MUODOT-yhteensopivuuden testit, gatewayn vartijoiden regressiot, oikein rajatun julkaisuun pääsyn sekä kielteisten oikeus-/symlink-/XSS-/verkkokokeiden näytön.

C2/C3 päätetään ennen host-muutosten komentojen kirjoittamista. Vain tämän ehdotuksen hyväksyntä ei ole deploy-lupa. Mahdollinen asennus tehdään tarkistetusta commitoidusta koodista nykyisten sääntöjen mukaan; nykyistä `scripts/deploy.sh`:ta ei käytetä erillisen repo-palvelun asentamiseen tutkimatta sen soveltuvuutta.

Tämä UI ei muuta SQLite-skeemaa. Nykyisen gatewayn alla myöhemmin liitetyn UI-koodin palautus on sen mountin/adaptaation koodipalautus; aiops-kantaa, budjettikirjanpitoa, hyväksyjäavaimia tai ajotuloksia ei palauteta tai poisteta UI:n vuoksi. Tuotannon täsmällinen palvelu-/konfiguraatiopalautus kirjoitetaan vasta valitun integraation rinnalle.
