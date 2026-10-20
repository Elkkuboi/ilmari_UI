# ilmari_UI: tämän repositorion tilanne 20.10.2026

## Päivitys 20.10.2026: sääntöpaneeli (aiops ADR-0017, ADR-0013 tarkennus 2026-10-20)

- Uusi sivu `/hub/saannot` ("Säännöt" navigaatiossa) näyttää aiopsin peruskirjan `docs/saannot.md` vain luku -tilassa.
  aiopsin `deploy.sh` julkaisee sen asennetusta commitista hakemistoon `/srv/aiops/ilmari/peruskirja` (`saannot.md` ja
  `meta.json`, muoto `aiops-peruskirja-v1`, root:ilmari-julkaisu).
- `src/ilmari_ui/peruskirja.py`: lukija käyttää ajolukijan polkukävelyä (dir_fd, O_NOFOLLOW) ja hyväksyy tuotannossa
  vain rootin omistaman hakemiston ja tiedostot, tavalliset tiedostot yhdellä linkillä, kokorajat (64 KiB / 4 KiB) ja
  meta.json:n tarkan muodon. saannot.md:n SHA-256:n ja koon on täsmättävä metaan, joten kesken jäänyt julkaisu näkyy
  virheenä eikä sekaversiona. Rajattu Markdown (otsikot, listat yhdellä sisennystasolla, taulukot, koodi, lainaus,
  vaakaviiva, lihavointi ja tekstinsisäinen koodi) tuottaa tietorakenteen; sivupohja koodaa kaiken, eikä `safe`-polkua ole.
- Konfiguraatio: valinnainen `[hub] peruskirja` (oletus `/srv/aiops/ilmari/peruskirja`), joten työaseman `hub.toml`
  ei muutu. Kehitystila: `--peruskirja-dir`; tuotannossa (`--config`) valitsin hylätään.
- Palvelutiedosto: `BindReadOnlyPaths=-/srv/aiops/ilmari/peruskirja` (miinus: puuttuva hakemisto ei estä käynnistystä).
- Esimerkkitila: synteettinen `demo/peruskirja`, merkitty sivulla.
- Testit Clauden ympäristössä: rootina 585 passed, 65 skipped; tavallisena käyttäjänä 582 passed, 68 skipped (kolme
  omistajatestiä vaatii rootin). Uudet: `tests/test_peruskirja.py` sekä lisäykset `test_config.py`, `test_cli.py` ja
  `test_unit_file.py`. Mutaatiokoe 16/16 kiinni (yksi niistä jumittaa testin aikarajaan asti, mikä on myös kiinni).
- Ei vielä asennettu eikä todettu työasemalla; isäntämuutokset kirjataan aiops-repon muutoslokiin.


## Päivitys 15.10.2026: asennettava sovellus ja MUODOT-sovitin

- Hub on asennettavissa sovellukseksi (PWA): `static/manifest.webmanifest` (start_url `/hub`, scope `/`, standalone),
  kuvakkeet 192/512 ja maskable 512, CSP:hen `manifest-src 'self'`. Hubissa ei ole service workeria eikä JavaScriptiä:
  sovellus tarvitsee yhteyden työasemaan. Scope `/` pitää myös gatewayn sivut (hyväksynnät, `/ilmari`) samassa ikkunassa.
- MUODOT-sovitin `src/ilmari_ui/muodot.py`: ajon otsikko (suunnitelma tai painopiste), ajat (meta.json:n alku on
  Helsingin aikaa ilman aikavyöhykettä; loppu = alku + lopetus.kesto_s), malli, taso, lopetus, repo, ehdotukset ja Solin
  tuomiot rivinumeron mukaan (aiops MUODOT.md kohta 8). Oikealla 6.10. ajolla todettu: `virhe` on virheettömässä ajossa
  merkkijono "None" (ilmari_yo.py kirjoittaa `str(virhe)`), ja puuttuva sol-tulos, ehdotukset tai patch ei ole virhe.
- Testit Clauden ympäristössä: 528 passed, 65 skipped.

## Päivitys 14.10.2026: tuotantoliitäntä (aiops ADR-0013)

- Päätös: aiops-repon ADR-0013 hyväksyttiin 14.10.2026 (PR #13). Hub saa oman käyttäjän ja Serve-polun `/hub`, eikä
  gateway muutu. ADR-UI-0001 on merkitty korvatuksi, ja `docs/ilmari-ready.md` on nyt kopio aiops-repon ajantasaisesta
  versiosta.
- Julkaisu: aiops-repon `scripts/julkaise.py` (PR #27) kopioi yöajon sallitut tiedostot hakemistoon
  `/srv/aiops/ilmari/ajot` (ryhmä ilmari-julkaisu). 16 ajoa julkaistiin työasemalla 14.10.2026, ja Hubin lukija
  (`runs.py`) luki julkaisun virheittä Clauden konttisimulaatiossa.
- Serve-koe työasemalla 14.10.2026 (`/hub-koe`, poistettu kokeen jälkeen): Serve poistaa polun etuliitteen, korvaa
  X-Forwarded-Hostin ja Tailscale-User-Loginin, poistaa asiakkaan Tailscale-Funnel-Requestin ja päästää
  X-Forwarded-Prefixin läpi. `/hub-koex` meni gatewaylle.
- Tässä muutoksessa: tuotantotila (`--config`, `src/ilmari_ui/config.py`), gatewayn sääntöjen mukainen vartija ja
  etuliitteen palautus (`app.py`), palvelutiedosto, konfiguraatiomalli, asennusskripti ja testit
  (`tests/test_production.py`, `test_config.py`, `test_unit_file.py`, `test_asenna.py`, `test_cli.py`).
- Testit Clauden ympäristössä: 506 passed, 65 skipped (selaintestit ilman Playwrightia). Palvelutiedosto jäsentyy
  systemd 255:llä (`systemd-analyze verify`).
- Seuraavaksi: isäntämuutokset aiops-repon muutoslokiin (käyttäjä ilmari-hub, `/etc/ilmari-hub/hub.toml`, asennus,
  palvelu, Serve-polku `/hub`) ja puhelinkoe. Sen jälkeen MUODOT-sovitin (ajon kenttien ja Solin tuomioiden esitys).

Tämä alkuosa koskee käyttäjän nimenomaisesti tilaamaa Ilmari Hub -käyttöliittymän toteutusta erilliseen `Elkkuboi/ilmari_UI`-repositorioon. Alempana oleva aiops-tilannekuva on käyttäjän toimittama alkuperäinen tausta-aineisto kokonaisena. Sen isäntä-, Git-, PR-, testi- ja GPU-havainnot eivät ole tämän pilviympäristön mittauksia. Historiaa ei ole muutettu.

## Tässä ympäristössä havaittu ja valmisteltu

- Lähtötilanne: tarkoituksella tyhjä Git-repo, ei aiops-alustan lähdekoodia, hyväksyttyjä ADR-tiedostoja, gatewayta tai `apps/ilmari-selain/MUODOT.md`:tä.
- Käyttäjän korjaus määrittelee tämän tehtävän koodaustyöksi. Erillinen UI-repo on valittu kehityksen toimituspaikaksi (C1). Tämä ei hyväksy tuotantopalvelun käyttäjää, reititystä tai asennustapaa.
- Toteutuksen kohde: suomenkielinen palvelinrenderöity FastAPI/Jinja2 Hub, Python 3.12 ja uv, kahdeksan pääosiota, neljä yhteistä tokenipohjaista skiniä, GET-pohjaiset esitysmieltymykset sekä vain lukevat julkaisut.
- Arctic Command on oletus. Slate Electric, Nordic Paper ja Aurora Lab käyttävät samaa HTML:ää ja yhteistä CSS:ää. Hub ei tarvitse JavaScriptiä, istuntoevästettä, ulkoista fonttia tai CDN:ää.
- Ajotulosten lukija on eristetty komponentti, jonka tavoite on erikseen hyväksytty julkaisuhakemisto `/srv/aiops/ilmari/ajot`. Lukija tarkastaa JSON/JSONL:n turvallisen rakenteen; MUODOT-semanttiikka täytyy sovittaa ennen tuotannon kenttien tulkintaa. Se ei anna lukuoikeutta `~/ilmari-yo`:hon, työkopioon, tietokantaan tai `/srv/aiops/data`:an.
- Sovelluskortit käyttävät tämän repon ehdotettua `ilmari.card.v1`-julkaisusopimusta ja julkaisijan palvelinpuolen rajoja. Korttisopimus ei ole aiops-alustan olemassa oleva API tai hyväksytty tietovirta.
- Keskustelu, mallin vaihto, todelliset hyväksyntälistat, GPU-/budjettimittarit ja ulkoiset sovellusyhteydet pysyvät rehellisesti ei-aktiivisina, kun todennettua rajapintaa ei ole. Mahdolliset esimerkkijulkaisut ovat kehityksen esimerkkidataa.
- Tuotantoliitännän ADR on **ehdotus**. C2 (käyttäjä/oikeudet) ja C3 (yhteys nykyiseen gatewayhin) ovat avoimet. Tailscale-identiteettiotsake yksin ei todenna käyttäjää; luottamus vaatii nykyisen gatewayn vartijan ja rajatun Unix-sokettiketjun.
- Isäntäkoneen muutoksia, deployta, sudo-komentoja, Serve-/UFW-muutoksia tai systemd-asennusta ei ole tehty. `docs/muutosloki.md`:tä ei luoda kuvitteellisen isäntäasennuksen kirjaamiseksi.
- GitHub-toimitus 13.10.2026: käyttäjän jatkopyynnön perusteella 64 tiedostoa commitoitiin ja pushattiin `ilmari-hub`-haaralle. Toteutuksen commit on `b65ae29e403278aecec96f4cdc25894be9099b4b`. GitHubin `git ls-remote --symref origin HEAD` vahvisti saman SHA:n ja `ilmari-hub`-oletushaaran. Etärepo ei enää ole tyhjä. Ennen ensimmäistä pushia GitHubissa ei ollut yhtään haaraa, joten PR:n vertailulle ei ollut perushaaraa. Aiops-repoon tai työasemaan ei tehty muutoksia.

## Testien ajantasainen näyttö

`UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --group browser pytest -q` → **472 passed**, 0 failed, 0 skipped (128,48 s). Näistä 65 on Chromium-selaintarkistuksia. Yksi Starlette/TestClientin httpx-deprekaatiovaroitus; ei testivirheitä.

Koti testattiin kaikilla neljällä skinillä ja leveyksillä 320/375/412/768/1024/1440 px. Kaikki 13 näkymää testattiin 320/768/1440 px:n leveyksillä. Lisäksi näppäimistön hyppylinkki, fokus, kaavion puuttuvan päivän taulukko, 44 px:n kosketuskohteet ja 200 % zoomausta vastaava 720 CSS-pikselin asettelu tarkistettiin. Tämä ei ole täydellinen WCAG-sertifiointi tai aiops-alustan regressioajo. Jokaisen skinin teksti-/tila-/fokus-/kaaviokontrastit sekä tokenien kattavuus läpäisivät 123 tarkistusta.

Neljä työpöytä- ja neljä puhelinkuvaa ovat ohitetussa `artifacts/screenshots/`-hakemistossa. Testiselain ei tehnyt kolmannen osapuolen verkkopyyntöjä, eikä HTTP-palvelinporttia avattu.

Todellinen Unix-soketin käynnistys palautti Koti- ja raporttipyynnöissä 200 ja väärällä Hostilla 403; hakemisto 0700, soketti 0600. Oikea subprocess-testi vahvisti SIGTERM-lopetuksen, oman soketin poiston ja uudelleenkäynnistyksen samalla polulla. `uv build` onnistui; erilliseen hakemistoon asennetusta wheelistä toimivat Koti, Ravintopolku ja CSS, ja paketti sisältää 13 sivupohjaa, 3 paikallista resurssia ja 19 synteettistä julkaisutiedostoa.

Pilviympäristön `install_script` ja `start_skill` tallennettiin asetusten luonnokseen. Asennusohjeen frozen-sync, `bash -n` ja ShellCheck läpäisivät. Tallennus ei julkaissut ympäristöä; uusi tehtävä ei ole vielä todentanut snapshotin palautusta. Ei uusia verkkodomaineja tai salaisuusvaatimuksia.

## Seuraava erillinen integraatiotyö

1. Tarkista aiops-repon todellinen kärki, PR #22:n ja MUODOT-PR:n yhdistyminen sekä korjattu MUODOT.md ja hyväksytyt ADR:t vain lukevilla tarkistuksilla.
2. Hyväksy C2/C3 sekä valittu gatewayn alla toimiva lukurajaus; säilytä nykyiset `/ilmari`, `/passkey` ja työkohtaiset WebAuthn-sivut ennallaan.
3. Sovita ajolukusopimus julkaistuihin tiedostoihin ja suunnittele erillinen atominen vienti. Ei suoraa raakadata- tai työkopioliitosta.
4. Hyväksy sovellusten julkaisijat ja dataluokat erikseen. Ravintopolun terveystiedot, UniCafen verkkohaku ja Joonaksen jakamislupa ovat omat päätöksensä.
5. Valmistele tarkistetusta, commitoidusta koodista asennus- ja palautusohje. Nykyinen aiops-deploy ei sellaisenaan asenna tätä erillistä repo-palvelua.

Tarkempi suunnitelma: [UI-määrittely](valmistelu/ilmari-hub-ui.md), [ADR-ehdotus](adr/0001-hub-integration-proposal.md), [integraation ennakkotarkistukset](INTEGRAATIO.md) ja [valmis PR-kuvauspohja](PR-KUVAUS.md). `ilmari-ready.md` säilytetään kokonaisena 8.10. taustadokumenttina; sen B-osan vanhaa ADR-0011-luonnostilaa ei tulkita nykytilaksi.

---

# Käyttäjän toimittama aiops-tilannekuva – alkuperäinen kokonaisena

# aiops: tilannekuva 13.10.2026 (8a-3d valmis ja asennettu 58f5443; ADR-0011 hyväksytty; T1 yöajossa live-testattu, PR #22; seuraavaksi selaimen määrittely ja PR #13)

**Päivitys 13.10.2026 klo 01 (lue tämä ensin):** istunto 11.–13.10. vei vaiheen 8a-3d (puhelinohjaus) loppuun, hyväksyi ADR-0011:n ja
rakensi T1:n (Ilmari kirjoittaa luonnosta) yöajoon. Alla on ajantasainen tila; sitä vanhemmat kohdat ovat historiaa.
- **Yhdistetyt PR:t:** #17 (muutosloki 8a-3d, `a5f704f`), #18 (yöajon ohjeluku, tilatiedosto ja korjaukset, `8f6cdc3`), #19 (Pysäytä omaan
  tuntirajaansa, `58f5443`), #20 (ADR-0010/0011: 8a-3d valmis, muutosloki asennuksesta, `896e0d9`) ja #21 (ADR-0011 hyväksytty, versio 5,
  `11746d6`). **Avoimet:** #22 (`vaihe-t1-yoajo`, kärki `a47515d`: T1; live-koe tehty 13.10., yhdistämiskomento annettu), MUODOT-PR
  (`apps-ilmari-selain-muodot`: Ilmarin luonnos ja Clauden korjaukset kahtena committina; luotu tai luomatta, tarkista `gh pr list`),
  #15 (ML-ajoympäristö) ja #13 (Ilmari-ready). Tarkista ensin `git --no-pager log --oneline -5` ja `gh pr list`.
- **Asennus:** `/opt/aiops/DEPLOYED` = `58f5443 2026-10-12T23:40:12+03:00` (PR #19: pysäytysten oma tuntiraja, sivun ohjeteksti; deploy ajettiin
  vahingossa kahdesti peräkkäin, vaaraton). Kanta skeema 4; rivit jobs 24, events 101, approvals 9, passkey_candidates 1, agentti_ohjeet 5.
- **Isäntämuutos 12.10.:** `/srv/aiops/ilmari` (2750 elias:aiops) ja `/etc/aiops/aiops.toml`:iin `[gateway.ilmari] tilatiedosto =
  "/srv/aiops/ilmari/tila.json"`; varmuuskopio `/etc/aiops/aiops.toml.ennen-8a3d-ilmari` (640 root:aiops); gateway käynnistetty uudelleen.
  Todennettu oikean gatewayn kautta (yöajon kirjoittama koetila näkyi sivulla). Muutoslokissa.
- **Todennettu:** GET/POST-kokeet sokettiin (200 tunnuksella, 403 ilman, POST ilman Originia 403); puhelinkoe 12.10. (lisäohje → malli
  kirjasi ehdotuksen otsikolla PUHELIN; Ohita päätti pätkän; Pysäytä → exit 4 ja tilatiedostossa `pysaytetty`; viive 1–6 s; toinen Ohita oli
  vahinkopainallus vanhentuneelta sivulta → toistosuoja 60 s); katselmointiyöajo 12.10. (Q6, 395 askelta, 8 ehdotusta; Sol 2 T, 2 O, 4 E,
  0,095 €; kaksi T:tä korjattu); T1-live-koe 13.10. klo 00.19 (Ilmari kirjoitti `apps/ilmari-selain/MUODOT.md` ja `SUUNNITELMA.md`).
- **Testit:** mainissa (`11746d6`) 1661 passed, 1 skipped; T1-haarassa (`a47515d`) **1711 passed, 1 skipped** (tavallisena käyttäjänä).
- **Päätökset 12.–13.10. (Elias):** Pysäytä pysäyttää vain yöajon (Sol tarkastaa kertyneet, sarja jatkaa); lisäohje on voimassa ajon loppuun;
  pysäytyksillä oma tuntiraja; ADR-0011 hyväksytty; **T1 väliaikaisesti yöajon työkopioon** (tie A, poikkeama päätöksestä 6 kirjattu);
  ensimmäinen T1-kohde on erillinen, vain lukeva selain (ajot, raportit, ehdotukset); **selain lukee julkaisuhakemistosta
  `/srv/aiops/ilmari/ajot`** (yöajo kopioi tulokset, selain omana käyttäjänään ilman pääsyä kotihakemistoon; 13.10.).
- **T1-luonnosten tarkistus 13.10.:** MUODOT.md hyvä (noin 60 rivinumeroa ja kenttää täsmäsi; 4 korjausta). SUUNNITELMA.md ei kelpaa
  sellaisenaan: ristiriidat omaan MUODOT.md:hen (meta.json:n kentät `loppu`, `tila`, `sol_tulos` puuttuvat; Sol-tuloksen rakenne väärin) ja
  puuttuvat turvarajat (käyttäjä ja oikeudet, tunnistus Tailscale-tunnuksella, polkuparametrin tarkistus, kokorajat).
- **Repon `docs/TILANNE.md`** on yhä 9.10. versio; vie tämä tiedosto repoon omalla haarallaan ja PR:llä.

**11.10. klo 23 (historia):** pino (PR #16) ja puhelinohjaus (PR #14) yhdistettiin ja #14 asennettiin (`b00ae39`, skeema 4); palautuspiste
`~/aiops-ennen-8a3d.sqlite` (SHA-256 `ae4150d8…a059c`, säilytä). Yksityiskohdat muutoslokissa (11.10.).

**Lue ensin (8.10.2026, ilta):** tämä päivitys kattaa 7.10. jälkeisen työn. Yksityiskohdat ovat kohdassa "Istunto
8.10.2026" ja ajantasainen git- ja isäntätila kohdassa "Nykyinen lähtötila". Aiempi 7.10.-yhteenveto on alla
sellaisenaan, ja ohitettu tieto on korjattu tai merkitty.

- **Valmista ja ajettua 8.10.:** vaiheet 1–7 ja 8a-1 (kuten ennen) sekä **8b-1:n koodi**: budjettiydin
  `src/aiops/budget.py` (viikkokatto 10 €, kirjanpito `/srv/aiops/valittaja`), Sol-tarkastaja `scripts/sol_tarkasta.py` ja
  kääre `scripts/yo_sol.sh` (yöajo ja Sol-tarkastus yhdellä komennolla). Sol-tarkastaja on **isäntäskripti, jota ajetaan
  sudolla; välittäjäpalvelua (systemd) ja agenttikytkentää (8a-3a/b) ei ole**. Asennettu palvelukoodi on yhä `58cd1eb`;
  mitään palvelua ei ole muutettu.
- **Sol tarkasti Qwenin ehdotukset ja näytti toimivan:** 24 ehdotuksesta (q6, ajattelu pois) T 3–4, O 3, V 12–13, E 5
  (medium vs high: 22/24 samat). Ainoat hyödylliset löydöt olivat `TILANNE.md`:n vanhentuneet rivit ja kaksi pientä
  `gpukoe.py`-korjausta, jotka on tehty. Qwen hakee ja viittaa tarkasti mutta tulkitsee usein väärin (13–14/24 väärä väite).
- **OpenAI:** Elias päätti 8.10. käyttää API:a ilman EU-datasijaintia (`api.openai.com`, `store: false`). Sol-tarkastajan
  päättely on medium (high eskalointiin on ehdotus, ei päätös). Viikon käyttö 8.10. illalla 0,83 € / 10 €.
- **Mallit:** ISTA:n GSQ-RCO-kvantisoitu `Qwen3.8-27B IQ3_S` (11,8 Gt) on asennettu mittausvalmiiksi (karanteeni → root-kopio,
  `MALLIT["iq3s"]`). Nopeampi kuin Q6 (generointi 94 vs 64 t/s), VRAM 15 GiB; laatua ei ole mitattu. Ajattelun säätö
  (`paattely`, `paattelybudjetti`, `lampotila`) on yöajon suunnitelmassa; kumpaakaan ei ole vielä verrattu Q6:een.
- **Tilanne tätä kirjoitettaessa:** koesarja on ajettu (`~/code/yo_sarja.sh`, 9.10. klo 00.00–02.30, viisi ajoa, Sol-tarkastus jokaisen
  jälkeen); tulokset ovat kohdassa "Koesarjan tulokset". IQ3_S ctx 131 072 näyttää toimivalta; ajattelu vähentää toistoa ja kaksoiskirjauksia mutta
  maksaa 2,8-kertaisen ajan eikä lisää T:tä; näihin ei pidä luottaa ennen ehdotusten lukua, koska kohina on suurta. Sarjan jälkeen HEAD
  on jälleen vapaa. `yo_sarja.sh` on yhä `~/code/`-hakemistossa eikä repossa. IQ3_S 65 536 -ajon tulosta ei ole tarkistettu.
- **Pilvisessioiden PR:t:** #14 (puhelinohjaus) on yhdistetty ja asennettu (ks. päivitys yllä); #15 (ML-ajoympäristö, ADR-0012) ja #13 (Ilmari-ready)
  odottavat; ne on arvioitu 9.10. (ks. "Pilvisessioiden PR:t").

**Tilanne 7.10.2026 (aiempi yhteenveto, osin ohitettu):** vaiheet 1–7 ovat valmiita, ADR-0008 ja ADR-0009 hyväksytty. **Vaihe 8a-1 on tehty:**
Qwen3.8-27B:n painot, llama.cpp-imaget, BF16-GGUF sekä Q4_K_M ja Q6_K on tehty, tarkistettu ja asennettu
root-kopioksi (PR #12 yhdistetty, main `10775e2`). **GPU-pilotti tehty 6.10.:** molemmat kvantisoinnit toimivat
kovennetussa verkottomassa kontissa Unix-soketin kautta; luvut ovat kohdassa "GPU-pilotti ja yöluenta" alla.
**Ilmari 0 (yöluenta, taso T0 eli vain luku) tehty:** paikallinen malli lukee repon kopiota ja kirjaa
ehdotuksia; kolme pitkää ajoa toivat esiin viisi virhettä (työkalun hiljainen katkaisu, kolme silmukan suunnitteluvirhettä
ja katkennut työkalukutsu), jotka korjattiin ja testattiin. **Pätkitetty yöajo (7.10. 00.04–00.14) päättyi noin
yhdeksässä minuutissa, ei kolmessa tunnissa:** neljännessä pätkässä malli tuotti liian pitkän työkalukutsun, jonka JSON
katkesi `max_tokens`-rajaan; llama-server vastasi HTTP 500, ja silmukka tulkitsi sen palvelinvirheeksi (minun virheeni,
korjattu: katkennut kutsu on mallin tulosteen virhe). Ajo kirjasi 9 ehdotusta; tarkistuksessa 4/9 sisälsi virheellisen
väitteen, 3 vertasi suunnitteluluonnosta nykykoodiin ja tulkitsi puuttuvan toteutuksen virheeksi, ja yksi (katon
täyttymisen signalointi) on todellinen aukko ADR-0011:ssä. **ADR-0011 on
luonnoksena** (haara `vaihe-8a2-yoluenta`; Eliaksen päätökset 6.10. kirjattu, hyväksyntä tapahtuu commitilla).
Asennettu koodi on yhä `58cd1eb`; palveluita ei ole muutettu. Agenttikytkentää, puhelinohjausta ja pilvikutsuja
(välittäjä, Sol) ei ole toteutettu. **Vaatimus 6.10.:** johtajan (koordinaattorin) on oltava vaihdettavissa
paikallisen Qwenin ja `gpt-6.1-sol`:n välillä, ja johtajien on hyödynnettävä toisiaan: Sol tarkastaa ja ohjaa,
koodi laukaisee yhteistyön (ADR-0011 kohta 8).

**Työtapa, Eliaksen uusi ohje 6.10.:** Elias hoitaa commitit, pushit, PR-toimet, yhdistämiset,
asennukset ja isäntämuutokset. Avustaja selittää yhden vaiheen kerrallaan, pyytää ennen muutosta
vain lukevan lähtötilan, valmistelee tarkastettavat tiedostot sekä antaa kopioitavat komennot ja
odotetut tulokset. Avustaja tarkistaa saamansa aineiston ja kertoo erikseen omat tarkistuksensa
sekä Eliaksen tulosteilla vahvistetut havainnot. Tämä korvaa aiemman luvan avustajan omille
commiteille. Liitteiden vanhat komennot ovat historiallista aineistoa, eivät uusia suorituspyyntöjä.

**Lisähavainnot 6.10. (historiallinen; main on sen jälkeen `10775e2`):** Eliaksen tulosteessa PR #11 oli yhdistetty, main ja origin/main
olivat tuolloin `5628b20`, ja paikallinen haara `vaihe-8a1-q6k` poistettiin. OpenAI-avain on tallennettu
salattuna systemd-credentialina (`/etc/aiops/credentials/openai.cred`, root:root 0600, 754 tavua).
Sen purku ja mallilistan haku onnistuivat: 133 mallia, `gpt-6.1-sol: True`. Tämä todistaa
avaimen toimivuuden mallilistan haussa, ei generointia, agenttikytkentää tai budjettivalvontaa.
TPM2 on saatavilla (`systemd-creds has-tpm2`: yes); käytettyä salauksen sidontaa ei ole
varmistettu erikseen. Laaja vaihe 8a-2:n vertailumittaus siirretään myöhemmäksi Eliaksen
päätöksen mukaan. Pieni Q4/Q6-koe on tehty 6.10. ja agentin rajapinnan valmistelu on ADR-0011-luonnoksena. ADR-0009:n
käyttöönottoa edeltävä pieni tehtäväsarja säilyy; laajan vertailun siirto ei poista sitä.

**Lähteiden ajantasaisuus:** päivitys perustuu Eliaksen 6.10. toimittamaan TILANNE.md:hen,
keskustelu- ja komentotulosteliitteisiin, mainin `5628b20` Git-arkistoon sekä tämän
istunnon Git-, testi-, PR #12-, ennakkotarkistus-, asennus- ja riippumattomiin tarkistustulosteisiin.
Avustaja tarkisti valmistelukopion; isäntäajot teki Elias. Avustaja ei käyttänyt API-avainta
eikä muuttanut isännän palveluita. Projektin synkronoidut lähdetiedostot voivat olla vanhempia.

**Root-kopio 6.10., valmis:** mainin arkiston Git-tunniste oli
`5628b2083681bc4e2954ed404e674a56a10cdc02`, avustajan laskema SHA-256
`bd59f7e8b0a80d8040a401f69fab7807e7264d01c40e364f3ca11089ba2cb466`
(Elias ei toimittanut erillistä tiivisteriviä vertailuun). Sen pohjalta valmisteltiin
kopiointiskripti, manifesti, 41 uutta testiä ja root-kopio-ohje. Valmistelukopiossa
**802 passed, 1 skipped** (14,95 s); Eliaksen koneella **802 passed, 1 skipped** (14,74 s).
Elias commitoi kuusi tiedostoa haaraan `vaihe-8a1-rootkopio`: `8dcbcae7c0acda584da3ce6ac05570be12e29dce`,
pushasi ja avasi luonnoksen https://github.com/Elkkuboi/aiops-tyoasema/pull/12.
Viimeisin PR-tuloste: OPEN, isDraft true, headRefOid sama kuin ajon commit.
Vain lukeva ennakkotarkistus läpäisi. Elias ajoi root-kopion samasta puhtaasta commitista:
`ASENNUS OK`; mitattu kokonaisaika **1 min 50,207 s** (sisältää sudo-kehotteen).
Kohde `/srv/aiops/models/qwen3.8-27b/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0-gguf-b11430`.
Riippumaton stat vahvisti hakemiston 0:0 / 0755 ja tiedostot 0:0 / 0644;
sha256sum ja nykyinen manifestitarkistin vahvistivat molemmat kopiot:

| Tiedosto | Tavua | SHA-256 |
| --- | ---: | --- |
| qwen3.8-27b-q4-k-m.gguf | 16547400192 | `95151662a26e3667c3ea93fa0a2414097c1b9639a37ee178814acae7454b3920` |
| qwen3.8-27b-q6-k.gguf | 22082529792 | `e45467caef1073ab75792cd3860c6b496685015be0c2a4320f361f980bbe9cca` |

`KAIKKI KUNNOSSA: 2 tiedostoa, 38629929984 tavua`.
Root-kopiota ei ajeta uudelleen olemassa olevaan kohteeseen. PR #12 on yhdistetty 6.10. (merge
`10775e24df0ef5269f10922652d3f551a1080d1f`, 14:27 UTC); dokumentointicommit `df64264` kuului samaan PR:ään.

## GPU-pilotti ja yöluenta (6.–7.10.2026)

Näyttö: Eliaksen isäntäajojen tulosteet ja lokipaketit sekä Clauden valmistelukopiossa tekemät testit ja
tarkistukset. Mittaukset ovat pilottitason (yksi kone, yksi ajo per piste), eivät ADR-0009:n tehtäväsarja.

### GPU-pilotti (`scripts/gpukoe.py`, haara `vaihe-8a1-gpukoe`, commit `2e96629`)

Kontti: sama kovennus kuin dispatcherin töissä (`--network none`, `--read-only`, `--cap-drop ALL`,
`no-new-privileges`, käyttäjä 10001:aiops, malli vain luku -liitoksena), llama.cpp b11430, `-fit off`, `-ngl all`,
`-np 1`, ajattelu pois. Lähtötila: GPU 727 MiB käytössä (työpöytä), ei laskentaprosesseja, ei konttia, ei töitä.

| | Q4_K_M | Q6_K |
| --- | ---: | ---: |
| Tiedosto | 15,41 GiB | 20,57 GiB |
| Generointi `llama-bench`, syvyys 0 / 8 192 / 32 768 (t/s) | 78,8 ± 1,3 / 77,7 / 72,1 | 64,1 ± 0,1 / 62,8 / 59,2 |
| Syötteen käsittely pp512, sama syvyys (t/s) | 3 898 / 3 736 / 2 963 | 3 256 / 3 143 / 2 563 |
| VRAM-huippu bench, syvyys 32 768 (lepo 513 / 522 MiB) | 18 993 MiB | 24 006 MiB |
| VRAM-huippu palvelin ctx 8 192 (lepo 546 / 554 MiB) | 17 036 MiB | 22 000 MiB |
| Mallin lataus (palvelimen loki) | 1,57 s lämmin mmap, 3,11 s suora levyluku (`-lm dio`, 5,3 GB/s) | 9,18 s kylmä mmap (2,4 GB/s) |
| Generointi palvelimessa, lyhyet syötteet (t/s) | 77,2 ja 76,9 | 62,9 ja 63,2 |

- Raja on `memory.total − 2048` = 30 559 MiB (ADR-0006); kumpikin mahtuu. llama.cpp näkee kortilla 32 088 MiB,
  nvidia-smi 32 607 MiB; budjetti lasketaan nvidia-smi:stä.
- Soketti: kääre `sh -c 'umask 007 && exec …'` antoi soketille tilan 0770, ja ryhmän aiops jäsen (Elias) pääsi
  yhteyteen ilman sudoa. Ilman käärettä soketin tilaa kontissa ei mitattu (Pythonin bind ja `sh` antoivat omassa
  ympäristössä umaskilla 022 tilan 0755). ADR-0009:n väite "Docker ei aseta umaskia" on lähteessä; umaskin
  periytymisestä isännän palvelusta ei ole näyttöä.
- Oletukset, jotka muuttaisivat tulosta hiljaa: `--fit` on oletuksena päällä, `-c 0` tarkoittaa mallin 262 144
  tokenia, `-np` ja `--reasoning` ovat automaattisia. Koe asetti ne itse. Palvelimen omat `--tools` ja `--agent`
  (shell ja kirjoitus) ovat oletuksena pois; testi vaatii sen.
- Levyvälimuisti: lämmin lataus (1,57 s) vs kylmä mmap (Q6 9,18 s) vs suora luku (Q4 3,11 s). Kylmän mmap-latauksen
  ja dion vertailu on eri tiedostoilla, joten se on suuntaa antava.
- Suomenkielinen yksittäisvastaus (kaksi kehotetta, lämpötila 0): Q6 kielellisesti siistimpi kuin Q4. Kummallakin
  hyväksyntävaihe tuli väärään kohtaan ja kumpikin oletti tietävänsä "eilisen simulaation" hakematta sitä.
  Yksittäinen vastaus ei siis riitä; mitattava on silmukka.
- Skripti: `tila` (vain luku), `bench`, `palvelin`; lähtötarkistukset (GPU vapaa, ei kontteja, ei töitä tiloissa
  `queued`, `awaiting_gpu`, `running`); tulokset `~/gpukoe-tulokset/` (0700); 43 testiä.

### Yöluenta ("Ilmari 0", `scripts/ilmari_yo.py`, haara `vaihe-8a2-yoluenta`)

Taso T0 (ADR-0011 kohta 6): malli saa repon `git archive HEAD` -kopion ja kuusi työkalua (hakemiston listaus, tiedoston
luku, haku, muistiinpano, ehdotuksen kirjaus, lopetus); ei kirjoitusta reposta, ei komentoja, ei verkkoa, ei sudoa,
ei salaisuuksia (estolista, symlinkit ja `..` hylätään; ehdotuksen tiedostojen on oltava olemassa). Rajat ovat
koodissa. Kontti päättyy itse `timeout`-komennolla; lopetus käyttää `sudo -n`.

- **Savukoe (8 askelta, 13 s):** 8/8 työkalukutsua kelvollisia, askel keskimäärin 1,6 s, generointi 55–58 t/s,
  prefix-välimuisti toimii (esim. 114 uutta tokenia 1 321:n sijaan). Löydös: `lue_tiedosto` katkaisi sivun hiljaa
  (otsikko väitti rivit 121–320, toimitettiin 121–219); korjattu rehelliseksi sivutukseksi ja testi vaatii, että
  ketjutetut sivut kattavat jokaisen rivin kerran.
- **Ensimmäinen pitkä ajo (keskeytetty noin askeleella 160):** silmukka toisti saman. Syyt: kehote käski lukemaan
  TILANNE.md:n (noin 28 000 tokenia, täyttää kontekstin yksin), nollausviesti puuttui, kun muistiinpanoja ei ollut,
  ja malli ei tehnyt muistiinpanoja pyytämättä. Korjaus: koodin pitämä lukulista, aina mukana oleva nollausviesti,
  tarkistuspiste (60 % kontekstista; kolme askelta löydösten tallennukseen) ja pysäytys, kun kolme nollausta ei tuota mitään.
- **Toinen pitkä ajo (ctx 65 536):** 85 askelta, 369 s, 15 ehdotusta, 8 muistiinpanoa, 2 virhettä (liian pitkä kenttä),
  VRAM-huippu 25 703 MiB (ennuste 25 838). Ajo päättyi, kun ehdotusraja 15 täyttyi. Tarkistuspiste laukesi askeleella
  23 ja tuotti heti ehdotuksia.
- **Ehdotusten tarkistus repoa vasten:** kaikki 21 tarkistettua rivinumeroviitettä osuivat täsmälleen; 87 % (34/39)
  perustelujen sitaateista oli sanasta sanaan lähteessä; **3/15 ehdotuksessa aineellisesti väärä väite** (ADR-0009
  mainitsee OpenAI:n kulurajan; umaskin periytymistä isännän palvelusta ei ole lähteessä; `vet()` rajaa imaget
  allowlistalla); noin yhdeksän erillistä aihetta, loput päällekkäisiä. Johtopäätös: ehdotukset ovat lähtökohta, eivät totuus.
- **Parannukset ajon jälkeen:** päällekkäisyyssuodatin (otsikon ja tiedostojen perusteella; raja-arvot valittu 15
  ehdotuksen aineistosta, ryhmittelyn teki Claude), kehotteeseen sääntö tarkistaa negatiiviset väitteet haulla,
  pätkitetty suunnitelma etukäteissuostumuksella (kohta alla). 125 testiä; mutaatiokoe: kaikki rikkomukset
  havaitaan.

### Pätkitetty yöajo 7.10. (ajettu ja tarkistettu)

`scripts/ilmari_yo.py suunnitelma config/yoluenta/yo-2026-10-06.toml`: viisi pätkää (ADR-0011-tarkistus, testiaukot,
dokumenttiristiriidat, gateway-turvallisuus, Ilmarin oma koodi), kukin enintään 0,5 h, kokonaisaika enintään 3 h,
suunnitelman SHA-256 `bbe71c13180a…`, ajon repo-commit `ce3988f255c1a60a8afe559e84e2963db7013bd3`. Elias antoi
etukäteissuostumuksen kirjoittamalla "kyllä". Malli q6, ctx 65 536, ajattelu pois; VRAM-huippu 25 967 MiB (lepo 592).

| Pätkä | Syy | Askelia | Kesto | Ehdotuksia | Päällekkäisenä hylätty |
| --- | --- | ---: | ---: | ---: | ---: |
| adr-0011-tarkistus | lopeta | 67 | 223 s | 7 | 1 |
| testiaukot | lopeta | 32 | 59 s | 1 | 0 |
| dokumenttiristiriidat | lopeta | 38 | 162 s | 1 | 1 |
| gateway-turvallisuus | **palvelinvirhe** | 23 | 94 s | 0 | 0 |
| ilmarin-oma-koodi | ei ajettu | | | | |

Yhteensä 160 askelta, 538 s, 9 ehdotusta, 12 muistiinpanoa, 3 lopeta-kutsua; syötettä 3 672 189 ja tulostetta 22 506
tokenia. Dispatcherin työt ennallaan (12/7/5), repon tila ennen ja jälkeen sama.

- **Pysähdyksen syy:** pätkän 4 askeleella 23 llama-server vastasi `HTTP 500: Failed to parse tool call arguments as
  JSON … invalid string`. Malli yritti kirjata pitkän muistiinpanon (edellinen yritys oli hylätty liian pitkänä), ja
  vastaus katkesi `max_tokens`-rajaan 1 500 kesken tekstikentän. Silmukka yritti kolme kertaa ja keskeytti koko suunnitelman.
  Korjaus: katkennut kutsu on mallin virhe (`katkennut_kutsu`), malli saa ohjeen lyhentää, `max_tokens` on 3 000, kenttien
  rajat (muistiinpano 1 000, perustelu 1 200, ehdotus 2 000, yhteenveto 2 000 merkkiä) näkyvät työkalukuvauksissa ja
  virheilmoitus kertoo todellisen pituuden. Viisi muuta hylättyä kutsua (`muu`) olivat liian pitkiä kenttiä, joiden rajoja
  malli ei tiennyt. 6 tarkistuspistettä ja 2 nollausta toimivat suunnitellusti.
- **Tarkistus repoa vasten:** rivinumeroviitteet 26/26 täsmäsivät; sitaateista 17/20 oli sanasta sanaan lähteessä (loput
  lainausmerkki- ja rivinvaihtoeroja). **Päättely oli heikompaa:** 4/9 ehdotuksessa väärä väite (95 %:n väli 19–73 %; yhdessä
  edellisen ajon kanssa 7/24, väli 15–49 %).

| # | Ehdotus (lyhennetty) | Arvio |
| ---: | --- | --- |
| 1 | ADR-0011 muka väittää 60 min vaativan hyväksynnän | **Väärä.** ADR sanoo "enintään 60 min, koska politiikka vaatii hyväksynnän sitä pidemmälle"; `policy.py` vertaa `>` 60:een. Ehdotettu korjaus on lähes sama lause |
| 2 | ADR ei erota hyväksynnän odotusta ja `awaiting_gpu`-tilaa | **Väärä.** ADR sanoo juuri sen: vain hyväksynnän odotus vanhenee (7 pv, `approvals.py:59`) |
| 3 | `istunnot`-taulu ja skeema 4 puuttuvat `db.py`:stä | Totta mutta ei virhe: ADR on luonnos ja ehdottaa taulun. Sanamuoto "ehdotetaan" voisi selkeyttää |
| 4 | `ehdota_tyo` ei ole `KNOWN_ACTIONS`issa | Sama: totta, ei virhe |
| 5 | SO_PEERCRED ei toteutettu; "CEO kirjoittaa tietokantaan" | Ensimmäinen totta (ei virhe). Toinen **väärin luettu**: gateway kirjoittaa, CEO:lla ei ole pääsyä kantaan |
| 6 | Viikkokatto: johtajan vaihto vs kutsun hylkäys ristiriidassa | Mekanismit täydentävät toisiaan, mutta **todellinen aukko:** ADR ei määrittele, miten istunto saa tiedon katon täyttymisestä |
| 7 | Agentin kiintiöt eivät toteutettavissa nykykoodilla | Totta (policy ei tunne pyytäjää, ei kirjanpitoa, ei GPU-odotuksen rajaa); käyttökelpoinen toteutuslista, ei virhe |
| 8 | `_start()`:n käynnistyshetken luokittelu testaamatta | **Väärä.** Kattavuus: rivit 348–353 suoritetaan (`test_approvals.py:330`); FORBIDDEN-alihaaran erillistestaus tarkistamatta |
| 9 | TILANNE.md:ssä ristiriita sallituista imageista | Liioiteltu: koneella olevat imaget ja sallittujen lista ovat eri asioita; selventävä lisäys kelpaa |

- **Johtopäätös:** malli hakee ja viittaa tarkasti, mutta vertaa suunnitteluluonnosta nykykoodiin ja tulkitsee puuttuvan
  toteutuksen virheeksi (kategoriavirhe), lukee väitteitä väärin ja väittää testejä puuttuviksi tarkistamatta. Ehdotusta ei
  voi hyväksyä ilman tarkistusta; tämä tukee ADR-0011 kohdan 8 Sol-tarkastusta ja deterministisiä tarkistuksia (haku,
  testikattavuus) ennen kuin väite kirjataan. Hyödyllistä: aukko 6 ja toteutuslista 7.
- Raportti, loki ja ehdotukset tuotiin Eliaksen paketista (`ilmari-yo-2026-10-07.tar.gz`); palvelimen loki ja kontin
  siivouksen tulos eivät olleet mukana, joten kontin pysäytys on tarkistamatta (sudo-aikaikkuna oli ajon lopussa
  todennäköisesti voimassa, koska ajo kesti alle 15 min).

### Sol-tarkastuskoe ja budjetin tarkistukset (7.10.)

- **Sol tarkastajana (käsin, ilman välittäjää):** Elias liitti ChatGPT:hen (`gpt-6.1-sol`, päättely high) yöajon yhdeksän ehdotusta
  lähderiveineen (`sol-tarkistuspaketti.md`). Claude oli tarkistanut ehdotukset etukäteen. Tulos: 8/9 samaan linjaan; neljä väärää
  väitettä (1, 2, 5, 8) ei hyväksynyt yksikään (V, V, E, E), neljä "totta mutta ei virhe" -tapausta sai tuomion O, ja puutteellisten
  lähteiden kohdalla Sol sanoi E eikä arvannut. Ero: ehdotuksen 6 aukkoa (katon täyttymisen signalointi) se ei nostanut esiin.
  Rajat: yhdeksän tapausta, luokittelu Clauden, otteet rajasivat näkyvyyttä. Tämä tukee tarkastajatilaa (ADR-0011 kohta 12).
- **OpenAI-dokumentaatiosta tarkistettu:** `gpt-6.1-sol` 2 $ / 10 $ per miljoona (syöte/tuloste), konteksti 1 050 000; työkalukutsut vain
  Responses API:lla; `reasoning.effort` low, medium (oletus), high, xhigh, max, ei none/minimal; EU-datasijainti tuettu (ei Fast-tilaa
  EU:ssa), projektikohtainen asetus; `usage` antaa tokenit (`input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens`), ei
  hintaa; `max_output_tokens` sisältää päättelytokenit ja katkennutkin vastaus laskutetaan. Datan käyttö- ja säilytysehtoja ei
  vahvistettu hausta; ne tarkistetaan ennen ensimmäistä sisältökutsua.
- **OpenAI:n kuluraja:** kuukausikohtainen (UTC). Vain "hard limit" päällä pyynnöt hylätään (HTTP 429 `insufficient_quota`), hälytys
  vain ilmoittaa; täytäntöönpano ei ole välitön. Elias on asettanut rajan 10 €; jakso ja kovuus tarkistamatta.
- **ChatGPT-budjetointiehdotus** (projektitiedosto) luettiin ja vietiin ADR-0011:n versioon 4 kohdaksi 11 korjauksineen: puoliavoin
  viikkoväli (ei `23:59:59`), konservatiivinen kurssi, "sama tila" tarkoittaa saman julkisen tilan, eskalointi alussa koodin säännöillä.
  Elias valitsi tarkastajan päättelyksi medium; kalibroidaan samoilla yhdeksällä tapauksella välittäjän valmistuttua.

## Istunto 8.10.2026 (budjettiydin, Sol-tarkastaja, mallit, ajattelu)

Näyttö: Eliaksen isäntäajojen tulosteet ja tiedostot (`sol-tulos*.json`, `meta.json`, `muistiinpanot.txt`, ajokansiot) sekä
Clauden valmistelukopiossa tekemät testit ja mutaatiokokeet. Valmistelukopiossa ei ollut Eliaksen reposta kuin
liitetyt koodikohdat, joten muutokset tehtiin täsmäkorvauksina (skripti hylkää koko muutoksen, jos korvattava kohta ei
löydy täsmälleen kerran), ja Eliaksen koneen testisarja on lopullinen todiste.

### Budjettiydin (`src/aiops/budget.py`, ADR-0011 kohta 11)

- Rahasummat ovat kokonaislukuja nanoeuroina, pyöristys aina ylöspäin. Jakso on maanantai 00.00 – seuraava maanantai
  00.00 Europe/Helsinki, puoliavoin (talviajan alkamisviikko 169 h ja kesäajan 167 h testattu). Viikkokatto 10 €,
  konservatiivinen kurssi 1 $ = 1 €, yhden kutsun enimmäishinta 1 €.
- Hinnasto `SOL_HINNASTO` (Standard, tarkistettu 8.10. OpenAI:n hinnastosta, vanhenee 30 pv): syöte 2,00, välimuisti 0,10,
  välimuistin kirjoitus 2,50, tuloste 10,00 $/M; yli 272 000 syötetokenia koko pyyntö pitkän kontekstin hinnoin
  (4,00 / 0,20 / 5,00 / 15,00). Kirjoittamaton syöte hinnoitellaan kirjoitushinnalla (usage ei erottele). Alueen kerroin 1,00
  (US); EU olisi +10 %.
- Varaus ja saldotarkistus ovat yksi `BEGIN IMMEDIATE`-transaktio. Kirjanpito on SQLite (append-only-triggerit) ja JSONL-loki,
  ja tilana käytetään kummastakin johdetuista luvuista suurempaa. Puuttuva, vioittunut tai kadonnut kirjanpito sulkee
  pilvikutsut (ei koskaan "käytetty = 0"). HTTP 429 `insufficient_quota` sulkee kutsut. Avaus ja ihmisen vahvistama alaraja
  (`vahvista`) ovat vain ihmisen CLI:ssä. 52 testiä; 14 mutaatiota kaatui kaikki testeihin.
- Isäntä: `/srv/aiops/valittaja` (root:root 0700), alustettu 8.10. klo 00.25: `budjetti.sqlite`, `budjetti.loki`,
  `ensikoe-ok.json`. `chattr +a` lokille ajettiin, mutta `lsattr`-varmistus (sudolla) on tekemättä. CLI:
  `sudo env PYTHONPATH=src /usr/bin/python3 -m aiops.budget --hakemisto /srv/aiops/valittaja nakyma|historia|avaa|vahvista`.
- Havainto: Responses API:n `usage` antaa `cache_write_tokens` (yön ajossa 75 131 / 75 149 syötetokenia); kirjattu kulu
  0,223031 € erosi tarkasta laskennasta 0,000007 €.

### Sol-tarkastaja (`scripts/sol_tarkasta.py`, `scripts/yo_sol.sh`, ADR-0011 kohta 12)

- Kolme alakomentoa: `paketti AJOKANSIO` (omana käyttäjänä; lähderivit commitista komennolla `git show`, vain sallitut tiedostot),
  `koe` (ensimmäinen valvottu kutsu, kulu alle sentin; kirjoittaa `ensikoe-ok.json`) ja `tarkasta PAKETTI` (sudolla).
  Responses API, `store: false`, päättely medium, JSON-skeema, enintään 5 ehdotusta tai 48 kt per erä, `--enint-eur 1.00`,
  `--erat-max 6` (korjatuilla otteilla 24 ehdotusta = 7 erää, joten `--erat-max 8`), ei uudelleenyrityksiä. Avain luetaan vain
  muistiin (`systemd-creds decrypt`, kokeillaan nimillä oletus, `openai`, `openai.cred`).
- `yo_sol.sh PLAN.toml -- YÖKOMENTO`: vaatii ensikokeen, kysyy Sol-osuudelle "kyllä", pitää sudo-aikaleiman hengissä koko
  ajon ajan (yöajo kestää yli 15 min), ajaa yöajon, rakentaa paketin ja lähettää sen. Tulos ajokansioon: `sol-paketti.json`,
  `sol-tulos.json`.
- Virhe ja korjaus: Qwen viittaa riveihin muodossa `r84–85`, jota paketoija ei tunnistanut; ehdotusten 17, 18, 20 ja 21 otteet
  puuttuivat tai olivat vajaat, ja neljästä E-tuomiosta kolme ratkesi uusinnalla (`--vain 17,18,20,21`, kulu 0,04 €).
- Testit: `tests/test_sol_tarkasta.py` 68 (HTTP väärennetty, verkkoveto kaataa testin); 24 mutaatiota kaikki kiinni.
  `shellcheck` ja `bash -n` läpäisty `yo_sol.sh`:lle.

### Yöajo 8.10. (q6, ajattelu pois, repo `d905b9b`) ja Solin tarkistus

Ajo `20261008-004002-yo-q6`: viisi pätkää, 541 askelta, 1 551 s (26 min; `lopeta` ennen kattoa), 20 nollausta, 24 ehdotusta
(20 hylätty päällekkäisenä), syötetokeneita 13 785 754 ja tulostokeneita 61 780, VRAM-huippu 25 761 MiB; neljäs pätkä pysähtyi
`toisto`-rajaan. Dispatcherin työt ennallaan (12/7/5).

| Tuomio (Sol) | medium, vanhat otteet | medium, korjatut otteet | high, korjatut otteet |
| --- | ---: | ---: | ---: |
| T (totta, korjaus tarpeen) | 2 | 3 (#11, #13, #18) | 4 (#11, #13, #18, #20) |
| O (totta, ei virhe) | 2 | 3 | 3 |
| V (väärä) | 14 | 13 | 12 |
| E (lähteet eivät riitä) | 6 | 5 | 5 |
| Kulu | 0,223 € | 0,255 € | 0,315 € |

- Medium ja high erosivat kahdessa ehdotuksessa (#20: E→T; #23: V→E), eikä T:tä käännetty V:ksi. High oli epäjohdonmukainen
  lähes samojen ehdotusten 22 ja 23 välillä. Päätös: medium oletuksena; high eskalointiin on ehdotus (ei päätös).
- **Clauden pistokoe:** 8 V-tuomiota tarkistettu lähteistä (1, 8, 12, 16, 19, 22/23, 24); 7 oikein, #12 kiistanalainen
  (O olisi osuvampi). Muita ei ole tarkistettu. Kaksi mallia samaa mieltä ei ole riippumaton todiste; E-tuomioille (esim.
  "testi puuttuu": #9, #10) tarvitaan deterministinen tarkistus.
- **Hyödylliset löydöt (4):** `TILANNE.md` rivi 323 ja 561 vanhentuneet (korjattu tässä päivityksessä); `gpukoe.py`
  `cmd_palvelin`-siivous ilman `sudo -n` (korjattu); `lue_muisti` kaatui lukuvirheeseen (korjattu). Väärin luettu: mm. Dockerin
  `--memory-swap 32g` = swap pois (Qwen väitti kahdesti päinvastaista).
- Ei tarkistettu: kontin pysäytys ja siivous ajon jälkeen (`sudo docker ps -a`, `ls /srv/aiops/mallityo`).

### `gpukoe`-korjaukset, IQ3_S ja ajattelun säätö

- **`gpukoe.py` (commit `8a00225`):** `DOCKER_EI_KYSY` (`sudo -n`) siivouksessa, `lue_muisti` jättää luvun pois virheessä
  (`MEMINFO`-vakio); testifeikki kaataa testin, jos `stop`, `logs` tai `rm` ajetaan ilman `-n`. 1100 passed.
- **IQ3_S (ADR-0009:n perusteltu poikkeus, Eliaksen hyväksyntä 8.10.):** `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`, revisio
  `d562806dbafae37109975e970aae91b43e73b440`, `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, 11 771 546 784 tavua, SHA-256
  `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`, Apache 2.0. Manifesti haettiin kahdesta toisistaan
  riippumattomasta ympäristöstä (täsmäsi), lataus karanteeniin `~/mallit-karanteeni/ista-iq3s` (64,7 Mt/s), `sha256sum` OK.
  Root-kopio `/srv/aiops/models/ista-qwen3.8-27b-gsq-rco/d562806…-iq3s` (root 0755/0644), `malli_manifest.py tarkista`: KAIKKI
  KUNNOSSA. Koodi (`4e1ae01`): `config/mallit/ista-qwen3.8-27b-gsq-rco-iq3s.tsv`, `MALLIT["iq3s"]`, `mallihakemisto()` ja
  `kontin_liput(..., malli=)`. 1113 passed. **Tekijöiden (ei meidän) väite:** IQ3_S "task-lossless" (AIME25 ja LiveCodeBench v6
  = BF16, GPQA-Diamond 89,39 vs 89,90). Ne eivät mittaa työkalukutsuja, pitkää kontekstia eikä suomea.
- **Nopeus (`gpukoe.py bench iq3s`, syvyydet 0 / 8 192 / 32 768):** generointi 94,0 / 90,2 / 83,3 t/s (Q6 64,1 / 62,8 / 59,2;
  Q4 78,8 / 77,7 / 72,1), pp512 3 788 / 3 600 / 2 850 t/s (Q6 3 256 / 3 143 / 2 563), VRAM-huippu 15 146 MiB (lepo 705).
- **Ajattelun säätö (commit `d938636`, 1132 passed, 1 skipped):** suunnitelman valinnaiset avaimet `paattely`
  (low, medium, xhigh), `paattelybudjetti` (256–16 384) ja `lampotila` (0–1,5). Ajattelun ollessa päällä palvelin saa
  `--reasoning-format deepseek --reasoning-effort … --reasoning-budget …`, pyynnön `max_tokens` = 3 000 + budjetti, ja
  `finish_reason: length` ilman työkalukutsua käsitellään katkenneena vastauksena (`katkennut_vastaus`), ei "ei kutsua" -tapauksena.
  Ajattelu pois: kaikki ennallaan. llama-server (b11430) tukee valitsimia (`--help` tarkistettu).

### Koesarja ja suunnitelmatiedostot (`config/yoluenta/`)

Sama suunnitelma (viisi pätkää) eri asetuksilla, kaikki samalta commitilta (HEAD kiinteä) ja kunkin jälkeen Sol-tarkastus:

| Ajo | Tiedosto | Muuttuja |
| --- | --- | --- |
| 1 | `yo-2026-10-06.toml` (uudelleen) | vertailukohta: Q6, ajattelu pois |
| 2 | `yo-iq3s-65536.toml` | IQ3_S, ctx 65 536 (**käynnissä 8.10. klo 23.07**) |
| 3 | `yo-iq3s-131072.toml` | IQ3_S, ctx 131 072 |
| 4 | `yo-ajattelu-0.4.toml` | Q6, ajattelu medium, budjetti 4 096, lämpötila 0,4 |
| 5 | `yo-ajattelu-1.0.toml` | sama, lämpötila 1,0 (Qwenin suositus ajattelulle) |
| (ei vertailu) | `yo-puhelinohjaus-valmistelu.toml` | kartoitus 8a-3d:n tueksi (gateway-lomake, migraatio, yöajon ohjeluku, kielletyt suunnat); Q6, ajattelu pois |

`~/code/yo_sarja.sh` ajaa nämä peräkkäin (järjestys: 1, valmistelu, 3, 4, 5). Se keskeytyy, jos HEAD vaihtuu tai pilvikutsut sulkeutuvat.

### Koesarjan tulokset (9.10. yöllä, HEAD `b4dfa0d`, `yo_sarja.sh`)

| Ajo | Asetukset | Askelia | Kesto | Nollauksia | Ehdotuksia | Sol T / O / V / E |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Q6, ctx 65 536, ajattelu pois (vertailukohta) | 453 | 1 138 s (19 min) | 11 | 23 | 6 / 3 / 7 / 7 |
| 2 | puhelinohjauksen valmistelu (Q6, kartoitus) | 313 | 1 044 s (17 min) | 6 | 20 | 0 / 9 / 2 / 9 |
| 3 | IQ3_S, ctx 131 072, ajattelu pois | 594 | 1 190 s (20 min) | 7 | 23 | 5 / 4 / 8 / 6 |
| 4 | Q6, ajattelu medium, budjetti 4 096, lämpötila 0,4 | 386 | 3 203 s (53 min) | 8 | 17 | 4 / 0 / 4 / 9 |
| 5 | Q6, ajattelu medium, budjetti 4 096, lämpötila 1,0 | 260 | 3 119 s (52 min) | 6 | 21 | 3 / 2 / 5 / 11 |

Ajokansiot: `20261008-234947-yo-q6`, `20261009-001037-yo-q6`, `20261009-002936-yo-iq3s`, `20261009-005046-yo-q6`,
`20261009-014510-yo-q6` (hakemistossa `~/ilmari-yo/`). Kaikki päättyivät syyhyn `valmis`; Sol-vaihe onnistui jokaisessa. Kirjanpito sarjan
jälkeen 2,139 € / 10 € (9.10. klo 02.38). IQ3_S 65 536 -ajon (`20261008-230713-yo-iq3s`) tulos ei kuulunut sarjaan eikä ole tarkistettu.

**Varovainen luku (vain lukumäärät, ehdotusten sisältöä ei ole vielä luettu):**
- **Kohina on suurta.** Sama asetus (Q6, ajattelu pois) antoi 8.10. V-osuuden 13/24 (54 %) ja nyt 7/23 (30 %); kaksi ajoa eri commiteilla, joten
  yhden tai kahden ehdotuksen erot asetusten välillä ovat kohinaa.
- **Ajattelu:** noin 2,8-kertainen kesto, T-määrä ei kasvanut (4 ja 3 vs 6), E-osuus noin kaksinkertainen (53 % ja 52 % vs 30 %), V-osuus
  hieman pienempi (24 % vs 30 %). T per tunti: Q6 noin 19, ajattelu 0,4 noin 4,5 ja ajattelu 1,0 noin 3,5. Tulostokeneita noin 170 000 vs
  50 000–67 000. **Raporttien (ajot 2–5) lisähavainto:** ajattelun ajoissa kaikki 10 pätkää päättyivät `lopeta`-kutsuun ja päällekkäisenä
  hylättyjä ehdotuksia oli vain 1 ja 2; ilman ajattelua `toisto`-pysähdys oli 4/9 pätkässä (ajot 2 ja 3, osin eri suunnitelmat) ja
  päällekkäisiä hylkäyksiä 16 ja 9. Ajattelu siis näyttää vähentävän toistoa ja kaksoiskirjauksia, mutta maksaa noin 2,8-kertaisen ajan, ja
  T per tunti on neljännes–viidennes. Syy E:n kasvuun (varovaisemmat väitteet vai heikommat otteet) on selvittämättä.
- **IQ3_S, ctx 131 072:** T-määrä (5) ja V-osuus (35 %) Q6:n kaltaiset; askelia nollausta kohti 85 vs 41 (Q6, ctx 65 536) ja nopeampi askel
  (594 askelta 1 190 sekunnissa vs 453 askelta 1 138 sekunnissa). VRAM-huippu 20 857 MiB (ennuste noin 20 GiB täsmäsi). Tämä tukee isomman kontekstin ja IQ3_S:n jatkomittausta; laadun yhtäläisyyttä
  se ei todista.
- **T-määrä voi sisältää saman löydön toistuvasti** (esim. TILANNE.md:n vanhentuneet rivit, jotka olivat korjaamatta HEADissa). Yksilöllisten
  löytöjen määrä vaatii ehdotusten luvun (digest).
- **Puhelinvalmistelu (ajo 2):** 20 ehdotusta, 9 O, 0 T oli odotettu (kartoitus: totta, ei virhe), 9 E (Sol ei voinut todentaa otteista), 2 V.
  Clauden tarkistus: ADR-viitteet (ADR-0010 82–83 ja 204–212; ADR-0011 84–90, 155–156 ja 205–216) täsmäävät; koodiviitteet ovat tarkistamatta.
  Sisältö on koottu PR:n tarkistuslistaksi (`puhelinohjaus-tarkistuslista.md`, ehdotettu polku `docs/valmistelu/`). Tärkeimmät löydöt:
  gatewayn `SCHEMA_VERSION = len(MIGRATIONS)` pakottaa asennusjärjestyksen (dispatcher migroi ensin); Qwenin ehdottama `tila.json` ajokansioon
  ei toimi, koska gateway ei lue kotihakemistoa; Qwenin `agentti`-kenttä ei ole ADR:ssä.

Vertailtavat: T-määrä, V-osuus, kesto, nollaukset, `katkennut_vastaus`/`katkennut_kutsu`, tokenit. Otos on pieni (24 vs 24:ssä V-osuus
14/24 → 7/24 antaa vasta p≈0,08), joten luvut lukee varoen ja ajot toistetaan tarvittaessa. Ajattelun ajoissa pätkän 0,5 h:n katto
voi katkaista työn (osa ajattelun hintaa).

### Pilvikrediitit, Ilmari-ready ja puhelinohjaus

- Elias sai 8.10. 100 € Claude Coden pilvisessio-krediittiä (ei API-krediittiä, ei GPU-vuokraa). Uutislähteiden mukaan krediitti
  kuluu ensin ja vanhenee 5.11. (varmista tililtä); ne eivät kata Projects- eikä Routines-ominaisuuksia.
- Ensimmäinen sessio laati `docs/ilmari-ready.md`:n (253 riviä, 236 lähdeviitettä; kiinnitetty commitiin `d905b9b`) ja avasi
  **PR #13:n (luonnos, `claude/ilmari-ready-docs-ops1vx` → main)**. Tarkistamatta; Clauden pistokoe tehdään komennolla, joka
  tulostaa satunnaiset viitteet. Neljä päätettävää: C1 (sitovatko "(alusta)"-kohdat uutta sovellusta; ehdotus kyllä), C3
  (tarjoamistapa puhelimelle; jää Ravintopolun käyttöönottoon), C5 (credentials-hakemisto vain rootille ja välittäjälle,
  ADR-0001/0002 tarkennettava), C7 (pilvisessio toimittaa PR:n, chat tar.gz:n; ei ristiriita).
- **Puhelinohjaus (8a-3d, ADR-0011 kohta 10):** tehty pilvisessiolla (PR #14, ks. alla), pohjana `main` (ADR-0011 v4 ja TILANNE luettiin
  commitista `d905b9b`). Sessio rakensi vain gateway-puolen: skeema 4 `agentti_ohjeet`, `/ilmari`, CLI `aiops ohjeet`,
  tilatiedoston luku. Yöajon puoli (silmukka lukee ohjeet pätkien välillä ja kirjoittaa tilatiedoston) tehdään erikseen.
  Ensimmäinen rajattu virstanpylväs on **käynnissä olevan T0-ajon ohjaus puhelimelta** (lisäohje, pysäytys, pätkän ohitus),
  ei ajon käynnistys; käynnistys vaatii 8a-3b:n ja allekirjoitetun istuntosuunnitelman.

### Pilvisessioiden PR:t (haettu 9.10.; Claude luki diffit ja PR-kuvaukset, Elias ajoi testit)

Kaikki kolme ovat luonnoksia, pohjana `main` (`10775e2`), yhdistettävissä, ilman kommentteja, katselmointeja ja CI-tarkistuksia.
Tila 9.10.: mikään ei ollut yhdistetty. **Päivitys 11.10.: pino (PR #16) ja #14 on yhdistetty ja #14 asennettu; #15 ja #13 odottavat.**

| PR | Haara ja kärki | Sisältö | Eliaksen testit |
| --- | --- | --- | --- |
| #13 | `claude/ilmari-ready-docs-ops1vx` `92045dc` | `docs/ilmari-ready.md`, 253 riviä | ei koodia |
| #14 | `claude/vaihe-8a3d-puhelinohjaus` `59ef4da` (2 commitia) | skeema 4, `/ilmari`, `aiops ohjeet`; +2166/−8, 17 tiedostoa | 1276 passed, 1 skipped (odotettu) |
| #15 | `claude/ml-ajoymparisto` `a1dc572` (1 commit) | ADR-0012, `images/ml/`, `aiops_ml`; +2775, 16 tiedostoa | 1102 passed, 1 skipped (odotettu) |

**#14 puhelinohjaus. Arvio: hyvä, yhdistettävissä. Ei estettä; ehdotetut jatkot alla.** Claude luki tuotantokoodin
(`db.py`, `instructions.py`, `gateway/status.py`, `gateway/app.py`, `config.py`, `cli.py`, mallit).
- Tarkistettu diffistä: vain `agentti_ohjeet` (skeema 4), ei `istunnot`-taulua. Append-only-triggerit estävät UPDATE ja DELETE, ja oma
  trigger estää REPLACE-kierron. CHECK-ehdot kattavat tyypin, tekstin pituuden (lisaohje 1–500, muut tyhjä), UTC-ajan muodon ja id > 0.
  Ohjeen tarkistus hylkää ohjausmerkit, rivin- ja kappaleenerottimet ja näkymättömät Cf-merkit; tuntiraja (30) lasketaan samassa
  `BEGIN IMMEDIATE` -transaktiossa kuin lisäys. `instructions.py` ei tuo jobs-, approvals-, policy- eikä dispatcher-koodia. `/ilmari`
  kulkee olemassa olevan guardin läpi (tunnus, osoite, Origin, Sec-Fetch-Site), ilman JavaScriptiä, vain kentät `tyyppi` ja `teksti`,
  onnistunut POST vastaa 303:lla. Tilatiedoston luku on kovennettu: ei linkkejä, enintään 64 KiB, tiukka JSON, vain tunnetut kentät,
  kaikki koodataan, vanhentunut tieto (yli 10 min) merkitään. `[gateway.ilmari]` on yhteisessä jäsentimessä, jotta dispatcher ei sulje
  WebAuthn-hyväksyntöjä (testi vahtii). CLI `aiops ohjeet` on vain luku (`mode=ro`, ei migraatiota).
- Ennallaan (diffin tiedostolista): `policy.py`, `approvals.py`, `dispatcher.py`, `pyproject.toml`, `uv.lock`, palvelutiedostot.
- Vastaa Ilmarin kartoitusajon (`puhelinohjaus-tarkistuslista.md`) kohtia: gateway A1–A9, migraatio B1–B6 ja CLI. Ei tarkistettu: ajo
  isännällä (PR:n vaiheet 2–7), joten koodin toiminta oikealla koneella on todentamatta.
- **Ehdotetut vastaukset PR:n avoimiin kysymyksiin:** (1) `tunnus` = Tailscale-tunnus, hyväksytään; (2) CLI:n oletus pysyy luettavana, `--json`
  koneelle (yöajo käyttää `--json`); (3) tilatiedosto `/srv/aiops/ilmari/tila.json` (elias:aiops, hakemisto 2750, tiedosto 0640), gateway
  lukee, yöajo kirjoittaa atomisesti; host-muutos ja muutoslokimerkintä; (4) tuntemattomat kentät ohitetaan kuten nyt; (5) **`pysayta`
  vapautetaan tuntirajasta** (pysäytyksen pitää toimia aina; oma pieni muutos); (6) vahvistussivu myöhemmin, ja yöajon silmukka lukee
  vain ajon alun jälkeen tulleet ohjeet (id-kursori), joten vahingossa painettu nappi ei vaikuta tulevaan ajoon; (7) ADR-päivitykset
  tekee Claude (ADR-0010:n taulukkoon rivi, ADR-0011:een skeemanumerointi 4 ja 5); (8) REPLACE-aukko vanhoissa tauluissa (`events`,
  `approvals`, `passkey_candidates`) korjataan omalla migraatiollaan; ei tässä PR:ssä.

**#15 ML-ajoympäristö. Arvio: hyvä, ei estettä; vaatii Eliaksen ajamat vaiheet 1–11 ennen yhdistämistä.**
- ADR-0012 (ehdotettu): konteksti, päätös, versiotaulukko lähteineen, hylätyt vaihtoehdot, seuraukset, "tarkistetaan toteutuksessa", ehdotus
  kokeen koodin toimitukseksi (ei toteutettu; JobSpec ennallaan) ja kahdeksan avointa kysymystä; tarkistamattomat asiat on merkitty
  avoimiksi eikä väitteiksi. Versiolähteitä (PyPI, pytorch.org, Docker Hub) Claude ei voinut tarkistaa; ne on todennettava lukituksella.
- Resepti `images/ml/`: pohjaimage kiinnitetty tiivisteellä (sama kuin `aiops/llama-muunnos:1`), `pip install --require-hashes
  --only-binary=:all:`, tarkistukset `RUN --network=none`, käyttäjä 10001, koti ja välimuistit `/tmp`:ssä, PIP_NO_INDEX, telemetria pois,
  ei apt-paketteja eikä kääntäjiä; lukitus `uv pip compile --generate-hashes --exclude-newer` ja lukon tarkistin (`tarkista_lukko.py`).
  Imagen oma paketti `aiops_ml` käyttää vain standardikirjastoa (tuloskortti, toistettavuus, savukoe; torch tuodaan laiskasti); koodissa ei ole
  verkko-, subprocess- eikä dynaamisia suorituskutsuja. `examples/sallitut-imaget.txt` ja `examples/ml-savukoe.yaml` lisätty.
- Ennallaan: politiikka, dispatcher, JobSpec, `pyproject.toml`, `uv.lock`.
- **Huomioitavaa:** (1) PR:n mukaan session monivaiheinen katselmointi on kesken ja tuo lisäcommitteja: tarkista `headRefOid` ennen
  yhdistämistä; (2) lukon sha256 pitää olla `a946658e5bf3568291fb63c6dbdc01d1afbc14dfb9ae2cf9219f342ee0ad33c3`, muuten pysähdy;
  (3) `RUN --network=none` vaatii BuildKitin (oletus uusissa Dockereissa); (4) image on noin 6–7 Gt; (5) `/tmp` on 1 Gt:n tmpfs, `noexec`-tila
  mitataan vaiheessa 7; (6) vaihe 10 muuttaa isäntää (sallittujen lista ja dispatcherin uudelleenkäynnistys, vain kun `aiops list --state
  running` on tyhjä); (7) repon `examples/sallitut-imaget.txt` sisältää `aiops/ml:1` ennen kuin asennettu lista sisältää sen, joten ADR-0008:n
  diff-tarkistus näyttää eron siihen asti; (8) torch 2.14.0 vs 2.14.1 on avoin.

**#13 Ilmari-ready. Arvio: rakenne hyvä, odottaa päätöksiäsi.** Pistokoe: 9/9 satunnaisesta ADR-0001/0003/0007/0008/0009/0010-, AGENTS.md- ja
TILANNE-viitteestä täsmäsi väitteeseen; kaksi `ADR-0009:169–172` -viitettä ylittää Clauden vanhan kopion pituuden (kopio on vanhempi kuin
repon versio), joten niitä ei voitu tarkistaa. Ei koodia. Ehdotetut päätökset ovat C1 (A-osan säännöt sitovat myös uutta sovellusta), C3 (jää
avoimeksi, päätetään ensimmäisen sovelluksen yhteydessä), C5 (credentials-hakemisto vain rootille ja välittäjälle; ADR-0001 ja ADR-0002
tarkennetaan), C7 (pilvisessio toimittaa PR:n, chat tar.gz:n). Yhdistä vasta, kun nämä on kirjattu dokumenttiin.

**Yhdistämisjärjestys ja odotettu testimäärä:** pino (+330) + #14 (+474) + #15 (+300) lisäävät mainin 802 testiin yhteensä noin 1906 testiä
(1 skipped); poikkeama selvitetään ennen asennusta. Ks. Seuraavat vaiheet kohdat 3 ja 5.

### Päätökset 8.10. (Elias)

1. OpenAI-API käytetään ilman EU-datasijaintia (`api.openai.com`, US/globaali); `store: false`; abuse monitoring -lokit 30 pv.
2. ISTA:n GSQ-RCO-kvantisointi hyväksyttiin karanteeniin ja mittaukseen ADR-0009:n "perusteltu poikkeus" -säännöllä.
3. Sol `high` sopii tarkastajalle (medium on silti oletus, kunnes ADR päivitetään; eskalointi E-tuomioille on ehdotus).
4. Puhelinohjaus tehdään pilvisessiolla ensimmäisenä (8a-3d ennen 8a-3a/b). Skeemanumerointi (`agentti_ohjeet` 4, `istunnot` 5)
   kirjataan ADR-0011:een.
5. Krediittien kulutusta ei mitata etukäteen; työt rajataan tehtävänannolla.

## Nykyinen lähtötila seuraavaa istuntoa varten

- **13.10. klo 01, ajantasainen:** main vähintään `11746d6` (PR #21); PR #22 (`vaihe-t1-yoajo`, `a47515d`) ja MUODOT-PR
  (`apps-ilmari-selain-muodot`) yhdistettävinä. `/opt/aiops/DEPLOYED` `58f5443`; kanta skeema 4; dispatcher ja gateway `active`;
  tilatiedosto `/srv/aiops/ilmari/tila.json` (viimeisin ajo jätti tilan `valmis`). Ajokansiot 12.–13.10.: `~/ilmari-yo/20261012-224146-yo-q6`
  (puhelinkoe), `~/ilmari-yo/20261012-225008-yo-q6` (katselmointi ja Sol) ja `~/ilmari-yo/20261013-001914-yo-q6` (T1-koe, `luonnos.patch`).
  Paikalliset, jo yhdistetyt haarat voi poistaa: `vaihe-8a3-ajattelu`, `docs-8a3d-muutosloki`, `vaihe-8a3d-yoajo`, `vaihe-8a3d-pysayta-raja`,
  `docs-8a3d-adr`, `adr-0011-hyvaksynta`. Avoimet PR:t #15 ja #13 ennallaan.
- **11.10. klo 23 (historiallinen):** main `b00ae39`; `/opt/aiops/DEPLOYED` `b00ae39`; kanta skeema 4; palautuspiste `~/aiops-ennen-8a3d.sqlite`
  (SHA-256 `ae4150d8…a059c`). Testit mainissa 1606 passed, 1 skipped.
- **8.10. ilta, git (historiallinen; ajantasainen tila yllä):** main ja origin/main `10775e2`. Mikään alla oleva haara ei ole mainissa; ne ovat yksi pino:
  `vaihe-8a1-gpukoe` (`2e96629`) → `vaihe-8a2-yoluenta` (…, `d905b9b` ADR-0011 v4 ja TILANNE 7.10.) → `vaihe-8b1-budjetti`
  (`f57856a` budget.py, sol_tarkasta.py, yo_sol.sh ja testit; `f26c37d` muutosloki: IQ3_S karanteeniin) →
  `vaihe-8a3-gpukoe-korjaukset` (`8a00225`) → `vaihe-8a3-iq3s-malli` (`4e1ae01`) → `vaihe-8a3-ajattelu` (`d938636`). IQ3_S:n
  root-asennuksen ja nopeusmittauksen muutoslokimerkintä sekä suunnitelmatiedostojen (`yo-iq3s-*.toml`, `yo-ajattelu-*.toml`)
  commit ovat joko tehty tai tekemättä: tarkista `git log --oneline -12` ja `grep -c "IQ3_S root-hakemistoon" docs/muutosloki.md`.
  Pilvisessioiden haarat (pohjana main, luonnos-PR:t, ei yhdistetty): PR #13 `claude/ilmari-ready-docs-ops1vx` (`92045dc`), PR #14 `claude/vaihe-8a3d-puhelinohjaus` (`59ef4da`), PR #15 `claude/ml-ajoymparisto` (`a1dc572`). Pinolle ei ole vielä PR:ää.
- **8.10. ilta, testit (historiallinen):** `vaihe-8a3-ajattelu` d938636: `uv run --frozen pytest -q` → **1132 passed, 1 skipped** (38,3 s).
  Aiemmat: 1090 (f57856a), 1100 (8a00225), 1113 (4e1ae01).
- **8.10. ilta, isäntä (historiallinen; `/opt/aiops/DEPLOYED` on nyt `b00ae39`):** `/opt/aiops/DEPLOYED` yhä `58cd1eb`. Uutta: `/srv/aiops/valittaja` (budjetti,
  root:root 0700), `/srv/aiops/models/ista-qwen3.8-27b-gsq-rco/d562806…-iq3s` (root-kopio), `~/mallit-karanteeni/ista-iq3s`
  (karanteenikopio, 0700; voi poistaa, kun root-kopio on hyväksytty), ajokansiot `~/ilmari-yo/20261008-004002-yo-q6`
  (24 ehdotusta, `sol-paketti-2.json`, `sol-tulos-2.json`, `sol-medium-24.json`, `sol-high-24.json`) ja
  `~/ilmari-yo/20261008-230713-yo-iq3s` (käynnissä tai valmis).
- **Käynnissä ei mitään:** koesarja päättyi 9.10. noin klo 02.30. Kontteja ei jäänyt (tarkistettu ennen sarjaa; sarjan jälkeen tarkistamatta).
- **OpenAI-budjetti:** kirjanpito 2,139 € / 10 € (viikko 5.–12.10.) 9.10. klo 02.38 sarjan jälkeen; jäljellä 7,86 €.
- **Aiempi 7.10.-lähtötila alla** on yhä voimassa niiltä osin kuin sitä ei ole korvattu.
- Git 7.10.: main ja origin/main `10775e24df0ef5269f10922652d3f551a1080d1f` (PR #12 yhdistetty 6.10.; sisältää
  dokumentointicommitin `df64264`). Haara `vaihe-8a1-gpukoe` (`2e96629`: GPU-pilottiskripti, testit ja ohje, ei PR:ää)
  ja sen päällä haara `vaihe-8a2-yoluenta` (`b1ae543` yöluenta, `366ba94` silmukan korjaus ja 7.10. commit: pätkitetty
  suunnitelma, päällekkäisyyssuodatin ja ADR-0011 luonnos; viimeinen commit on `d905b9b` (ADR-0011 v4 ja TILANNE 7.10.;
  tunniste saatu 8.10.). Paikallinen ja etähaara `vaihe-8a1-rootkopio` ovat yhä olemassa. Palveluiden deployta ei tehty.
- Resurssit ennen root-kopiota (6.10., eivät uusi mittaus kopion jälkeen): levy 2,3 T,
  käytössä 1,1 T, vapaana 1,2 T; RAM available 54 GiB; GPU 742/32607 MiB.
- Aiempi main: `5628b20` (PR #11 yhdistetty 6.10., Eliaksen tulosteella vahvistettu).
  PR #11:n viimeinen haaracommit oli `4ce5fa2ad023f2be631a81297c5db8125a955845`
  (Q6_K:n tulos, toistettavuus ja ylimääräisen kopion poisto muutoslokiin); koodicommit
  `e37e9eba16bc798f544f01afdb0e2b63c4526fa7` yleisti kvantisointiskriptin Q6_K:lle.
  Aiemmat yhdistämiset: `1f8a5e7` (PR #10), `1d384f0` (PR #9), `e5295b8` (PR #8)
  ja `b75fc34` (PR #7, ADR-0009).
- Paikallinen haara `vaihe-8a1-q6k` poistettu yhdistämisen jälkeen; PR #10:n haarat
  on aiemman tilannekuvan mukaan poistettu. Etähaaran poistosta ei ole uutta näyttöä.
- Testit: Eliaksen koneella viimeksi nähty `uv run --frozen pytest -q` → **917 passed, 1 skipped** (25,94 s, commit
  `b1ae543`). Clauden valmistelukopiossa etuoikeudettomana (vastaa Eliaksen ajoa) viimeisin tila **963 passed, 1 skipped**
  (28 s; koodia lisättiin: `test_gpukoe.py` 43, `test_ilmari_yo.py` 125). Myöhempien commitien Eliaksen tuloksia ei
  toimitettu tälle päivitykselle. Rootina ajettuna kolme testiä ohittuu. Aiempi: 802 passed, 1 skipped (PR #12).
- Historiallinen Eliaksen testi ennen PR #11:n dokumentointicommitia ja yhdistämistä:
  `uv run --frozen pytest -q` → **761 passed, 1 skipped**, 16,67 s. Tämä
  dokumentointipäivitys ei muuta koodia; sarjaa ei tässä päivityksessä ajettu uudelleen.
- OpenAI-credential: `/etc/aiops/credentials/openai.cred`, root:root 0600, 754 tavua;
  hakemisto root:root 0700. Mallilistakoe onnistui, välittäjäpalvelu on vielä toteuttamatta.
- Imaget: aiops/llama-server:1 = `72dcb4910b6e` (3,64 GB), aiops/llama-muunnos:1 =
  `8f977d43894830435b9ca67a3033b0403817e314809d2db380d502ffc0295cba` (2,15 GB; todistettu commitin `91b919d`
  reseptistä välimuistirakennuksella, sama ID). Poistettu: `194b09305fb3` (upotettu käyttöliittymä
  "latest") ja `34954f0eedf1` (ilman USERia). Ei sallittujen listalla: dispatcher ei voi ajaa niitä.
- /srv/aiops/mallityo (root:aiops 2770, luotu 6.10. klo 00.16):
  qwen3.8-27b-bf16.gguf 53 808 282 112 tavua, 10001:aiops 0644, SHA-256
  `44e2957458acc9c5e5bd297ff25832ef72b1b8aa5bfffb082c71059406cb0542`. Alihakemisto `q4-k-m.A1vIwg`
  (elias:aiops 2770, skriptin luoma): `qwen3.8-27b-q4-k-m.gguf` 16 547 400 192 tavua (15,41 GiB), 10001:aiops 0644,
  SHA-256 `95151662a26e3667c3ea93fa0a2414097c1b9639a37ee178814acae7454b3920`, sekä `q4-viite.tsv` ja
  `alkupera.tsv` (0640). Alihakemisto `q6-k.m3qXUv` (elias:aiops 2770): `qwen3.8-27b-q6-k.gguf`
  22 082 529 792 tavua (20,57 GiB), 10001:aiops 0644, SHA-256
  `e45467caef1073ab75792cd3860c6b496685015be0c2a4320f361f980bbe9cca`, sekä `q6-k-viite.tsv` ja `alkupera.tsv`
  (0640). Toisen ajon samanlainen kopio `q6-k.gYWUUr` poistettu. Lokit kotihakemistossa:
  ~/aiops-q4_k_m-kuivaharjoitus.TQWAXw, ~/aiops-q4_k_m-kvantisointi.D9JQ1t, ~/aiops-q6_k-kuivaharjoitus.ysv5rN ja
  ~/aiops-q6_k-kvantisointi.D5uXAz.
- `/opt/aiops/DEPLOYED`: `58cd1eb 2026-10-04T22:37:35+03:00`. Palvelut active, live-kanta skeema 3, jobs 24,
  approvals 9, passkey_candidates 1 (ei muutoksia 4.10. jälkeen).
- Puhelimen avain: elias-puhelin, sormenjälki `655a a1a2 e949 72ed bbde 9b98 986d 30d7 c2ef a3f3 ed10 1955 a682 826e f07b 51d4`.
- Malli: /srv/aiops/models/qwen3.8-27b/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0, 32 tiedostoa,
  55 586 114 863 tavua, root:root 0755/0644, läpäisi manifestitarkistuksen 5.10.
- Isännän jäljet 6.–7.10. (ei palvelumuutoksia): kontit `aiops-koe-bench`, `aiops-koe-palvelin` ja `aiops-ilmari-yo`
  (`sudo docker run`, imagena `aiops/llama-server:1`) ajettu ja poistettu; 6.10. kokeen jälkeen `docker ps -a` näytti vain kolme
  14 kk vanhaa `hello-world`-konttia, `/srv/aiops/mallityo` ei sisältänyt `koe-soketti.*`-hakemistoja, VRAM 548 MiB ja
  dispatcherin työt ennallaan (12 succeeded, 7 cancelled, 5 failed; viimeisin työ 24). 7.10. yöajon päätyttyä sama tarkistus on
  tekemättä. Kotihakemistossa: `~/gpukoe-tulokset/` (viisi ajokansiota, 0700), `~/ilmari-yo/` (ajokansiot, 0700; viimeisin on 7.10. yöajo),
  `~/llama-server-help.txt`, `~/llama-bench-help.txt`, `~/gpukoe-lokit-2026-10-06.tar.gz`,
  `~/gpukoe-lokit-2026-10-06-b.tar.gz`, `~/ilmari-savu-2026-10-06.tar.gz`, `~/ilmari-yo-2026-10-07.tar.gz`, `~/aiops-claude-repo.tar.gz` ja
  `~/aiops-claude-tila.txt`.
- Ollama: inactive ja disabled.
- Vanhempi 6.10. resurssihavainto: levy käytössä 994 Gt, vapaana 1,2 T; muisti 61 GiB,
  noin 53 GiB käytettävissä. Uudempi ennen root-kopiota mitattu lähtötila on yllä.

## Palautus

**12.10.: tilatiedosto ja Pysäytä-raja.** Vain jos jokin on pielessä. Konfiguraatio: `sudo cp -p /etc/aiops/aiops.toml.ennen-8a3d-ilmari
/etc/aiops/aiops.toml && sudo systemctl restart aiops-gateway` (sivu näyttää silloin "Ei tilatietoa.", yöajo jatkaa ilman tilatiedostoa);
hakemiston `/srv/aiops/ilmari` voi jättää tai poistaa. Koodi (pysäytysten oma raja): `git switch --detach b00ae39 && sudo scripts/deploy.sh
"$(command -v uv)" && git switch main` (ei kantamuutosta). Yöajon koodi (puhelinohjaus, T1) ajetaan reposta, joten se palautuu
`git revert` -komennolla tai haaran vaihdolla; T1:n luonnokset ovat vain ajokansioissa, eikä niitä sovelleta automaattisesti.

**11.10.: puhelinohjaus (skeema 4).** Palauta vain, jos jokin on pielessä: pysäytä gateway ja sitten dispatcher; ota epäonnistuneesta kannasta erillinen kopio; tarkista
palautuspisteen SHA-256 (`ae4150d8…a059c`), integrity ja skeema 3; `git switch --detach 58cd1eb && sudo scripts/deploy.sh "$(command -v uv)"`; kopioi palautuspiste
kannaksi komennolla `sudo install -o elias -g aiops -m 0660 ~/aiops-ennen-8a3d.sqlite /srv/aiops/db/aiops.sqlite`; poista `-wal`- ja `-shm`-tiedostot vasta, kun
kantaan ei ole yhteyksiä; käynnistä dispatcher ja gateway. Palautuspisteen jälkeen syntyneet työt, tapahtumat, hyväksynnät ja ohjeet menetetään; pelkkä koodin
palautus ei riitä, koska vanha koodi kieltäytyy skeemasta 4.

**8.10.: IQ3_S ja budjetti.** IQ3_S pois: `sudo rm -r /srv/aiops/models/ista-qwen3.8-27b-gsq-rco` (karanteenikopio
`rm -r ~/mallit-karanteeni/ista-iq3s`); koodi palautuu poistamalla haara tai `git revert` commitille `4e1ae01`. Budjetin
kirjanpitoa ei poisteta käsin: lokin `chattr +a` estää muokkauksen, ja kirjanpidon katoaminen sulkee pilvikutsut tarkoituksella.
Uusi alustus vaatii ihmisen toimen (`chattr -a` ja kirjanpidon tarkistus). Jos Sol-vaihe pitää ohittaa, ajetaan yöajo
ilman käärettä (`scripts/ilmari_yo.py suunnitelma TIEDOSTO`). Koodimuutokset (`gpukoe`, ajattelun säätö) palautuvat
`git revert` -komennolla omille commiteilleen (`8a00225`, `d938636`).

**8a-1, uusi Q4/Q6-root-kopio (6.10.):** vain jos mallia ei käytetä ja kohteen
sisältö on ensin tarkistettu, poistetaan yksilöidysti kaksi GGUF-tiedostoa polusta
`/srv/aiops/models/qwen3.8-27b/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0-gguf-b11430` ja hakemisto vain tyhjänä (`rmdir`).
Täsmälliset komennot: `docs/valmistelu/8a1-rootkopio.md`. Kopion lähteet ja BF16
säilytetään GPU-kokeen yli; niiden poistamista ei ole tehty. Alla olevat vanhempien
vaiheiden palautuskeinot eivät ole tämän istunnon suorituspyyntöjä.

**8a-1, imaget ja GGUF:t (6.10.):** `sudo docker image rm aiops/llama-server:1 aiops/llama-muunnos:1 &&
sudo docker builder prune` ja `sudo rm -r /srv/aiops/mallityo`. GGUF:t saa uudelleen muuntamalla ja
kvantisoimalla (ks. Käyttö); BF16-muunnos kesti 1 min 37 s ja Q4_K_M 2 min 41 s.

**8a-1 (isäntä):** Ollama takaisin `sudo systemctl enable --now ollama`. Mallihakemisto pois
`sudo rm -r /srv/aiops/models`. Painot saa takaisin lataamalla revision uudelleen ja tarkistamalla
manifestilla (ks. Käyttö).

**Puhelimen hyväksyntävalta pois** (esim. kadonnut puhelin), toimii ilman koodimuutosta ja ilman
verkkotiliä (harjoiteltu 7e:ssä):
`sudo rm /etc/aiops/hyvaksyjat/elias-puhelin.pub && sudo systemctl restart aiops-dispatcher`.
Käynnistysviestissä pitää sen jälkeen näkyä vain `elias (ed25519)`.

**Laite pois tailnetistä:** https://login.tailscale.com/admin/machines → laite → Remove. Vaatii
kirjautumisen Tailscaleen GitHub-tunnuksella. Takaisin kirjautumalla laitteen Tailscale-sovellukseen.
Passkeyn voi lisäksi poistaa puhelimen salasanojen hallinnasta (vaatii uuden rekisteröinnin).

**Avain takaisin** (harjoiteltu 7e:ssä): kopio on tiedostossa ~/elias-puhelin.pub. Järjestys on tärkeä,
koska kotihakemiston tiedostoon voi kirjoittaa mikä tahansa eliaksena ajettava ohjelma:
1. `sudo install -o root -g aiops -m 0640 ~/elias-puhelin.pub /etc/aiops/hyvaksyjat/elias-puhelin.pub`
2. Sormenjälki asennetusta tiedostosta:
   `/usr/bin/openssl pkey -pubin -in /etc/aiops/hyvaksyjat/elias-puhelin.pub -outform DER | /usr/bin/sha256sum | cut -c1-64 | fold -w4 | paste -sd' '`
   → `655a … 51d4`. Jos ei täsmää: `sudo rm` asennettu tiedosto, eikä dispatcheria käynnistetä uudelleen.
3. Vasta sitten `sudo systemctl restart aiops-dispatcher` ja käynnistysviestin tarkistus.

**7d-5 (koodi):** kanta ei muuttunut, joten riittää asentaa 7d-4:n koodi:
`git switch --detach d26974e && sudo scripts/deploy.sh "$(command -v uv)"`, sen jälkeen
`git switch main`. Hyväksyntärivit #4–#9 jäävät tauluun. 7d-3:een: `cc6c061` samalla tavalla.
Asennus kieltäytyy, jos töitä on käynnissä.

**Skeema 2 (7d-2:ta edeltävä tila):** `~/aiops-ennen-7d2.sqlite` on SQLite backup API:lla
luotu konsistentti skeema 2 -kopio, 0600, integrity ok, rivit 19/74/2. SHA-256:
`c777bf286603d0b8e9f0d9fbb513628dc8099b90c41a1014fd261a8e69be86eb`. Palautus vaatii
koodin `eaac91b` ja tämän backupin, ja sen jälkeiset työt (20–24), hyväksynnät (#3–#9) ja
passkey-ehdokkaat (#1) menetettäisiin. Järjestys ja omistus on kirjattu `docs/muutosloki.md`:hen.
Backup on samalla fyysisellä levyllä kuin live-kanta.

## Tavoite

Kirjoitat puhelimeen tehtävän, ja työasema hoitaa loput: tekoäly suunnittelee työn, työnjohtaja (dispatcher) ajaa sen eristetyssä kontissa näytönohjaimella, ja tulokset palaavat puhelimeen. Tekoäly on taitava mutta erehtyväinen työntekijä. Siksi rakennetaan ensin talo, jossa sen virheet eivät voi aiheuttaa vahinkoa, ja tekoäly tulee viimeisenä (vaihe 8).

## Ympäristö (mitattu, ei oletettu)

| Asia | Arvo |
| --- | --- |
| Käyttöjärjestelmä | Ubuntu 24.04.5 LTS, ydin 7.0, X11 ja GNOME, systemd 255. Kone on myös päivittäinen työpöytä- ja pelikone. |
| Suoritin ja muisti | Ryzen 9 7950X (32 säiettä), 64 Gt |
| Näytönohjain | RTX 5090 32 Gt, avoin ajuri 595.91.07 Ubuntun paketeista, CUDA-tuki 13.2, compute capability 12.0 |
| GPU-asetukset | BIOS-kytkin silent (575 W). Näyttö on kytketty 5090:een (ADR-0006), joten CUDA:n kernel-aikaraja on päällä. Työpöytä käyttää tyhjäkäynnillä noin 0,8–0,9 GiB VRAMia. |
| Levy | Yksi 3,6 Tt:n NVMe, jolla on myös Windows. Ei salausta, Secure Boot pois (hyväksytty riski). Linux-osio 2,3 T, vapaana 1,2 T (6.10.). |
| Työkalut | uv 0.10.11. Condan base on aina aktiivinen, mutta alusta ei käytä sitä (PATH:n `openssl` on condan; riippumattomiin tarkistuksiin /usr/bin/openssl 3.0.13). Git ja gh 2.45.0 (Ubuntun paketti), jolla git käyttää gh:n kirjautumista; `gh pr view` kaatuu ilman `--json`-valitsinta Projects (classic) -virheeseen. |
| Docker | 29.8.1, rootful, BuildKit (tukee `RUN --network=none`), NVIDIA Container Toolkit 1.20.1 (nvidia.github.io). Imaget: aiops/gpu-smoke:1, aiops/py-gpu:1, aiops/llama-server:1, aiops/llama-muunnos:1; vanhoja: open-webui (4,78 GB), nvidia/cuda:12.1.0-base, hello-world. |
| Palvelut | aiops-dispatcher ja aiops-gateway: systemd, enabled, käynnistyvät bootissa. Journal säilyy uudelleenkäynnistysten yli. |
| Verkko | UFW päällä (saapuvat kiinni). Tailscale 1.102.4: tyoasema 100.67.5.28 (tyoasema.taild1a5b7.ts.net) ja pixel-10a 100.93.75.21. Tailscale-kirjautuminen GitHub-tunnuksella (Elkkuboi@github). GitHubin kaksivaiheinen tunnistus päällä 4.10. (tekijä puhelimessa, palautuskoodit muualla; ADR-0004). Puhelimen passkey on Google Password Managerissa (synkronoitu, ADR-0010). |
| Tailscale Serve | https://tyoasema.taild1a5b7.ts.net (443) → unix:/run/aiops-gw/gateway.sock, vain tailnetiin. HTTPS-varmenteet päällä (nimet julkisissa CT-lokeissa). Funnel pois. |
| Muut palvelut | Ollama 0.13.5: pois käytöstä 5.10. (inactive, disabled; ohjelma, käyttäjä ja mallit ennallaan). Alusta ei käytä sitä (ADR-0009). RStudio Server osoitteessa 127.0.0.1:8787. Open WebUI poistettu, sen volyymi jätetty talteen. |
| Repo | ~/code/aiops ↔ github.com/Elkkuboi/aiops-tyoasema (yksityinen). Asennettu commit 58f5443 (12.10., PR #19). main ja avoimet PR:t: ks. "Nykyinen lähtötila". |
| Varmuuskopiot | ADR-0008: varmistus on GitHub-repo (koodi, ADR:t, muutosloki, konfiguraatiomallit); kanta ja työhakemistot saavat hävitä levyn menetyksessä. Paikallinen SQLite-palautuspiste ennen riskialttiita muutoksia. Ei ulkoista levyä. |

## Käyttäjät ja oikeudet

| Käyttäjä | Ryhmät | Rooli |
| --- | --- | --- |
| elias (1000) | sudo, aiops (ei docker) | Ihminen. Jättää töitä jonoon ja lukee tulokset komentoriviltä tai puhelimesta. |
| aiops-gw (994) | aiops (981) | Gateway systemd-palveluna: ei verkkoa, ei Dockeria, ei dataa (InaccessiblePaths), kirjoitus vain kantaan. Koti /nonexistent, kuori nologin. |
| aiops-run (993) | aiops (981), docker (983) | Dispatcher systemd-palveluna: ei verkkoa, ei API-avaimia, ei erityisoikeuksia. Koti /nonexistent, kuori nologin. |
| kontti | UID 10001, GID aiops (981) | Ei tiliä isännässä |

Ryhmä aiops on järjestelmän sisäinen maailma, eikä se anna oikeuksia isäntäkoneeseen. Kirjoitusoikeus tietokantaan ei anna valtaa hyväksyä: hyväksyntä vaatii hyväksyjän yksityisen avaimen (ADR-0007) tai puhelimen passkeyn ja sormenjäljen (ADR-0010). Ilman palvelun kovennusta aiops-gw näkisi kaiken datan, koska datahakemistot ovat 2750 elias:aiops (todettu 30.9.). Siksi gatewayn palvelutiedostossa on InaccessiblePaths=/srv/aiops/data.

## Hakemistot (ADR-0002)

| Polku | Tila | Sisältö |
| --- | --- | --- |
| /opt/aiops | root, 0755 | Asennettu koodi ja .venv. Asennettu commit on tiedostossa DEPLOYED. |
| /usr/local/bin/aiops, aiops-dispatcher, aiops-gateway | symlinkit | Komennot |
| /etc/systemd/system/aiops-dispatcher.service, aiops-gateway.service | root 0644 | Palvelutiedostot, lähde repossa config/systemd/. Asentaa deploy.sh. |
| /etc/aiops | root:aiops 0750 | |
| /etc/aiops/aiops.toml | root:aiops 0640 | [webauthn] rp_id, [gateway.kayttajat] (Tailscale-tunnus = elias) ja 12.10. alkaen [gateway.ilmari] tilatiedosto = "/srv/aiops/ilmari/tila.json" (ohjeita_tunnissa oletus 30). Malli config/aiops.toml.esimerkki. Luetaan käynnistyksessä: gateway koko tiedoston, dispatcher jäsentää koko tiedoston tiukasti mutta käyttää vain rp_id:tä, ja yöajo lukee tilatiedoston polun. Puuttuva tai rikkinäinen tiedosto estää gatewayn käynnistyksen; dispatcher käynnistyy, mutta hylkää kaikki WebAuthn-hyväksynnät. |
| /etc/aiops/aiops.toml.ennen-8a3d-ilmari | root:aiops 0640 | Varmuuskopio ennen [gateway.ilmari]-taulua (12.10.). |
| /etc/aiops/sallitut-imaget.txt | root:aiops 0640 | aiops/gpu-smoke:1, aiops/py-gpu:1. Luetaan käynnistyksessä: muutoksen jälkeen `sudo systemctl restart aiops-dispatcher`. |
| /etc/aiops/credentials | root:root 0700 | openai.cred: salattu systemd-credential, root:root 0600, 754 tavua (6.10.). Välittäjä ei ole vielä käytössä. |
| /etc/aiops/hyvaksyjat/ | root:aiops 0750 | Hyväksyjien julkiset avaimet (PEM): Ed25519 = komentorivi, P-256 = passkey. elias.pub (Ed25519, 0640) ja elias-puhelin.pub (P-256, 0640, 178 tavua, asennettu 3.10.). Luetaan käynnistyksessä: muutoksen jälkeen `sudo systemctl restart aiops-dispatcher`. |
| ~/.config/aiops/hyvaksyja.key | elias 0600 | Eliaksen yksityinen hyväksyjän avain. Ei repoon, ei chattiin, ei agentille. |
| ~/elias-puhelin.pub | elias 0644 | Kopio puhelimen julkisesta avaimesta (asennuksen lähde). Julkinen, vaaraton; voi poistaa. |
| /run/aiops-gw/ | aiops-gw 0700 | Gatewayn soketti gateway.sock (Uvicorn antaa sille tilan 0666, suojaus on hakemistossa). systemd luo ja poistaa. |
| /srv/aiops/db/aiops.sqlite | 0660 elias:aiops | Jono, audit-loki, hyväksynnät, passkey-ehdokkaat ja agentin ohjeet. Skeema versio 4 (append-only `agentti_ohjeet`, 11.10.). |
| /srv/aiops/ilmari | 2750 elias:aiops | Yöajon tilatiedosto tila.json (0640 elias:aiops, atominen kirjoitus), jonka gateway lukee ryhmän aiops kautta (12.10.). Päätetty 13.10., ei vielä luotu: alihakemisto ajot/ selaimen julkaisuhakemistoksi. |
| ~/aiops-ennen-8a3d.sqlite | elias 0600 | Palautuspiste ennen skeemaa 4 (SHA-256 `ae4150d8…a059c`). Säilytä. |
| /srv/aiops/db/dispatcher.lock | aiops-run:aiops | Yksi dispatcher kerrallaan (flock). |
| /srv/aiops/jobs/ID/ | 2770 aiops-run:aiops | work, output, logs (command.txt, stdout.log, stderr.log) |
| /srv/aiops/data/public, private, restricted | 2750 elias:aiops | Datan luokka = hakemisto (ADR-0003) |
| /srv/aiops/mallityo | root:aiops 2770 | Väliaikainen työhakemisto GGUF-muunnokselle ja kvantisoinnille (6.10.). Kontti kirjoittaa ryhmän aiops kautta, tiedostot 10001:aiops 0644. BF16 sekä kvantisointien omat alihakemistot q4-k-m.A1vIwg ja q6-k.m3qXUv (elias:aiops 2770: GGUF, oma viite, alkupera.tsv). Poistetaan, kun lopulliset tiedostot on kopioitu ja mitattu (tiedostot yksilöidysti, hakemistot tyhjinä). |
| /srv/aiops/models/MALLI/REVISIO | root:root 0755, tiedostot 0644 | Mallien painot (ADR-0009, ADR-0002:n tarkennus). Nyt qwen3.8-27b/1d4bf0f2…, tarkistettu manifestilla config/mallit/qwen3.8-27b.tsv. Kontit vain luku -liitoksena (8a-1:ssä). |
| /srv/aiops/models/qwen3.8-27b/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0-gguf-b11430 | root:root 0755, tiedostot 0644 | Q4_K_M ja Q6_K, 38629929984 tavua. Riippumattomat stat-, sha256sum- ja manifestitarkistukset läpäisty 6.10. |
| /srv/aiops/models/ista-qwen3.8-27b-gsq-rco/d562806dbafae37109975e970aae91b43e73b440-iq3s | root:root 0755, tiedosto 0644 | ISTA GSQ-RCO IQ3_S, 11771546784 tavua (8.10.). Manifesti config/mallit/ista-qwen3.8-27b-gsq-rco-iq3s.tsv; tarkistus läpäisty. Ei hyväksytty koordinaattoriksi, vain mittaukseen. |
| /srv/aiops/valittaja | root:root 0700 | Pilvibudjetin kirjanpito: budjetti.sqlite, budjetti.loki (append-only-lokiin `chattr +a` ajettu, varmistus tekemättä) ja ensikoe-ok.json. Vain root ja sudolla ajettu sol_tarkasta.py. Ei palvelua. |
| ~/mallit-karanteeni/ista-iq3s | elias 0700 | IQ3_S:n karanteenikopio (ADR-0009: karanteeni → mittaus → hyväksyntä). Ei liitetä kontteihin. |

## Päätökset (ADR)

- **0001:** rootful Docker ja kaksi palvelukäyttäjää. Kontin kovennusliput ovat pakolliset.
- **0002:** koodi, konfiguraatio ja tila ovat eri paikoissa. Tarkennus: ryhmä aiops, kontti on GID aiops, dispatcher ei luota jonoon. Tarkennus 5.10.: /srv/aiops/models (root 0755/0644), mallin manifesti repossa ja tarkistus kopioinnin jälkeen. Tarkennus 6.10. (PR #10): /srv/aiops/mallityo on ihmisen muunnostyön välihakemisto (root:aiops 2770); kvantisoinnille luodaan uusi yksilöllinen alihakemisto (elias:aiops 2770), joka on kontin ainoa kirjoittava liitos, ja BF16 liitetään yksittäisenä vain luku -tiedostona; palveluiden painot kopioidaan edelleen root-omisteisina /srv/aiops/models-hakemistoon.
- **0003:** datan luokka on hakemisto. Yksityisestä datasta ulkoiseen API:in vain skeemat ja yhteenvedot. Rajoitettua dataa ei koskaan ulos.
- **0004:** etäkäyttö vain Tailscalen kautta, ei SSH-palvelinta. Tailnetissä suodattimena toimii politiikka (config/tailscale/policy.hujson): omat laitteet saavat avata tyoasemaan vain portin tcp:443. Tarkennus 1.10.: gateway kuuntelee Unix-soketissa, ei osoitteessa 127.0.0.1.
- **0005:** isännällä on vain ajuri, CUDA tulee imageista.
- **0006:** näyttö pysyy 5090:ssä, 2 GiB VRAMia on varattu työpöydälle ja pitkät laskennat pilkotaan lyhyisiin kernel-kutsuihin.
- **0007:** politiikka on puhdas funktio koodissa (AUTO, HYVÄKSYNTÄ, KIELLETTY), ja hyväksyntä on Ed25519-allekirjoitus, joka sidotaan työhön ja määrityksen tiivisteeseen, on kertakäyttöinen ja vanhenee.
- **0010:** gateway on postinkantaja: näyttää, vastaanottaa ja välittää, ei päätä eikä allekirjoita. Unix-soketti 0700-hakemistossa, Tailscale Serve, identiteetti otsakkeesta Tailscale-User-Login, osoite otsakkeesta X-Forwarded-Host (Serve ei välitä Host-otsaketta sokettiin, tarkennus 7b-3), POST vain omalta sivulta (Origin ja Sec-Fetch-Site), ei verkkoa, ei dataa. Puhelimen hyväksyntä on passkey (WebAuthn, ES256), jonka dispatcher tarkistaa julkisella avaimella elias-puhelin.pub. Tarkennus 7d-3: hyväksyjän avain valitsee tarkistustavan (Ed25519 → ed25519-rivit, P-256 → webauthn-rivit), ei rivin format-kenttä; haaste = `challenge()` eli ADR-0007:n viestin SHA-256; origin johdetaan dispatcherin RP ID:stä; aiops.toml:n jäsennin on `aiops.config`, eikä dispatcher tuo mitään gateway-paketista. Tarkennus 7d-4: rekisteröinti omassa moduulissaan `aiops.passkeys` (vain gateway ja CLI); hyväksyjän nimi todennetusta identiteetistä (`NIMI-puhelin`); /passkey on ainoa sivu, jolla skripti toimii, ja CSP sallii vain tiedoston /rekisterointi.js sekä Trusted Types; haaste ilman tilaa (`aiops-rekisterointi-v1`, nimi, antoaika, 10 min); sormenjälki = SHA-256 kanonisesta SPKI:stä; htmx:ää ei käytetä; live-havainnot 3.10. Tarkennus 7d-5: hyväksyntäsivu /tyo/ID/hyvaksy, haaste `approvals.challenge()` gatewayssa, puhelin valitsee passkeyn itse (ei allowCredentials, päätös 3.10.), userHandle vain aikaista virheilmoitusta varten, oma skripti /hyvaksynta.js samalla CSP-mallilla, gateway ei tarkista allekirjoitusta eikä lue avaimia; live-havainnot 4.10. Kaikki "Tarkistetaan toteutuksessa" -kohdat on todettu. Tarkennus 7e: loppukoe mobiiliverkosta, varastetun puhelimen kaksi lukkoa (tailnet ja avain) testattu erikseen livenä, seuraukset käyty läpi; vaihe 7 valmis.
- **0008:** varmistus on Git-repo; ajonaikainen tila saa hävitä levyn menetyksessä. Ennen riskialttiita muutoksia paikallinen palautuspiste. Hyväksyjien avaimet luodaan uudelleen. Tarkennus 5.10.: mallit kaikista /etc/aiops:n tiedostoista ja imagejen Dockerfilet ovat repossa; sallittujen imagejen malli korjattu (py-gpu puuttui); pohjaimaget python:3.12-slim ilman tiivistettä (hyväksytty); painot eivät kuulu varmistukseen. Uudelleenrakennusta ei ole kokeiltu. llama-imagejen pohjat on kiinnitetty tiivisteellä (6.10.); py-gpu ja gpu-smoke yhä ilman.
- **0009:** paikallinen koordinaattori (CEO) dispatcherin GPU-työnä kovennetussa kontissa, vain Unix-soketti, ei esivaltausta (CEO odottaa GPU-työn ajan); painot /srv/aiops/models vain luku, SHA-256 ja alkuperä kirjattu, vain tunnetut julkaisijat; malli valitaan mittaamalla (ehdokkaat 4.10.: Qwen3.8-27B ensisijaisena, haastajina Gemma 4 ja Qwen3.6-35B-A3B; isännän vanhoja malleja ei käytetä). Pilvikumppani `gpt-6.1-sol` vain välittäjän kautta (API-avain systemd-credentialina, CEO ei näe), kulukatto 10 €/vko koodissa (varaus ennen kutsua), korkein vedenkorkeus: julkinen/yhteenvedot AUTO, yksityiset rivit HYVÄKSYNTÄ, restricted KIELLETTY. Eteneminen 8a (paikallinen, ei verkkoa) → 8b (välittäjä, yleiset istunnot) → 8c (yksityiset viestit hyväksynnällä).
- **0009, tarkennus 6.10. (8a-1, mainissa):** inferenssipalvelin llama.cpp tagi b11430 (commit 8345f333951c661d166b00e6f9362e553768f292), joka tukee arkkitehtuuria qwen35 ja Unix-sokettia (`--host` päättyy `.sock`, ei TCP:tä). Resepti images/llama/Dockerfile: aiops/llama-server:1 (palvelin ja mittaustyökalut, CUDA 12.8.1, ajoimage ilman RUN-komentoja) ja aiops/llama-muunnos:1 (safetensors → GGUF, torch CPU). Kaikki kiinnitetty (pohjaimaget tiivisteellä, llama.cpp commitilla, Python uv.lockilla), käännös ilman verkkoa, ei HTTPS:ää, ei selainkäyttöliittymää, ei NCCL:ää. Kvantisoitu versio tehdään itse; kuvaosa (mmproj) ja MTP-kerros jätetään V1:ssä pois (`--no-mtp`, sama kuin llama.cpp-projektin oma muunnos).
- **Vaatimus 6.10. (Elias): johtaja vaihdettavissa.** Koordinaattori on rooli, ei malli: Elias valitsee, hoitaako sen paikallinen Qwen vai `gpt-6.1-sol`. Seuraukset: yksi rajapinta johtajamalliin (paikallinen llama-server soketin kautta tai välittäjä → Sol); kun Sol johtaa, korkein vedenkorkeus koskee koko istuntoa alusta (julkinen ja yhteenvedot AUTO, yksityinen data vain hyväksynnällä, restricted ei lainkaan); johtaja kuluttaa budjettia nopeammin, joten katon täyttyessä istunto siirtyy paikalliselle johtajalle tai pysähtyy (päätetään); valinnan tekee Elias konfiguraatiossa tai istunnon alussa, malli ei voi ylentää itseään. Kirjataan ADR-0011:een ja ADR-0009:n tarkennukseksi. Ei muuta 8a:n järjestystä.
- **0011 (hyväksytty 12.10.2026, versio 5):** agentin rajapinta: CEO:n identiteetti, istunnot ja korkein vedenkorkeus, välittäjä ja budjetti, johtajan valinta (paikallinen tai Sol), tasot T0–T4, puhelinohjaus (kohta 10, toteutettu 8a-3d), tarkastajatila ja tuomioluokat T/O/V/E (kohta 12), päätökset 6.–7.10., 8.10. ja 12.10. Skeemanumerointi: `agentti_ohjeet` 4, `istunnot` 5. Poikkeus: T1 väliaikaisesti yöajon työkopioon (päätös 12.10. kohta 4) ennen 8a-3a:ta ja 8c:tä.
- **0010, tarkennus 12.10.:** gatewayn taulukkoon ohjeen tallennus (/ilmari, vain `agentti_ohjeet`, tuntiraja) ja tilatiedoston luku (vain luku).
- Eliaksen riskilinjaus 4.10.: turvatoimi tehdään, vaikka se olisi tarpeeton 95 % ajasta; jätetään pois vain, jos se on käytännössä aina tarpeeton. Huom: hyökkääjän valitsemissa tilanteissa normaalin käytön taajuus ei kuvaa riskiä, ja peruuttamattomat vahingot (tietovuoto) painavat enemmän.

## Koodi (repo ~/code/aiops)

- **`states.py`, `db.py`, `jobs.py`, `spec.py`, `policy.py`, `approvals.py`, `cli.py`, `dispatcher.py`:** kuten vaiheessa 6 (tilakone 13 kaarta, SQLite WAL ja nyt skeema 3, vertaa ja vaihda -siirtymät, tiukka määritys, politiikka v1, Ed25519-hyväksynnät, CLI check/submit/list/show/cancel/keygen/approve, kovennettu dispatcher). Muutos 7c: `create_job(conn, spec, submitted_by, reason="luotu")`.
- **`passkeys.py` (7d-4):** rekisteröinti, jota käyttävät vain gateway ja CLI (testi vahtii, ettei dispatcher tuo sitä). `verify_registration()` tarkistaa järjestyksessä: ES256 (−7), P-256 kanonisessa SPKI-muodossa, credential ID:n pituus, clientDataJSON (type webauthn.create, haaste, origin, ei crossOriginia eikä topOriginia, ei päällekkäisiä avaimia), rpIdHash, varatut liput, AT ja avaintiedot, credential ID = authenticatorDatan tunniste, BS vain BE:n kanssa, UP ja viimeisenä UV. ED sallitaan, COSE-avainta ei jäsennetä. `registration_challenge()` (SHA-256: `aiops-rekisterointi-v1`, approver, issued), `issued_at_problem()` (10 min, 1 min vinouma), `phone_approver()` (NIMI-puhelin, enintään 32 merkkiä), `fingerprint()`/`fingerprint_rows()` (16 neljän heksan ryhmää, neljä riviä), `public_key_pem()`, tiukka `b64url_decode()`, `insert_candidate()`, `candidate_problem()` (rivi on epäluotettavaa dataa).
- **`approvals.py` (7d-3):** `key_format()` (Ed25519 → ed25519, P-256 → webauthn, muut eivät kelpaa), `challenge()` (viestin SHA-256), `verify(…, rp_id=…)` tarkistaa järjestyksessä hyväksyjän, muodon ja avaimen vastaavuuden, allekirjoituksen (Ed25519 tai `webauthn.verify_assertion`), työn, tiivisteen ja ajan. Puuttuva tai tuntematon muoto hylätään. `insert_webauthn_approval()` tallentaa raakatavut ja base64-allekirjoituksen (gatewayta varten 7d-5:ssä). Avainten lataus hyväksyy Ed25519- ja P-256-avaimet.
- **`config.py` (7d-3):** aiops.toml:n tiukka jäsennin (`AiopsConfig`, `origin_for`), siirretty gatewaysta pakettitasolle. `gateway/config.py` tuo nimet täältä (`GatewayConfig` = `AiopsConfig`).
- **`dispatcher.py` (7d-3):** `--config` (oletus /etc/aiops/aiops.toml), `load_webauthn_rp_id()` ei kaada dispatcheria, `Config.webauthn_rp_id` välitetään jokaiseen tarkistukseen (myös käynnistyshetken uudelleentarkistus). Käynnistysviesti näyttää hyväksyjät muotoineen ja RP ID:n.
- **`cli.py` (7d-3):** `aiops approve` kieltäytyy selkeästi, jos käyttäjän nimellä on P-256-avain; `aiops show` näyttää hyväksynnän muodon.
- **`cli.py` (7d-4):** `aiops passkeys` listaa ehdokkaat sormenjälkineen; `aiops passkey-pem ID TIEDOSTO` kirjoittaa PEM-tiedoston (0644, ei ylikirjoita) ja tulostaa riippumattoman OpenSSL-tarkistuksen ja asennuskomennot. Kieltäytyy, jos samanniminen avain on jo asennettu tai ehdokas ei kelpaa. Ehdokasrivin tekstit näytetään ohjausmerkit koodattuina (ANSI-koodi voisi väärentää sormenjälkirivin päätteessä).
- **`db.py` (7d-2):** skeema 3 lisää approvals-tauluun `format`-kentän ja WebAuthnin raakatavut BLOBina sekä append-only `passkey_candidates`-taulun. Vanhat hyväksynnät säilyvät `ed25519`-muodossa. Triggeri suojaa myös uusia allekirjoitettuja kenttiä.
- **`webauthn.py` (7d-1):** puhdas ES256/P-256-assertionin tarkistin. Allekirjoitus tarkistetaan datasta `authenticatorData || SHA-256(clientDataJSON)`, sitten type, haaste, origin, crossOrigin/topOrigin, rpIdHash sekä UP/UV. Tuntemattomat clientDataJSON-kentät sallitaan; ristikehykset, WebAuthn-laajennukset ja assertionin AT-lippu hylätään. `signCount` jätetään käyttämättä ADR-0010:n mukaisesti.
- **`gateway/config.py`:** ohut tuonti moduulista `aiops.config` (7d-3). Puuttuva tai kelvoton aiops.toml estää gatewayn käynnistyksen.
- **`gateway/files.py`:** työhakemistot luetaan seuraamatta symbolisia linkkejä (O_NOFOLLOW ja dir_fd joka osalle, O_NONBLOCK putkia vastaan, vain tavalliset tiedostot).
- **`gateway/app.py`:** FastAPI ja Jinja2. CSP kieltää skriptit kaikilla sivuilla paitsi /passkey (7d-4). Portti (guard): vain GET, HEAD ja POST; osoite = RP ID (X-Forwarded-Host, jos Serve lähetti sen, muuten Host; väärä 421); Funnel-otsake 403; tuntematon tai puuttuva tunnus 403; POST vain, kun Origin = gatewayn osoite ja Sec-Fetch-Site = same-origin. Referrer-Policy on same-origin: no-referrer saisi selaimen lähettämään Originin arvona null (7c-3). Sivut: työlaatikko (odottaa hyväksyntää, käynnissä ja jonossa, päättyneet), työn sivu (tiedot, politiikka, tulokset ja kuvien esikatselu, lokin loppu, historia, hyväksynnät), uusi työ pohjasta (Tarkista, sitten Jätä jonoon), peruminen ja hylkäys vahvistussivun kautta, /kuka. Lukevat sivut avaavat kannan tilassa mode=ro, jättäminen ja peruminen tilassa mode=rw, migraatioita ei koskaan. Rajoitetun datan työstä näytetään vain tiedostonimet ja koot. `main()` tarkistaa, että soketin hakemisto on 0700, ja käynnistää Uvicornin; `--check` tarkistaa konfiguraation ja kannan. Passkey (7d-4): GET /passkey antaa haasteen (antoaika piilokentässä), CSP `script-src https://RP_ID/rekisterointi.js; require-trusted-types-for 'script'; trusted-types 'none'`; POST /passkey purkaa kentät tiukasti, tarkistaa ajan ja `verify_registration()`:n ja tallentaa ehdokkaan (sama passkey kahdesti → 409); tulossivu näyttää sormenjäljen. Alapalkissa linkki rekisteröintiin. Hyväksyntä (7d-5): GET /tyo/ID/hyvaksy vain awaiting_approval-työlle (muuten 409) näyttää määrityksen, politiikan, tiivisteen alun, hyväksyjän (NIMI-puhelin) ja voimassaolon 24 h, ja antaa haasteen `challenge(työ, tiiviste, vanheneminen, hyväksyjä)`; CSP sallii vain /hyvaksynta.js. POST purkaa kentät tiukasti (tiiviste 64 heksaa, voimassaolo tulevaisuudessa ja enintään 24 h + 1 min, userHandle = hyväksyjän nimi), vaatii että työ odottaa yhä, tiiviste vastaa nykyistä määritystä (muuten 409) eikä aiempi hyväksyntä odota dispatcheria (409), tallentaa `insert_webauthn_approval()`-funktiolla ja ohjaa työn sivulle (303). Työn sivulla linkki "Hyväksy puhelimella" ja hyväksynnän muoto.
- **`gateway/static/hyvaksynta.js` (7d-5):** `navigator.credentials.get` (userVerification required, ei allowCredentials), vastauksen tavut lomakkeen piilokenttiin ja `form.submit()`. Ei laske haastetta, ei kutsu luontia, ei verkkokutsuja (testi vahtii).
- **`gateway/static/rekisterointi.js` (7d-4):** gatewayn ainoa skripti: `navigator.credentials.create` (alg −7, UV required, attestaatio none, residentKey preferred, user.id = hyväksyjän nimi), getPublicKey/getAuthenticatorData/getPublicKeyAlgorithm ja lomakkeen piilokentät base64url-muodossa, sitten tavallinen `form.submit()`. Ei verkkokutsuja eikä innerHTML:ää (testi vahtii). Nappi on pois käytöstä, kunnes skripti on tarkistanut WebAuthn-tuen.
- **`gateway/pohjat/`:** gpu-savutesti, satunnaiskentta (siemen 7) ja hyvaksynta-testi.
- **`config/systemd/aiops-gateway.service`:** User=aiops-gw, RuntimeDirectory=aiops-gw (0700), ProtectSystem=strict, ReadWritePaths vain db, InaccessiblePaths=/srv/aiops/data, PrivateNetwork ja AF_UNIX, PrivateDevices, ProtectClock, RestrictSUIDSGID ja muu dispatcherin kovennus. Testi vahtii tätä.
- **`scripts/deploy.sh`:** asentaa molemmat palvelutiedostot ja pysäyttää ja käynnistää ne palvelut, jotka olivat käynnissä. Ei koskaan käynnistä uutta palvelua.
- **`scripts/gw_pyynto.py`:** yksi HTTP-pyyntö gatewayn sokettiin (testeihin, pelkkä standardikirjasto).
- **`scripts/gguf_asenna.py` (PR #12, commit 8dcbcae, isäntäajo tarkistettu):** kiinteät Q4/Q6-lähteet
  ja uusi kohde `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0-gguf-b11430`.
  `tarkista` vain lukee, `asenna` vaatii rootin. Puhdas repo ja commitin sisältö,
  UID 10001/GID 981/0644, koko ja SHA-256, polut ilman linkkien seuraamista,
  rootin omistama kohdepolku, levytila. Root-valmisteluhakemisto 0700;
  kopioiden tiivisteet tarkistetaan uudelleen nykyisellä manifestitarkistimella.
  Lopputila root:root 0755/0644; Linux renameat2 estää ylikirjoituksen myös
  kilpailussa. Virheessä valmistelu säilyy. Ei deployta tai palvelumuutoksia.
- **`config/mallit/qwen3.8-27b-gguf-b11430.tsv` (PR #12, commitoitu):** kaksi tiedostoa,
  yhteensä 38 629 929 984 tavua. Julkaisija/revisio kuvaavat lähdepainoja;
  omien GGUF-johdannaisten alkuperä ja resepti ovat muutoslokissa ja root-kopio-ohjeessa.
- **`tests/test_gguf_asenna.py` (PR #12, commitoitu):** 41 testiä. Riippumaton hello-tiiviste,
  oikea kopiointi ja osittaiset kirjoitukset, linkit/putket, muutettu lähde,
  olemassa oleva kohde ja kilpailu, levyraja, muuttumaton kuivaharjoitus,
  Git- ja root-vaatimukset, keskeytyneen valmistelun säilyttäminen.
  Root-omistus simuloitu, renameat2 oikeasti ajettu tilapäishakemistoissa.
- **`scripts/malli_manifest.py` (8a-1):** mallin manifesti. `hae REPO REVISIO` hakee Hugging Facesta jokaisen tiedoston koon ja tiivisteen (LFS: SHA-256, muut: gitin blob-SHA-1) kiinnitetystä revisiosta (vaatii huggingface_hub-paketin, ajetaan `uv run --no-project --with`). `tarkista MANIFESTI HAKEMISTO` vain standardikirjastolla: täsmälleen manifestin tiedostot tavallisina tiedostoina, koko ja tiiviste; linkit, puuttuvat ja ylimääräiset ovat virheitä, vain .cache/huggingface ohitetaan. Polut tarkistetaan (ei absoluuttisia, .., ohjausmerkkejä) ja näytetään koodattuina. Manifestin muoto `# aiops-mallimanifesti-v1`, jäsennys tiukka.
- **`images/llama/` (8a-1, mainissa):** Dockerfile (vaiheet lahde → kaannos → llama-server, lahde → llama-muunnos), pyproject.toml, uv.lock (28 pakettia, torch 2.11.0+cpu, ei nvidia-paketteja) ja .python-version. Testi `tests/test_llama_image.py` (19 testiä) vahtii tiivisteet, CUDA ≤ 13.2, commitin tarkistuksen, käännösvalinnat (OPENSSL, UI, NCCL pois, `RUN --network=none`), käyttäjän 10001, ENTRYPOINT [], muunnoksen offline-ympäristön ja USERin sekä lukon.
- **`scripts/gguf_vertailu.py` (8a-1, PR #10, mainissa):** `viite LÄHDE` (polku tai https, Range-pyynnöt) kirjaa jokaisen tensorin nimen, tyypin, muodon, koon ja näytteiden SHA-256:t (≤ 256 KiB kokonaan, muuten alku, keskikohta ja loppu à 16 KiB) sekä metatietojen tiivisteet; `vertaa VIITE TIEDOSTO` ilman verkkoa (tensorierot virheitä, metatietoerot tietoa). Vain standardikirjasto. Jäsennin tarkistettu llama.cpp:n gguf-py:tä vastaan (851 tensoria identtiset). 38 testiä, mutaatiokoe 17/17.
- **`config/mallit/qwen3.8-27b-bf16-viite-ggml-org.tsv` (PR #10):** viite tiedostosta ggml-org/Qwen3.8-27B-GGUF @ 71bc7b627595dc8a91039addd9c791ae548d6747 /Qwen3.8-27B-BF16.gguf (sama lähderevisio 1d4bf0f2…, `--no-mtp`): 851 tensoria, 40 metatietoa, 1847 näytettä. Haettu kahdesti toisistaan riippumatta (identtinen).
- **`scripts/gguf_kuivaharjoitus.sh` (PR #10, ChatGPT, Clauden tarkistama):** `[Q4_K_M|Q6_K]` (sallittujen lista, muuten paluukoodi 2 ennen isäntätoimia), `llama-quantize --dry-run` kontissa ilman kirjoittavaa liitosta, 5 min aikaraja, 4 GiB ilman swapia, loki kotihakemistoon.
- **`scripts/gguf_kvantisoi.sh` (PR #10 ChatGPT, yleistys PR #11 Claude):** `Q4_K_M|Q6_K` pakollisena argumenttina (muuten paluukoodi 2 ennen isäntätoimia); tyypistä hakemiston ja tiedoston nimi (`q4-k-m`, `q6-k`) ja levyvaatimus (24 tai 32 GiB); tiedostonimi ja tyyppi kulkevat kontin kuorelle argumentteina; ERR-käsittelijä kertoo epäonnistuneen rivin (`VIRHE: rivi N epäonnistui`). Vaatii puhtaan työpuun (kirjaa HEADin), BF16:n koon ja SHA-256:n (ennen ja jälkeen ajon), ryhmän 981, 24 GiB levyä ja 32 GiB RAMia. Luo `mktemp -d /srv/aiops/mallityo/TYYPPI.XXXXXX` (2770), kontti: image koko ID:llä `sha256:72dcb491…91d8` ja `--pull never`, `--runtime nvidia` + `NVIDIA_VISIBLE_DEVICES=none` (ajurin kirjastot ilman GPU-laitetta; kontti tarkistaa, ettei /dev/nvidia0 ole), UID 10001:981, `--network none`, `--read-only`, `--cap-drop ALL`, no-new-privileges, `--init`, 8 CPU:ta, 24 GiB ilman swapia, pids 128, tmpfs noexec, 60 min aikaraja ja EXIT-käsittelijä (`docker stop` nimellä). Kirjoittaa `.part`-tiedoston, siirtää `mv -n`, tekee oman viitteen ja vertaa tensorien nimet ja muodot ggml-org-viitteeseen, kirjoittaa alkupera.tsv:n. Tulos jää yksilölliseen hakemistoon. Oma viite on `TYYPPI-viite.tsv` (Q4-ajossa vielä `q4-viite.tsv`).
- **`tests/test_gguf_skriptit.py` (PR #10 ja #11, Claude):** 47 testiä: kummankin skriptin `docker run` -liput käsin kirjoitettua totuutta vastaan (kovennus, kielletyt liput kuten -p, --privileged, --gpus, -v ja --cap-add, image-ID, liitokset: syöte vain luku, ainoa kirjoittava $TYO), BF16-tiiviste ennen ja jälkeen ajon, .part ja `mv -n`, tensorivertailun sarakkeet; väärät argumentit, `--help` ja likainen työpuu ajetaan oikeasti väärennetyillä sudo- ja docker-ohjelmilla (ei kutsuja, ei lokia); PR #11: sallitut tyypit ja niistä johdetut nimet ja levyrajat, ERR-käsittelijä oikealla ajolla (puhdas testirepo ilman viitettä → oikea rivinumero). Mutaatiokokeet 18/18 (PR #10) ja 14/14 (PR #11) kiinni.
- **`config/mallit/qwen3.8-27b.tsv`:** Qwen/Qwen3.8-27B @ 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0, apache-2.0, 32 tiedostoa (18 safetensors-palaa).
- **Riippuvuudet:** pydantic, pyyaml, cryptography, fastapi 0.142, uvicorn 0.54 (pelkkä h11, ei uvloopia) ja jinja2. Kehitys: pytest ja httpx2. uv.lock lukitaan uv 0.10.11:llä.
- **Uusi valmistelusarja (root-kopio):** `uv run --frozen --no-sync pytest -q`
  → **802 passed, 1 skipped**, 14,95 s (6.10.). Käytettiin valmista
  riippuvuusympäristöä, jonka uv.lock on identtinen toimitetun repon kanssa;
  verkkolataus ei onnistunut. Tavallisessa eristyksessä FastAPI TestClient jäi
  odottamaan myös tyhjällä sovelluksella. Koko sarja läpäisi laajemmilla suoritusluvilla.
  Python-syntaksi tarkistettu. Bash-skriptejä ei muutettu. Valmistelutesteissä isäntäomistus
  simuloitiin; Elias on nyt erikseen ajanut todellisen kopioinnin ja tarkistanut sen.
- **Eliaksen testi PR #12:n valmistelusta:** `uv run --frozen pytest -q` →
  **802 passed, 1 skipped**, 14,74 s. Tämä tulos on ennen dokumentointipäivitystä.
- **`scripts/gpukoe.py` (haara `vaihe-8a1-gpukoe`, `2e96629`):** GPU-pilottikoe, vain standardikirjasto. `tila`, `bench Q4|Q6`
  (`llama-bench`, keskiarvo ± keskihajonta, VRAM-seuranta) ja `palvelin Q4|Q6 --ctx N [--lataus dio]` (Unix-soketti, latausaika, kaksi
  suomenkielistä kehotetta). Kontin liput kuten dispatcherilla; lähtötarkistukset; tulokset `~/gpukoe-tulokset/`. Ohje:
  `docs/valmistelu/8a1-gpukoe.md`. 43 testiä (liput molempiin suuntiin, oikea Unix-soketti, koko ajo valedockerilla).
- **`scripts/ilmari_yo.py` (haara `vaihe-8a2-yoluenta`):** Ilmari 0, T0. Kuusi rajattua työkalua repon kopiosta, silmukka (lukulista,
  tarkistuspiste, nollausviesti, pysäytys ilman edistystä, toisto- ja virherajat), päällekkäisyyssuodatin, pätkitetty suunnitelma
  (`suunnitelma TIEDOSTO`, TOML, etukäteissuostumus "kyllä", kokonaisaika kova katto), raportti ja loki `~/ilmari-yo/`. Importtaa
  `gpukoe.py`:n kontti- ja soketti-funktiot. Katkennut työkalukutsu (HTTP 500 "Failed to parse tool call arguments") käsitellään
  mallin virheenä. Ohje: `docs/valmistelu/8a2-yoluenta.md`. 125 testiä; mutaatiokoe kaikki kiinni.
- **`config/yoluenta/yo-2026-10-06.toml`:** tämän yön suunnitelma; testi vahtii, ettei sitä muuteta rajojen ulkopuolelle.
- **`docs/adr/0011-agentin-rajapinta.md`:** hyväksytty 12.10.2026 (versio 5, PR #21); ks. Päätökset (ADR).
- **`src/aiops/budget.py` (haara `vaihe-8b1-budjetti`):** budjettiydin (ks. Istunto 8.10.). Vain standardikirjasto, ei verkkoa.
  CLI `python -m aiops.budget --hakemisto … alusta|nakyma|historia|avaa|vahvista`. 52 testiä (`tests/test_budget.py`).
- **`scripts/sol_tarkasta.py`, `scripts/yo_sol.sh`:** Sol-tarkastaja ja kääre (ks. Istunto 8.10.). 68 testiä
  (`tests/test_sol_tarkasta.py`).
- **`scripts/gpukoe.py` (8.10.):** `DOCKER_EI_KYSY`, `MEMINFO`, `lue_muisti` kestää virheet (`8a00225`); `MALLIT["iq3s"]`,
  `MALLIHAKEMISTO_POIKKEAVAT`, `mallihakemisto(malli)` ja `kontin_liput(..., malli=)` (`4e1ae01`). Testit
  `tests/test_gpukoe_korjaukset.py` ja `tests/test_gpukoe_iq3s.py` (rakenteellinen vartija: jokainen `kontin_liput`-kutsu välittää mallin).
- **`scripts/ilmari_yo.py` (8.10., `d938636`):** suunnitelman avaimet `paattely`, `paattelybudjetti`, `lampotila`; `Asetukset.lampotila`
  ja `max_tokens`; `finish_reason: length` → `katkennut_vastaus`; 19 uutta testiä `tests/test_ilmari_yo.py`:ssä.
- **`scripts/yo_sarja.sh` (repossa PR #16:sta lähtien):** useita yöajon suunnitelmia peräkkäin, suostumus kerran, Sol-tarkastus
  jokaisen jälkeen, HEAD-vartija, yhteenveto `~/ilmari-yo/sarja-*.txt`. Testattu väärennetyillä komponenteilla (kahdeksan tilannetta); löysi
  `pipefail`+`grep -q` -virheen. Siirrä repoon (`scripts/`) sarjan jälkeen.
- **`config/mallit/ista-qwen3.8-27b-gsq-rco-iq3s.tsv`**, **`config/yoluenta/yo-iq3s-*.toml`** ja **`yo-ajattelu-*.toml`:** ks. Koesarja.
- **`src/aiops/instructions.py` (8a-3d, PR #14 ja #19):** ohjeen tarkistus (tyypit `lisaohje` 1–500 merkkiä, `pysayta`, `ohita_patka`; ohjausmerkit,
  bidi- ja leveydettömät merkit hylätään, emojien ZWJ sallitaan), tallennus ja luku. Tuntiraja samassa `BEGIN IMMEDIATE` -transaktiossa:
  lisäohjeet ja ohitukset yhteinen raja, pysäytyksillä oma samansuuruinen raja (12.10.). Ei tuo töiden, hyväksyntöjen eikä dispatcherin koodia.
- **Gateway `/ilmari` (8a-3d):** GET näyttää ajon tilan (tilatiedosto, `gateway/status.py`: tiukka JSON, 64 KiB, ei linkkejä, yli 10 min vanha
  merkitään) ja viimeiset 20 ohjetta; POST tallentaa ohjeen ja ohjaa takaisin (303); samat tarkistukset kuin muissa lomakkeissa; ei
  JavaScriptiä. Ohjeteksti kertoo tilan viiveestä (12.10.). `[gateway.ilmari]` jäsennetään `aiops.config`:ssa. CLI `aiops ohjeet [--jalkeen ID]
  [--json]` (vain luku, `mode=ro`).
- **`scripts/ilmari_yo.py`, puhelinohjaus (PR #18):** `Ohjaus` lukee ohjeet asennetulla CLI:llä (`/usr/local/bin/aiops ohjeet --json --jalkeen
  ID`) jokaisen askeleen alussa; kursori = suurin id suostumuksen jälkeen; pysäytys → paluukoodi 4; ohitus vain lähetyshetkellä käynnissä
  olleeseen pätkään, toistosuoja 60 s; lisäohje käyttäjän viestinä, voimassa ajon loppuun (10 uusinta nollauksen jälkeen); luku epäonnistuu
  alussa → ajoa ei aloiteta, 5 peräkkäistä kesken ajon → lopetus. `Tilakirjuri` kirjoittaa tilatiedoston atomisesti (0640), tekstit
  gatewayn säännöillä; lopputila vastaa paluukoodia. Raporttiin "Ohjeet puhelimesta".
- **`scripts/ilmari_yo.py`, T1 (PR #22):** suunnitelman `kirjoitus = ["apps/…"]` tekee ajosta T1-ajon (suostumusnäkymä: TASO T1). Työkalut
  `kirjoita_tiedosto`, `lisaa_tiedostoon`, `muokkaa_tiedosto`; vain `apps/`-alihakemistoihin, ei piilo- eikä estettyjä nimiä; polku avataan
  osa kerrallaan ilman linkkien seuraamista; ohjaus- ja bidi-merkit hylätään (Trojan Source); 256 KiB / tiedosto, 400 kirjoitusta ja 16 MiB /
  ajo. Pohja erillisessä Git-hakemistossa `AJOKANSIO/luonnos.git` (malli ei näe), tulos `luonnos.patch` (0600, `git apply` -yhteensopiva) myös
  keskeytetystä ajosta; raporttiin "Luonnos (T1)". Kirjoitus lasketaan edistykseksi (tyhjän pätkän sääntö). 50 testiä, mutaatiokoe 15/15.
- **`config/yoluenta/`:** uudet `yo-puhelinkoe.toml` (live-koe 0,5 h), `yo-katselmointi-8a3d.toml` (katselmointiyöajo 3 h) ja `yo-t1-koe.toml`
  (T1: selaimen pohjatyö, 1 h).
- **`apps/ilmari-selain/MUODOT.md` (MUODOT-PR):** yöajon ja Sol-tarkastuksen tiedostojen muodot rivinumeroineen (commit `a47515d`); Ilmarin
  T1-luonnos ja Clauden korjaukset erillisinä committeina. SUUNNITELMA.md jäi ajokansioon (ei käyttöön).
- **Testit 13.10.:** mainissa (`11746d6`) **1661 passed, 1 skipped**, T1-haarassa (`a47515d`) **1711 passed, 1 skipped** (tavallisena käyttäjänä; rootina
  kolme lisää ohittuu). 12.10.: 1642 (PR #18), 1659 (korjaukset), 1661 (PR #19).
- **Testit, historia:** mainissa (PR #11) koko sarja **761 passed, 1 skipped** (6.10.; 8a-1:n imagetestit 19, vertailutestit 38 ja skriptitestit 47). PR #10:n jälkeen 751 passed. Ennen korjauscommitia 714 passed, 1 skipped (Codex, Elias ja Claude). Mainissa (PR #9) 676 passed, 1 skipped. Aiemmin haarassa `vaihe-8a1` koko sarja `uv run pytest -q`: **657 passed, 1 skipped** (14,04 s; ohitettu on vain rootina ajettava testi). 8a-1 lisäsi 47 testiä (tests/test_malli_manifest.py): riippumattomina totuuksina `git hash-object`- ja `sha256sum`-arvot tavuille `hello\n`; kielletyt suunnat: kelvottomat manifestit (otsake, revisio, lisenssi, koko, tiivisteen tyyppi ja pituus, polut .., /, //, ., kenoviiva, .cache/huggingface, ohjausmerkit, järjestys, ylimääräinen kenttä), ristiriitainen Hugging Facen vastaus (eri revisio, LFS-koko, puuttuva koko, kelvoton lisenssi), puuttuva, väärän kokoinen ja muuttunut tiedosto, ylimääräinen tiedosto, linkki tiedostoon ja hakemistoon, hakemisto linkkinä, ohjausmerkit tulosteessa. Mutaatiokoe 11/11 kiinni. Aiemmin: 611 testiä; Eliaksen koneella haarassa `vaihe-7d5` koko sarja `uv run pytest -q`: **610 passed, 1 skipped** (14,44 s; ohitettu on vain rootina ajettava testi). 7d-5 lisäsi 38 testiä (tests/test_gateway_approve.py), jotka kulkevat koko kierroksen gatewayn sivulta dispatcherin tarkistukseen ja ajettuun työhön; kielletyt suunnat: väärennetty allekirjoitus (tallentuu, dispatcher hylkää), kopio samanlaiselle työlle, määrityksen muutos sivun avaamisen jälkeen, työ peruttu välissä, väärä voimassaolo, väärä passkey (userHandle), rikkinäiset kentät, toinen hyväksyntä edellisen odottaessa, lomake muualta tai ilman tunnusta, väärä skeema. Mutaatiokoe 7d-5: 10/10 kiinni. Chromium-virtuaalitodentaja: hyväksyntä ilman allowCredentials, UP ja UV, dispatcherin verify() hyväksyi. 7d-4 lisäsi 118 testiä (tests/test_passkeys.py, test_gateway_passkey.py, test_cli_passkey.py). Riippumattomat totuudet 7d-4: W3C WebAuthn -luonnoksen §16.2 rekisteröintivektori (liput 0x59 ilman UV:tä → hylkäys juuri UV:stä, UV-bitin kanssa hyväksytään; vektorin COSE-avain = sen yksityisen avaimen julkinen avain), sormenjälki laskettu `/usr/bin/openssl … | sha256sum` -putkella ja haaste sha256sum-ohjelmalla. Kielletyt suunnat 7d-4: väärä algoritmi, P-384/RSA/Ed25519 ja ei-kanoninen (tiivistetty) SPKI, webauthn.get-tyyppi, väärä haaste/origin/RP ID, crossOrigin/topOrigin, päällekkäiset avaimet, varatut liput, AT pois, katkaistu avaintieto, ristiriitainen credential ID, BS ilman BE:tä, UP tai UV pois, lomake muualta tai ilman tunnusta, vanha tai tuleva sivu, toisen nimen haaste, muutettu antoaika, rikkinäiset ja liian pitkät kentät, sama passkey kahdesti, väärä skeema, CLI: ohjausmerkit, ylikirjoitus, jo asennettu avain, kelvoton ehdokas. Mutaatiokoe 7d-4: 14 tarkoituksellista rikkomusta, kaikki jäivät kiinni. Päästä päähän ennen laitetta: Chromium (Playwright 1194) WebAuthn-virtuaalitodentajalla oikeaa gatewayta vasten HTTPS:llä: tallennettu avain = todentajan avain, POST Origin + Sec-Fetch-Site same-origin, UV:tön todentaja → NotAllowedError, JS pois → nappi pois käytöstä, Trusted Types estää innerHTML:n ja script.src:n, CSP estää toisen skriptitiedoston ja inline-skriptin. Aiemmat: 7d-3:n 49 WebAuthn-hyväksyntätestiä ja mutaatiokoe (9/9), 7d-1:n 26 testiä ja W3C Level 3 §16.6 -vektori, gatewayn pääsy-, CSRF-, tiedosto- ja palvelutiedostotestit.

## Käyttö

- Puhelimella: https://tyoasema.taild1a5b7.ts.net (Tailscale päällä).
- Tila ja loki: `systemctl status aiops-dispatcher aiops-gateway` ja `sudo journalctl -u aiops-gateway -f`
- Konfiguraation tarkistus: `(cd / && sudo -u aiops-gw aiops-gateway --check)`
- Dispatcherin käynnistysviesti (hyväksyjät ja RP ID): `sudo journalctl -u aiops-dispatcher -b --no-pager | grep käynnissä`
- Serve: `tailscale serve status`, pois `sudo tailscale serve --https=443 off`.
- Asennus: `sudo scripts/deploy.sh "$(command -v uv)"`, kesken työn `… --force`.
- Hyväksyntä työasemalla: `aiops approve ID` ja "kyllä". Hylkäys puhelimesta (Hylkää työ) tai `aiops cancel ID`.
- Passkey-ehdokkaat: `aiops passkeys`; PEM: `aiops passkey-pem ID ~/NIMI.pub` (tulostaa tarkistus- ja asennuskomennot). Rekisteröinti puhelimella: https://tyoasema.taild1a5b7.ts.net/passkey (alapalkin linkki). Uusi rekisteröinti korvaa puhelimen vanhan aiops-passkeyn, jolloin asennettu avain on vaihdettava.
- Hyväksyntä puhelimella: avaa odottava työ → Hyväksy puhelimella → tarkista määritys → Hyväksy sormenjäljellä. Tulos (käytetty tai hylätty syineen) näkyy työn sivulla ja komennolla `aiops show ID`.
- Puhelimen hyväksyntävalta pois: `sudo rm /etc/aiops/hyvaksyjat/elias-puhelin.pub && sudo systemctl restart aiops-dispatcher`. Takaisin: ks. Palautus (install, sormenjälki asennetusta tiedostosta, vasta sitten restart).
- Laite pois tailnetistä: https://login.tailscale.com/admin/machines → laite → Remove. Takaisin kirjautumalla laitteen Tailscale-sovellukseen. Tila: `tailscale status` (`direct` = suora yhteys, `relay` = DERP-välitys).
- Uutta koodia purettaessa: `tar -xzf ~/Downloads/NIMI.tar.gz -C ~/code`. Jos sama nimi ladataan toiseen kertaan, selain voi lisätä nimeen `(1)`: valitse uusin `F=$(ls -t ~/Downloads/NIMI*.tar.gz | head -n 1)` ja tarkista tiiviste.
- Commit-lohkot alkavat haaratarkistuksella: `test "$(git branch --show-current)" = HAARA && git add …`. Haarat näkyvät komennolla `git branch -v --list main HAARA` (`git rev-parse --short` hyväksyy vain yhden revision).
- Mallin manifesti ja tarkistus: `uv run --no-project --python /usr/bin/python3 --with huggingface_hub==2.1.1 python scripts/malli_manifest.py hae REPO REVISIO` ja `/usr/bin/python3 scripts/malli_manifest.py tarkista config/mallit/MALLI.tsv HAKEMISTO`. Lataus: `uvx --python /usr/bin/python3 --from huggingface_hub==2.1.1 hf download REPO --revision REVISIO --local-dir ~/mallit-lataus/NIMI`, sen jälkeen root-kopio manifestin mukaan (`install -o root -g root -m 0644`) ja tarkistus kopiosta.
- Kovennetut kontin liput käsin (samat kuin dispatcherilla): `G=$(getent group aiops | cut -d: -f3); K="--rm --network none --read-only --tmpfs /tmp:rw,size=1g,mode=1777 --cap-drop ALL --security-opt no-new-privileges --user 10001:$G --pids-limit 512"`.
- BF16-muunnos: `sudo docker run $K --memory 32g --memory-swap 32g --cpus 16 --mount type=bind,source=/srv/aiops/models/qwen3.8-27b/REVISIO,target=/malli,readonly --mount type=bind,source=/srv/aiops/mallityo,target=/ulos aiops/llama-muunnos:1 python /opt/llama.cpp/convert_hf_to_gguf.py /malli --outtype bf16 --no-mtp --model-name Qwen3.8-27B --outfile /ulos/qwen3.8-27b-bf16.gguf`.
- GGUF:n vertailu: `/usr/bin/python3 scripts/gguf_vertailu.py vertaa config/mallit/qwen3.8-27b-bf16-viite-ggml-org.tsv /srv/aiops/mallityo/qwen3.8-27b-bf16.gguf`; viitteen riippumaton haku: `… viite URL | diff - VIITE && echo SAMA`.
- Kvantisointi: kuivaharjoitus `bash scripts/gguf_kuivaharjoitus.sh TYYPPI`, sitten `bash scripts/gguf_kvantisoi.sh TYYPPI` (TYYPPI = Q4_K_M tai Q6_K, puhdas työpuu; aja kerran, jokainen ajo tekee uuden 16–22 Gt:n kopion). Tulos uuteen hakemistoon /srv/aiops/mallityo/q4-k-m.XXXXXX tai q6-k.XXXXXX, alkuperä tiedostossa alkupera.tsv. llama-quantize on CUDA-käännös ja tarvitsee libcuda.so.1:n, joten kontti ajetaan `--runtime nvidia`, vaikka GPU:ta ei käytetä.
- PR:n tarkistus: `gh pr view N --json number,state,isDraft,headRefOid,mergeable` (gh 2.45.0:n oletusnäkymä kaatuu), `git diff --stat main...origin/HAARA`, `git log --format='%h %an <%ae> %s' --name-only main..HAARA`. Yhdistäminen vain tarkistetusta kärjestä: `gh pr merge N --merge --match-head-commit SHA`.
- **Sol-tarkastus käsin:** `python3 scripts/sol_tarkasta.py paketti AJOKANSIO --repo ~/code/aiops --ulos AJOKANSIO/sol-paketti.json`, sitten
  `sudo /usr/bin/python3 scripts/sol_tarkasta.py tarkasta AJOKANSIO/sol-paketti.json --hakemisto /srv/aiops/valittaja --ulos AJOKANSIO/sol-tulos.json --erat-max 8`
  (`--paattely high`, `--max-output 16000`, `--enint-eur 2.00`, `--vain 17,18` ja `--ennakkosuostumus` tarpeen mukaan). Avain luetaan vain muistiin.
- **Yöajo ja Sol yhdellä komennolla (tmuxissa):** `tmux new -s yo`, sitten
  `scripts/yo_sol.sh config/yoluenta/TIEDOSTO.toml -- /usr/bin/python3 -B scripts/ilmari_yo.py suunnitelma config/yoluenta/TIEDOSTO.toml`
  (TIEDOSTO korvataan oikealla nimellä). Irrottautuminen `Ctrl-b`, `d`; takaisin `tmux attach -t yo`.
- **Yösarja:** `tmux new -s sarja`, sitten `cd ~/code/aiops && scripts/yo_sarja.sh config/yoluenta/A.toml config/yoluenta/B.toml …` (nimet
  korvataan oikeilla; sudo-salasana ja yksi "kyllä" alussa). Keskeytys `Ctrl-C`; sarjan jälkeen `cat ~/ilmari-yo/sarja-*.txt`.
- **Puhelinohjaus (12.10.):** käynnissä olevan yöajon aikana https://tyoasema.taild1a5b7.ts.net/ilmari: Lisäohje (enintään 500 merkkiä,
  voimassa ajon loppuun; malli noudattaa rajojensa sisällä), Ohita pätkä ja Pysäytä. Paina kerran, odota noin 10 s ja päivitä sivu: tila
  päivittyy vasta seuraavalla askeleella. Ennen ajoa tai ajojen välissä lähetetyt ohjeet eivät vaikuta (kursori). Tuntiraja 30 lisäohjetta
  ja ohitusta, pysäytyksillä oma 30. Kysymyksen voi esittää pyytämällä muistiinpanoa: se näkyy sivulla viimeisenä muistiinpanona. Ohjeet
  komentoriviltä: `aiops ohjeet --json --jalkeen ID`; tila: `cat /srv/aiops/ilmari/tila.json`. Paluukoodi 4 = pysäytetty puhelimesta;
  `yo_sol.sh` ajaa silti Sol-tarkastuksen ja `yo_sarja.sh` jatkaa seuraavaan suunnitelmaan.
- **Ennen yöajoa:** sulje Discord (tai kytke sen laitteistokiihdytys pois): sen renderöijä käyttää GPU:ta laskentaan, ja esitarkistus
  kieltäytyy. Tarkistus: `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` ei tulosta mitään.
- **T1-ajo (13.10.):** suunnitelmaan `kirjoitus = ["apps/NIMI"]`; ajo kuten T0 (`/usr/bin/python3 -B scripts/ilmari_yo.py suunnitelma
  TIEDOSTO`; ilman Solia, koska Sol lukee lähteet reposta). Tulos `AJOKANSIO/luonnos.patch` ja luonnoksen tiedostot `AJOKANSIO/tyokopio/apps/…`.
  Käyttöönotto omassa haarassa: `git apply --check --include=POLKU AJOKANSIO/luonnos.patch && git apply --include=POLKU …`; ensimmäinen
  commit luonnos sellaisenaan, toinen tarkistuksen korjaukset (jäljitettävyys).
- **Budjetin tila:** `sudo env PYTHONPATH=src /usr/bin/python3 -m aiops.budget --hakemisto /srv/aiops/valittaja nakyma`.
- **Uusi mallitiedosto karanteeniin:** manifesti haetaan kahdesti toisistaan riippumatta, `hf download --revision` (huggingface_hub 2.1.1
  uvx:llä), `sha256sum -c`; root-kopio `sudo install -d … && sudo install -o root -g root -m 0644 …`, sitten
  `python3 scripts/malli_manifest.py tarkista MANIFESTI HAKEMISTO` ja muutoslokimerkintä.
- **Suunnitelmatiedosto toisella mallilla tai asetuksilla:** `sed -e "0,/^nimi = .*/s//nimi = \"UUSI NIMI\"/" -e 's/^malli = "q6"/malli = "iq3s"/' -e "s/^ctx = .*/ctx = 131072/" config/yoluenta/yo-2026-10-06.toml > config/yoluenta/UUSI.toml`
  (`0,/…/` rajaa nimen vaihdon ylätason avaimeen, ei pätkien nimiin).
- **Opitut käytännöt 6.10.:** (1) haaran luonti ketjutetaan aina (`git switch -c X && …`), koska erillinen epäonnistunut rivi jätti purun mainiin (commit-lohkon haaratarkistus pysäytti committoinnin); (2) pitkiä monirivisiä komentoja ei liitetä yhtenä rivinä: rivinvaihtojen kadotessa `set -euo pipefail IMAGE=…` asetti positionaaliset parametrit ja tee loi repoon roskatiedostot (poistettu); pidemmät ajot skripteinä repoon; (3) ennakkokokeet ajetaan käyttäjänä 10001 ilman passwd-riviä (`setpriv --reuid=10001 --regid=981 --clear-groups`), koska root-ajo piilotti torchin getpwuid-kaatumisen; (4) rakennuslokit luetaan aina: llama.cpp latasi käyttöliittymän verkosta oletuksena; (5) toisen tekoälyn commitit tarkistetaan ennen yhdistämistä: diff ja arkisto tiivisteineen, testit omassa ympäristössä, isännän tiedot omilla vain luku -komennoilla (TILANNE väitti Q4-tiedot muutoslokiin, mutta ne puuttuivat), yhdistäminen `--match-head-commit`; (6) `git log` avaa sivuttajan: `git --no-pager` tai `q`.
- **Opitut käytännöt 8.10.:** (1) Ketjun tarkistuksessa käytetään `git status --porcelain --untracked-files=no`; jäljittämättömät tiedostot
  (generoidut suunnitelmat) pysäyttivät ketjuja hiljaa, joten jokaisen ketjun alkuun tulee `git status -sb`. (2) Avustajan komennoissa ei
  paikkamerkkejä (`TIEDOSTO`-esimerkki kaatui) vaan oikeat nimet. (3) Isäntäskriptien muutokset toimitetaan täsmäkorvausskriptinä, joka hylkää
  koko muutoksen, jos jokin kohta ei löydy täsmälleen kerran, ja uusi testitiedosto samassa paketissa. (4) Koesarjan aikana ei committata
  eikä pullata (ajot lukevat `git archive HEAD`). (5) Pitkät ajot tmuxissa. (6) Shell-skripteissä `set -o pipefail` ja `… | grep -q` antavat vääriä virheitä (grep sulkee putken): tallenna tuloste ensin muuttujaan.
- **Opitut käytännöt 12.–13.10.:** (1) Purku- ja commit-lohkot ovat yksi vartijoitu ketju (`… && … || echo "PYSÄHTYI"`) tai `( set -e …; echo "N …" )`
  -lohko, joka kertoo, mihin kohtaan se pysähtyi; erilliset rivit jatkoivat puuttuvan arkiston jälkeen (kahdesti: arkisto oli lataamatta).
  Pohja tarkistetaan yhdistetyllä tiivisteellä (`sha256sum TIEDOSTOT | sha256sum`) ennen purkua ja sen jälkeen. (2) Arkistojen aikaleima
  menneisyyteen (tulevaisuuden aikaleima antoi tarin varoituksen). (3) Päivämäärä järjestelmän kellosta, ei oletuksesta (korjaukset
  merkittiin ensin 13.10., vaikka ne tehtiin 12.10.; korjattu PR #19:ssä). (4) Puhelimen sivu päivittyy vasta ajon seuraavalla askeleella:
  paina kerran ja päivitä (vahinkopainallus ohitti pätkän; toistosuoja). (5) Ennen yöajoa Discord kiinni. (6) PR:n komennot kirjoitetaan
  `gh`:lle haaran nimellä (`gh pr merge HAARA …`), jolloin numeroa ei tarvitse arvata. (7) Solin tuomiot tarkistetaan koodia vasten ennen
  korjauksia (12.10.: 2 T aitoja, yksi E-väite oli väärä). (8) T1-luonnos otetaan käyttöön kahtena committina (luonnos sellaisenaan ja
  tarkistuksen korjaukset), jotta näkyy, mitä Ilmari kirjoitti itse.

## Mitatut faktat

- **Matriisitulo n = 8192:** GPU FP64 1,7, FP32 74, TF32 115 ja BF16 240 TFLOPS. CPU FP64 0,74 TFLOPS.
- **Cholesky n = 8192:** FP32 epäonnistuu jitterillä 1e-6 ja onnistuu jitterillä 1e-3. FP64 onnistuu (0,11 s GPU:lla, 0,32 s CPU:lla).
- **Tarkan GP:n raja FP64:llä:** noin 60 000 pistettä (29 Gt) ja noin 43 s.
- **Satunnaiskenttä 4096²:** 4 ms GPU:lla ja 220 ms CPU:lla. Menetelmän virhe 0,001.
- **Teho:** tyhjäkäynnillä noin 22 W, kuormassa 575 W (silent).
- **Dispatcherin kovennus:** systemd-analyze security 8,3 → 1,4.
- **Vaiheet 5g ja 6:** aikaraja, SIGKILL ja recover(), uudelleenkäynnistys, politiikka ja allekirjoitettu hyväksyntä todennettu (työt 11–17).
- **Vaihe 7 (30.9.):** aiops-gw pystyi ilman palvelun kovennusta lukemaan kaikki kolme datahakemistoa. Uvicorn 0.54 antaa soketille tilan 0666 (lähdekoodi ja testi).
- **Vaihe 7b (1.10.):** gatewayn systemd-analyze security 0,8 (OK). Palvelussa CapBnd 0, NoNewPrivs 1, Seccomp 2; palvelun sisältä aiops-gw saa hakemistosta restricted Permission denied, mutta lukee työhakemistot (E1). elias ei pääse sokettiin (Errno 13). Rootina sokettiin: ilman tunnusta 403, oikealla 200, väärä Host 421, POST 405.
- **Vaihe 7b-2 (1.10.):** Serve lähettää sokettiin Host: localhost ja nimen otsakkeessa X-Forwarded-Host. Se korvaa väärennetyt X-Forwarded-Hostin ja Tailscale-User-Loginin ja lisää X-Forwarded-For (lähettäjän tailnet-osoite) ja X-Forwarded-Proto: https. Korjauksen 7b-3 jälkeen /kuka toimii Serven kautta myös väärennöksillä.
- **Varianssin tarkistus (1.10., suljettu):** 32 kentän keskivarianssin keskihajonta toruksella ℓ = 0,1 on 0,031 kun ν = 0,5, ja 0,040 kun ν = 2,5 (laskettu tarkasti spektristä: Var = 2 Σ S(k)² / M²). Yksi kenttä vastaa noin 63:a (ν = 0,5) tai 38:aa (ν = 2,5) riippumatonta havaintoa, vaikka pisteitä on 16,8 miljoonaa. Aiempi 0,939 on z = −1,9, siemen 7 (työ 18) antoi 1,012 (z = +0,4) ja 1,011 (ν = 2,5). Yhdessä z = −1,1, eli poikkeama oli otantavaihtelua. Menetelmän virhe 0,001.
- **Vaihe 7c (1.10.):** ensimmäinen lomake puhelimesta hylättiin, koska Referrer-Policy no-referrer sai Chromen lähettämään Origin: null. Toistettu Chromiumilla ja korjattu (7c-3). Korjauksen jälkeen työ 18 (satunnaiskenttä, siemen 7) jätettiin puhelimesta ja valmistui, työ 19 jäi odottamaan hyväksyntää ja hylättiin puhelimesta, ja väärennetty lomake Serven kautta sai vastauksen 403 eikä luonut työtä.
- **Vaihe 7d-1 (1.10.):** WebAuthn ES256 -tarkistin ja 26 testiä. Sallittu suunta sekä väärä avain/käyrä/allekirjoitus, type, haaste, origin, crossOrigin/topOrigin, rpIdHash, UP/UV, varatut liput, AT/ED, BS ilman BE, väärä pituus ja epäkelpo JSON testattu. Riippumattomana totuutena W3C Level 3 §16.6 -vektori. Eliaksen koneella uv 0.10.11:llä kohdistettu sarja 26 passed ja koko sarja 396 passed, 1 skipped. Commit `05cd63b`.

- **Vaihe 7d-2 (1.10.):** c424a20 asennettu klo 19.01.54. Gateway pysäytettiin ennen dispatcheria, deploy jätti molemmat pysäytetyiksi. Dispatcher käynnistettiin ensin; ensimmäinen välitön kannan tarkistus näki vielä skeeman 2, mutta myöhempi tarkistus ja dispatcherin käynnistysviesti vahvistivat skeeman 3. Tämä oli tarkistuksen ajoitus, ei havaittu migraatiovirhe. Live-tarkistus: integrity ok, viitteet tyhjät, rivit 19/74/2 ja ehdokkaat 0, Ed25519-oletukset kunnossa. Gateway --check läpäisi ennen käynnistystä; molemmat palvelut active. systemd active ei yksin todista sovelluksen valmiutta.

- **Vaihe 7d-3 (2.10.):** cc6c061 asennettu klo 23.54.22. Ennen asennusta uuden koodin RP ID -luku oikeaa aiops.toml:ia vasten antoi `('tyoasema.taild1a5b7.ts.net', None)`, ja aiops-run pystyi lukemaan tiedoston. Käynnistysviesti: `hyväksyjät: elias (ed25519); WebAuthn RP ID: tyoasema.taild1a5b7.ts.net`. Regressiotesti: työ 20 → awaiting_approval → `aiops approve` → hyväksyntä #3 (ed25519) käytetty → succeeded, exit 0 (13 s); allekirjoituksesta kontin käynnistykseen noin sekunti. WebAuthn-reittiä ei voi vielä kokeilla livenä, koska puhelimen avainta ei ole asennettu.

- **Vaihe 7d-4 (3.10.):** d26974e asennettu klo 00.35.59. Pixel 10a:n Chrome loi passkeyn Google Password Manageriin, antoi julkisen avaimen getPublicKey-kutsulla, UV oli päällä ja credential ID 16 tavua. Ehdokas #1 tallentui klo 00.36.43 (44 s asennuksesta). Sormenjälki `655a … 51d4` täsmäsi puhelimessa, `aiops passkeys`-tulosteessa ja /usr/bin/openssl + sha256sum -laskussa. Avain asennettiin vertailun jälkeen; käynnistysviesti klo 00.37.41: `hyväksyjät: elias (ed25519), elias-puhelin (webauthn)`. Chromium varoittaa konsolissa, että RS256 puuttuu algoritmilistasta; tarkoituksellinen (vain ES256).

- **Vaihe 7d-5 (4.10.):** 58cd1eb asennettu klo 22.37.35. Työ 21 jätettiin puhelimesta klo 22.38.00, hyväksyntäsivu avattiin klo 22.38.12, puhelin valitsi passkeyn itse ja allekirjoitti sormenjäljellä, dispatcher hyväksyi #4 klo 22.38.20 (8 s sivun avaamisesta) ja työ valmistui klo 22.38.34, exit 0 (13 s). UP ja UV todettu oikealla puhelimella (dispatcher ei hyväksy muuta). Negatiivinen kontrolli: #4:n tavut kopioitiin samanlaiselle työlle 22 (sama tiiviste e5d56b589abd…) riviksi #5 → klo 22.40.28 `hylätty: WebAuthn-haaste ei täsmää`, työ pysyi odottamassa ja peruttiin.

- **Vaihe 7e (4.10.):** mobiiliverkko (Wi-Fi pois): työ 23 jätettiin klo 22.57.27, `tailscale status` näytti pixel-10a:lle `active; direct` operaattorin julkiseen osoitteeseen (ei lähiverkkoa, ei DERP:iä), hyväksyntä #6 käytetty klo 22.57.50 (6 s sivun avaamisesta), työ valmis. Laite pois tailnetistä klo 23.01: puhelimen pyyntö jäi ilman vastausta, ilman Tailscalea nimi ei ratkennut; takaisin klo 23.03 samalla osoitteella, siirtolaskurit nollautuneet, identiteetti ennallaan. Avain pois klo 23.06: aidot sormenjälkiallekirjoitukset #7 ja #8 → `hylätty: tuntematon hyväksyjä 'elias-puhelin'`. Avain takaisin klo 23.07 (sormenjälki asennetusta tiedostosta), #9 käytetty klo 23.08.07, työ 24 exit 0 (12 s).

- **Vaihe 8a-1, painot (5.10.):** Qwen3.8-27B:n manifesti haettiin kahdesti toisistaan riippumatta (identtinen). `hf download` 12 min 17 s, siirto 47,7 Gt (Xet), koottu 55,6 Gt (32 tiedostoa). Latauskopio ja root-kopio läpäisivät manifestitarkistuksen; viimeisen palan SHA-256 täsmäsi coreutilsiin. Ollama pysäytetty: portti 11434 suljettu. Isännän nemotron-3-nano:30b (`ollama show`): nemotron_h_moe 31.6B, konteksti 1M, Q4_K_M, NVIDIA Open Model License; ei käytetä.

- **Vaihe 8a-1, imaget (6.10.):** pohjaimagejen tiivisteet haettu kahdesti toisistaan riippumatta (Clauden ympäristö rekisterin rajapinnasta ja `docker buildx imagetools inspect`), identtiset. Käännös 140–143 s (16 rinnakkain). Ensimmäinen rakennus latasi oletuksena (LLAMA_USE_PREBUILT_UI=ON) selainkäyttöliittymän Hugging Facesta version "latest" (b11430:lle ei ollut omaa), ja tarkistussumma tuli samasta lähteestä; korjattu, llama-server pieneni 63 924 552 → 60 776 104 tavua. Savukoe kovennetussa kontissa: `version: 0.6.0-dev (build 11430, commit 8345f33)`, GNU 14.2.0, `CUDA0: NVIDIA GeForce RTX 5090 (32088 MiB, 30939 MiB free)`, ldd: ei puuttuvia, ei libssl:ää eikä libnccl:ää. Muunnosimage: torch 2.11.0+cpu, transformers 4.57.6.
- **Ennakkokokeet Clauden ympäristössä (5.–6.10.):** muunnoksen kuivaharjoitus oikeilla tokenisaattoritiedostoilla ja safetensors-otsakkeilla (harvat tiedostot) antoi 851 tensoria ja 53,8 G `--no-mtp`-valinnalla (866 ja 54,6 G MTP:n kanssa). llama-server CPU-käännöksenä Unix-soketissa: ei TCP-kuuntelijaa; soketin tila umaskin mukaan (022 → vain omistaja, 007 → ryhmä); SIGTERM jättää sokettitiedoston, ja uusi käynnistys samaan polkuun kaatuu (`couldn't bind HTTP server socket`). Ilman käyttöliittymää GET / → 404, /health toimii.
- **Muunnosimagen kaatuminen (6.10.):** käyttäjä 10001 ilman passwd-riviä → torch kysyy käyttäjänimeä välimuistihakemistoa varten → `KeyError: getpwuid(): uid not found: 10001` ennen ensimmäistä tensoria. Toistettu Clauden ympäristössä, korjattu USER=aiops ja TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor.
- **BF16-muunnos (6.10.):** klo 00.21.27–00.23.04 (1 min 37 s, kirjoitus 581 Mt/s), 851 tensoria, 53,8 G, 53 808 282 112 tavua. Vertailu llama.cpp-projektin BF16:aan: kaikki 851 tensoria ja 1847 näytettä täsmäsivät; ainoa metatietoero `tokenizer.ggml.add_eos_token` vain meidän tiedostossa (selittää +64 tavua). Varoitukset `Transformers does not recognize this architecture` ja `Unknown RoPE type: default` ovat odotettuja (muunnin lukee config.jsonin).
- **Q4_K_M (6.10., tarkistettu):** kuivaharjoitus 851/851, quant size 15 770,35 MiB (4,92 BPW), 109,88 ms. Kvantisointi commitista `a9dacef` (commit 01.18.34, ajo 01.21.08–01.24.33), llama-quantize 160,7 s CPU:lla 8 säikeellä, model size 51 305,09 MiB (16,00 BPW) → 15 770,35 MiB (4,92 BPW). Tiedosto 16 547 400 192 tavua, SHA-256 `95151662…3920` (skriptin alkupera.tsv ja Eliaksen erillinen sha256sum täsmäsivät). Tyypit: 353 F32 (normit ja pienet), 433 Q4_K, 65 Q6_K (mm. attn_v ja osa ffn_down-kerroksista); ei BF16:ta. Nimet ja muodot = ggml-org-viite. BF16 ennallaan.
- **Q6_K (6.10., tarkistettu):** kuivaharjoitus 851/851, quant size 21 049,06 MiB (6,57 BPW), 113 ms. Kvantisointi commitista `e37e9eb` kahdesti peräkkäin (vahinko): 15.40.12–15.42.24 ja 15.43.28–15.45.44, llama-quantize 91,8 s (nopeampi kuin Q4_K_M:n 160,7 s, koska Q4_K hakee lohkojen skaalat iteratiivisesti). Kummassakin 22 082 529 792 tavua ja SHA-256 `e45467ca…9cca` (alkupera.tsv ja Eliaksen erillinen sha256sum täsmäsivät): **kvantisointi on toistettava tavulleen** samalla imagella, syötteellä ja komennolla (8 säiettä). Tyypit: 353 F32 ja 498 Q6_K (ei tyyppisekoitusta). Nimet ja muodot = ggml-org-viite. BF16 ennallaan.


- **PR #11 ja credential (6.10. tulosteet):** PR yhdistetty,
  main/origin/main tuolloin `5628b20` (nyt `10775e2`), paikallinen q6k-haara poistettu. OpenAI-credential
  root:root 0600 / 754 tavua; salauksen purku ja GET /v1/models onnistuivat,
  133 mallia ja `gpt-6.1-sol: True`. Mallin generointia tai agentin API-reittiä
  ei kokeiltu. systemd ilmoitti koneavaimen olevan salaamattomalla levyllä;
  ilmoitus ei tarkoita, että credential-tiedosto olisi tallennettu selväkielisenä.

- **GGUF-root-kopio (6.10., Eliaksen tulosteilla tarkistettu):** commit `8dcbcae`,
  ennakkotarkistus ja asennus läpäisty, kokonaisaika 1 min 50,207 s. Root:root
  0755/0644, kaksi GGUF:ää yhteensä 38629929984 tavua; erilliset sha256sum-arvot
  täsmäsivät manifestiin ja manifestitarkistus läpäisi. Täydet tiivisteet ovat alussa.
  Tämä todistaa root-kopion eheyden ja omistukset; GPU-inferenssiä ei vielä kokeiltu.

- **GPU-pilotti ja yöluenta (6.–7.10.):** mittaukset, löydökset ja tarkistustilastot on koottu kohtaan "GPU-pilotti ja
  yöluenta (6.–7.10.2026)" yllä.

- **8.10. mittaukset:** IQ3_S-nopeus ja VRAM sekä Sol-tarkastuksen kulut ja tuomiojakaumat on koottu kohtaan "Istunto 8.10.2026".

## Tila

Valmiit vaiheet: 1–6, 7a–7e (**vaihe 7 valmis**: hyväksyntä puhelimella sormenjäljellä kodin ulkopuolelta, hyväksyntävallan voi perua kahdella toisistaan riippumattomalla tavalla). ADR-0008 ja ADR-0009 hyväksytty. **8a-1 tehty** (painot, llama.cpp-imaget, Q4_K_M ja Q6_K, root-kopio; PR #12 yhdistetty 6.10.; GPU-pilotti ajettu). **8a-2:n esikoe tehty** (yöluenta T0, tarkistus Sol-tarkastajalla). **8b-1:n koodi tehty ja ajettu** (`budget.py`, `sol_tarkasta.py`, `yo_sol.sh`) isäntäskriptinä; välittäjäpalvelu (systemd) ja agenttikytkentä ovat tekemättä. ADR-0011 hyväksytty 12.10. (versio 5). Koesarja ajettu. **8a-3d valmis** (puhelinohjaus: gateway, yöajon ohjeluku ja tilatiedosto, pysäytysten oma raja; asennettu 58f5443, todennettu puhelimella ja yöajossa 12.10.). **ADR-0011 hyväksytty 12.10. (versio 5).** **T1 väliaikaisesti yöajossa** rakennettu ja live-testattu 13.10. (PR #22). PR #15 (ML) ja #13 (Ilmari-ready) odottavat.

**7.10. päivitys:** 8a-1 on tehty (root-kopio yhdistetty, GPU-pilotti ajettu). Käynnissä on 8a-2:n esikoe (yöluenta, T0, vain
luku) ja ADR-0011 on luonnoksena. Agenttikytkentää ei ole.

**8.10. päivitys:** budjettiydin ja Sol-tarkastaja valmiit; ensimmäinen pätkitetty yöajo korjatulla harnessilla ajettu ja
tarkistettu; IQ3_S mittausvalmiina; ajattelun säätö koodissa; Ilmari-ready-luonnos PR #13:ssa.

## Seuraavat vaiheet

1. **Nyt (13.10., aloita tästä):** (a) yhdistä PR #22 (T1) ja MUODOT-PR, jos ne ovat yhdistämättä (`gh pr list`); (b) vie tämä TILANNE.md repoon
   omalla haarallaan ja PR:llä; (c) poista yhdistetyt paikalliset haarat (lista kohdassa "Nykyinen lähtötila").
2. **Selaimen määrittely (ennen koodia):** kirjoitetaan `docs/valmistelu/` tai oma ADR. Sisältö: julkaisuhakemisto `/srv/aiops/ilmari/ajot`
   (yöajo ja `yo_sol.sh` kopioivat raportti.md:n, meta.json:n, ehdotukset.jsonl:n, sol-tulos.json:n ja luonnos.patch:n; ei työkopiota;
   ryhmä aiops lukee, koko rajattu), palvelukäyttäjä (oma, ryhmä aiops, `ProtectHome`, ei verkkoa, gatewayn kovennukset), osoite ja
   käynnistystapa Ilmari-ready-sopimuksen mukaan (Tailscale Serve, ei Funnelia, ei `docker -p`), tunnistus (Tailscale-tunnus sallittujen
   listalta kuten gatewayssa), polkuparametrin tiukka muoto (`^\d{8}-\d{6}-yo-[a-z0-9]+$`) ja luku `dir_fd`:llä, kokorajat (loki ja diff),
   raportti tekstinä (ei Markdown-riippuvuutta). Pohjana MUODOT.md ja SUUNNITELMA.md:n rakenne (korjattuna). Isäntämuutos ja muutoslokimerkintä.
3. **PR #13 (Ilmari-ready):** katselmointi ja päätökset C1, C3, C5, C7 ennen selaimen määrittelyä tai sen osana.
4. **Selaimen toteutus T1:llä:** Ilmari kirjoittaa määrittelyn pohjalta yöajossa (`kirjoitus = ["apps/ilmari-selain"]`); Claude ja Elias
   tarkistavat diffin, testit ajetaan (Elias, koska T2 puuttuu), sitten asennus erillisenä palveluna. Sol-tarkastus T1-luonnoksille vaatii,
   että tarkastaja lukee työkopiota tai luonnoshaaraa (nyt se lukee repoa).
5. **Koesarjan tulokset ja malli:** digest ja T-löydöt, IQ3_S 65 536 -ajon tulos, päätös IQ3_S:stä, ajattelusta ja kontekstista; ohjaa
   tehtäväsarjaa (8a-3c).
6. **PR #15 (ML-ajoympäristö):** vasta kun lukitus, rakennus ja PR:n vaiheet 1–11 on ajettu ja `headRefOid` tarkistettu.
7. **8a-3a:** käyttäjä `aiops-ceo`, agenttisoketti (SO_PEERCRED), luku- ja ehdotustoiminnot; samalla T1 siirtyy käyttöjärjestelmän rajaamaksi
   (päätös 6). **8a-3b:** mallityö dispatcherissa ja istuntotaulu (skeema 5). **8a-3c:** tehtäväsarja (vähintään 30 skenaariota) ennen
   agentin käyttöönottoa ja T2:ta.
8. **8b-1, jäljellä:** Sol-tarkastaja isäntäskriptinä vai välittäjäpalvelu; tarkastajan deterministiset tarkistukset ja PR-diffit. **8b-2:**
   johtajien yhteistyö. **8c:** yksityisiä rivejä nähneiden istuntojen lähtevät viestit ihmisen allekirjoitetulla hyväksynnällä.
9. **Myöhemmät kokeet (Eliaksen ehdotukset 12.10.):** järjestys (1) KV-välimuistin kvantisointi llama.cpp:ssä (esim. q8_0; vain lippu, ei uutta
   mallia eikä imagea; mitataan VRAM, nopeus ja laatu), (2) MTP (vaatii mallin ennustuskerrokset ja moottorin tuen; V1 muunnettiin
   `--no-mtp`), (3) TurboQuant-tyyppinen KV-tiivistys verrattuna kohtaan 1, (4) NVFP4 ja vLLM yhdessä (uusi image PR #15:n prosessilla,
   uudet painot karanteeniin; hyöty lähinnä rinnakkaisille agenteille). Tuki RTX 5090:llä ja moottoreissa tarkistetaan lähteistä ennen kokeita.
10. **Ravintopolku ja muut sovellukset:** erillinen palvelu Ilmari-ready-sopimuksen mukaan; ei agentin kautta ennen 8c:tä.
11. **Laaja 8a-2-vertailu myöhemmin:** laajempi tehtäväsarja, haastajamallit, perplexity-koe. Managerit, missions-työt, muistikerros ja
    Ilmari wrapped ovat myöhempiä kokonaisuuksia (VISIOT.md on ei-sitova).

## Avoimet asiat

- **Puhelinohjaus, jäljellä (13.10.):** vahvistussivu Pysäytä- ja Ohita pätkä -napeille (toistosuoja lieventää, ei poista); ohituksen
  sitominen sivulla näkyvään pätkään (gatewaymuutos), jos toistosuoja ei riitä; sarjan väliin (Sol-tarkastuksen aikana) painettu Pysäytä ei
  vaikuta seuraavaan ajoon; REPLACE-aukko vanhoissa tauluissa (`events`, `approvals`, `passkey_candidates`) omalla migraatiollaan;
  pysäytys ei keskeytä käynnissä olevaa mallivastausta eikä mallin latausta (viive enintään yksi vastaus).
- **T1 (väliaikainen, 13.10.):** rajaus on koodia, ei käyttöjärjestelmän pakottama (riski kirjattu ADR-0011:een); ei testien ajoa (T2); Sol ei
  näe luonnosta; malli tekee suunnitelmissa virheitä, jotka ristiriitaisivat sen omien dokumenttien kanssa (SUUNNITELMA.md), joten jokainen
  luonnos tarkistetaan ennen käyttöönottoa. Poikkeama päätöksestä 6 voimassa kunnes 8a-3a.
- **Solin tuomio 12.10. #4 (E):** `aja_patkat`:n kokonaisaikarajan haara on testattu vain väljästi (vanhaa koodia, ei 8a-3d:n).
- **PR #15, avoimet:** lukon sha256 (`a946658e…`) isännällä, `RUN --network=none` ja BuildKit, `/tmp`-liitoksen `noexec`, torch 2.14.0 vs 2.14.1,
  `aiops/py-gpu:1`:n CUDA 13.4 -osat, kokeen koodin toimitus (oma ADR), session kesken oleva katselmointi (uudet commitit).
- **Sol-tarkastaja, rajat:** tuomioluokat vahvistettu ADR-0011:een 12.10. Tarkastaja näkee vain otteet (katkaistaan 12 000 tavuun, mikä
  selittää osan E-tuomioista); kaksi mallia samaa mieltä ei ole riippumaton todiste; 16/24 tuomiota (8.10.) on tarkistamatta lähteistä.
  Tarkastus ei kata PR-diffejä eikä T1-luonnoksia.
- **OpenAI:** kuukausittaisen 10 €:n kovan rajan (hard limit) jakso ja kovuus tarkistamatta; datan säilytys: ei ZDR:ää eikä MAM:ia,
  abuse monitoring -lokit 30 pv. Repon tiedostojen otteet lähtevät Solille (ADR-0011 kohta 3: julkista); US-sijainti on Eliaksen päätös 8.10.
  (kirjattu ADR-0011:een).
- **`sudo`-aikaleiman hengissäpito:** `yo_sol.sh` pitää aikaleiman yllä koko ajon ajan; tämä on tietoinen turvakompromissi ja pätee
  vain, kun terminaali on Eliaksen hallinnassa.
- **IQ3_S:** tekijöiden benchmarkit eivät ole riippumattomia eivätkä mittaa työkalukutsuja, pitkää kontekstia tai suomea;
  `mmproj` (kuvat) ei ladattu; hyväksyntä koordinaattoriksi vasta 8a-3c:n ja koesarjan jälkeen.
- **Ajattelu:** `max_tokens`, lämpötila ja budjetti ovat valintoja, joiden vaikutus on mittaamatta; ajattelun suosituslämpötila (1,0)
  ja harnessin 0,4 ovat omat ajonsa.
- **Pilvikrediitit:** vanhenemispäivä (uutislähteiden mukaan 5.11.) ja ehdot varmistamatta; "Ultracode" ei ole tunnistettu termi
  tässä aineistossa.
- **Ilmari-ready (PR #13):** viitteiden pistokoe, päätökset C1, C3, C5, C7 ja ADR-0001/0002:n tarkennus (credentials-hakemisto vain
  rootille ja välittäjälle; TILANNE.md:n mukaan hakemisto on root:root 0700).
- **Ravintopolku:** erillisen palvelun asennus ja yksityisyys (paino- ja ruokadata on terveysdataa; OpenAI-luonnokset vain tietoisella päätöksellä).
- **Rinnakkaiset tekoälytyökalut (6.10., uusi työtapa):** Elias hoitaa Git-toimet ja
  isäntämuutokset. Avustajat valmistelevat ja tarkistavat. Totuus on repossa; tämän
  tiedoston päivitys toimitetaan tarkastettavana kokonaisena tiedostona Eliaksen
  commitointia varten. Yhdistäminen vain tarkistetusta kärjestä (`--match-head-commit`).
- **OpenAI-credentialin kirjaus:** tallennus ja mallilistakoe on lisätty toimituksen
  täydelliseen docs/muutosloki.md:hen. Ne ovat aiemmin Eliaksen tekemä isäntämuutos;
  tämä päivitys ei käytä tai muuta avainta. Valmistelukirjaus sisältyi Eliaksen
  kuuden tiedoston committiin `8dcbcae`. Root-kopion tuloskirjaus on tehty: se kirjattiin muutoslokiin PR #12:n dokumentointicommitissa `df64264` (ei ajocommitissa `8dcbcae`).
- **Ilmarin oma kehitystyö:** T0 (vain luku) ja T1 (väliaikaisesti yöajon työkopioon, `apps/`-hakemistoihin) käytössä. T2 (testien ajo)
  vaatii T1:n ja tehtäväsarjan (8a-3c); T3 (diff ja testitulokset); T4 ei koskaan (repo, commit, deploy, politiikka, avaimet, oma istunto,
  johtaja, budjetti). ADR-0011 hyväksytty 12.10.
- **Yöajon 7.10. tulos tarkistettu:** ks. kohta "Pätkitetty yöajo 7.10." Pätkät 4 ja 5 jäivät silloin ajamatta (katkennut kutsu kaatoi ajon;
  korjattu; ajettu uudelleen 8.10., ks. "Istunto 8.10.2026"). Ehdotusten laatu: 4/9 virheellinen väite, vain aukko 6 ja toteutuslista 7 hyödyllisiä.
  Kontin pysäytys ja siivous ajon lopussa tarkistamatta (komento: `sudo docker ps -a`, `ls /srv/aiops/mallityo`); sama tarkistus on tekemättä 8.10. ajojen jälkeenkin.
- **Mallin ehdotusten tarkistus:** deterministiset tarkistukset (tiedostohaku, testikattavuus `coverage`-työkalulla) ja Sol-tarkastus
  (ADR-0011 kohta 8) ennen kirjausta; "testi puuttuu" -väite tulee todentaa kattavuudella (7.10. väite osoittautui vääräksi).
- **README.md vanhentunut:** Tila-lista näyttää vaiheet 2–8 tekemättöminä, vaikka vaiheet 1–7 ovat valmiita. Päivitä tai poista lista.
- **Umask ilman käärettä kontissa mittaamatta:** kääre `umask 007` on todettu toimivaksi; ilman sitä soketin tilaa kontissa ei mitattu.
- **Palvelimen prompt-välimuisti:** `llama-server` pitää RAM-välimuistia (lokissa varoitus noin 7,7 GiB:n poistosta); kontin
  muistiraja 32 g sisältää mmap-sivut ja tämän. OOM-käytöstä ei ole mitattu.
- **Kontin pysäytys yöllä:** `sudo -n` ei onnistu yli 15 minuutin ajon jälkeen; kontti päättyy itse `timeout`-komennolla ja
  palvelin vapauttaa VRAMin 15 min joutenolon jälkeen (`--sleep-idle-seconds`, dokumentoitu, mittaamatta).
- **Päällekkäisyyssuodattimen raja-arvot:** valittu 15 ehdotuksen aineistosta; tarkista, kun ehdotuksia on enemmän.
- **Haarojen siivous:** `vaihe-8a1-rootkopio` (paikallinen ja etä) voi poistaa PR #12:n yhdistämisen jälkeen; 13.10. yhdistetyt paikalliset ja etähaarat: ks. Nykyinen lähtötila.
- **gh 2.45.0** (Ubuntun paketti) on vanha, ja `gh pr view` kaatuu ilman `--json`-valitsinta. Uudempi versio
  vaatisi GitHubin oman apt-lähteen (uusi pakettilähde = toimitusketjupäätös), joten se tehdään harkiten omana
  kirjattuna muutoksenaan. Siihen asti `--json`.
- **Docker-siivous:** kolme vanhaa hello-world-konttia (Exited, 14 kk) sekä vanhat imaget open-webui (4,78 GB), nvidia/cuda:12.1.0-base-ubuntu22.04 ja hello-world
  sekä rakennusvälimuisti (`sudo docker builder prune`; CUDA-kehitysimage noin 9 Gt). Kirjattuna muutoksena.
- **GGUF-työhakemisto:** /srv/aiops/mallityo poistetaan, kun lopulliset tiedostot on kopioitu ja mitattu. Samalla kotihakemiston kvantisointilokit (~/aiops-q4_k_m-*), kun niiden tieto on muutoslokissa.
- **Varmistusten jatko (ADR-0008, valinnainen):** haarasuojaus mainille (force push ja poisto estetty; yksityisessä repossa vaatii GitHub Pron) tai toinen repokopio laitteelle, johon työasema ei voi kirjoittaa. Raspberry Pi mahdollinen, kun säilytettävää dataa syntyy.
- **Isännän Ollama:** pois käytöstä 5.10. Ohjelma (0.13.5, hyvin vanha; uusin vakaa 0.34.3, 19.9.2026),
  käyttäjä ollama ja vanhat mallit (noin 145 Gt) ovat yhä koneella. Poistetaan omana kirjattuna muutoksenaan,
  kun on selvää, ettei niitä tarvita. Jos Ollama otetaan joskus käyttöön, sen palvelutiedostosta poistetaan
  PATH, joka sisältää eliaksen kotihakemiston polkuja (asennusskriptin perintö), ja ohjelma päivitetään.
- **Hugging Facen tiedostot kotihakemistossa:** ~/.cache/huggingface/hub (37 Gt, vanhempia latauksia) ja
  ~/.cache/huggingface/token (Hugging Face -tunnus). Alusta ei tarvitse tunnusta: julkiset mallit latautuvat
  ilman sitä, mutta huggingface_hub käyttää tallennettua tunnusta automaattisesti. Jos tunnusta ei käytetä,
  `hf auth logout`. Välimuistin voi tarkistaa ja siivota (`du -sh ~/.cache/huggingface/hub/*`).
- **Ilmari wrapped (idea, myöhemmin):** järjestelmä paketoituna niin, että sen voi asentaa toiselle laitteelle helposti, ja siihen käyttöliittymä. Toimisi samalla ADR-0008:n uudelleenrakennuksen todellisena kokeena.

- **Mallistrategia (ADR-0009, ennen vaihetta 8).** Ohjaaja yksi kerrallaan, erikoismallit imageina jonossa `--network none`. Päätettävä painojen säilytys (esim. /srv/aiops/models vain luku, vain safetensors) ja paikallinen LLM yksityiselle datalle vs. VRAM (pysyvästi muistissa oleva malli pitää probe_gpu():n varattuna). Reititys päätetään koodissa.
- **Satunnaiskenttädemon tuloste (valinnainen):** rivin "otantavaihtelu" luvut ovat kovarianssikäyrän suurin poikkeama, eivät varianssin keskivirhe. Demo voisi tulostaa myös keskivirheen (32 kentällä 0,031 kun ν = 0,5, ja 0,040 kun ν = 2,5).
- **ADR-0010:** tarkistuslista ja seuraukset käyty läpi (7e). Jäljelle jäävä hyväksytty riski: puhelin allekirjoittaa tiivisteen, ei näkemäänsä tekstiä; lievennykseksi V1.5:n riippumaton ntfy-ilmoitus. Google-tili on hyväksyntäketjussa (passkeyn synkronointi).
- **CLI:n muut tulosteet (valinnainen):** `aiops list` ja `aiops show` tulostavat kannan tekstikentät (spec.name, submitted_by, syyt) sellaisinaan. Kantaan voi kirjoittaa koko ryhmä aiops, joten sama ohjausmerkkien koodaus kuin `aiops passkeys`-komennossa olisi hyvä. Vain näyttö, ei valtaa.
- **Orvot kontit:** recover() käsittelee vain running-tilan työt. Parannus: tappaa käynnistyksessä myös tuntemattomat kontit, joilla on label aiops.job.
- **dispatcher.lock (tarkistamatta):** jos lukkotiedosto on ryhmän aiops luettavissa, kuka tahansa ryhmässä (myös gateway) voi ottaa flock-lukon, jolloin uudelleenkäynnistyvä dispatcher kieltäytyisi. Vain palvelunesto. Tarkistus: `ls -l /srv/aiops/db/dispatcher.lock`. Korjaus esim. lukko hakemistoon, johon vain aiops-run pääsee.
- **Jatkokovennus (valinnainen):** dispatcherille DevicePolicy=closed ja DeviceAllow vain /dev/nvidia*-laitteille. Gatewaylle PrivateUsers ja ProcSubset=pid. Ei kokeiltu.
- **Gatewayn näkymät:** GPU-tila puuttuu (gatewaylla ei ole laitteita). Mahdollisesti dispatcher kirjaa tilan kantaan.
- **Arkkitehtuuridokumentin kommentti** "Riittääkö V1:ssä pelkkä työlaatikko" on vastaamatta dokumentissa. Linja: työlaatikko, ei chattia (ADR-0010).
- **Varmuuskopio ~/aiops-ennen-6b.sqlite:** voi poistaa, kun 6b on toiminut jonkin aikaa.
- **Luke:** työnjohtajan linjaus henkilökohtaisista laitteista ja AI-palveluista on selvittämättä.
- **Harkittavat:** Ubuntu Pro ESM ja tehorajakoe, esim. 450 W.
- **Minecraft:** jouluna portti avataan tilapäisesti, `sudo ufw allow 25565/tcp`, ja suljetaan palvelimen jälkeen.
- **V1.5:** paikallinen LLM (ADR-0009), ntfy-ilmoitukset (myös: mitä hyväksyttiin, gatewaysta riippumatta), r-spatial-image, PostGIS, toistuvat työt, SIGHUP-uudelleenluku, mahdollisesti Open WebUI vain omaan koneeseen.
- **V2:** rootless Docker tai gVisor, Headscale ja pörssisähkön mukaan ajoitetut eräajot.
