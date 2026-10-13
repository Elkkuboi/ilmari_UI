# Ilmari-ready: sopimus sovellukselle Ilmarin rinnalla

- Tila: luonnos Eliaksen tarkistettavaksi, 8.10.2026. Tämä tiedosto ei muuta yhtään ADR:ää.
- Tarkoitus: ehdot, jotka sovelluksen on täytettävä, jotta Elias voi ottaa sen käyttöön työasemallaan Ilmarin (aiops) rinnalla.
- Lukijat: tekoälyavustaja (Claude Code tai Codex), joka rakentaa sovelluksen, eli **rakentaja**, ja Elias, joka tarkistaa työn.

## Miten tätä luetaan

- **Osa A** on sitova nyt. Sovellus, joka rikkoo A-kohtaa, ei ole valmis käyttöön.
- **Osa B** on ADR-0011:n luonnosta. Se **ei ole sitova eikä toteutettu**, joten sen varaan ei rakenneta.
- **Osa C** on Eliaksen päätettävä. Rakentaja ei ratkaise C-kohtia itse vaan kysyy.
- Merkintä **(alusta)**: lähde koskee nimenomaan aiops-alustan palveluita. Sitooko kohta sovellusta suoraan, ratkeaa kohdassa C1.
- Jos asiaa ei ole tässä eikä lähteissä, älä arvaa: pyydä vain luku -tuloste tai kysy (`AGENTS.md:15–16`).
- Poikkeaminen hyväksytystä ADR:stä vaatii uuden ADR:n (`AGENTS.md:12`, `AGENTS.md:24`).

**Lähteet.** Tämän repon haara `vaihe-8a2-yoluenta`, commit `d905b9b` (vastaa Eliaksen liittämiä tiedostoja; ei vielä mainissa).
ADR-0011 ja viitatut TILANNE.md:n rivit ovat siinä. AGENTS.md, README.md, ADR:t 0001–0010, koodi ja viitatut muutoslokin
rivit ovat samat kuin mainissa (`10775e2`). Viittaus
`TIEDOSTO:RIVIT` osoittaa rivit. Lyhenteet: `ADR-NNNN` = `docs/adr/NNNN-*.md`, `TILANNE` = `docs/TILANNE.md`, `MUUTOSLOKI` =
`docs/muutosloki.md`, `*.service` = `config/systemd/aiops-*.service`, `policy.hujson` = `config/tailscale/policy.hujson`,
`*.py` = `src/aiops/*.py`, `*.sh` = `scripts/*.sh`; `.gitignore` ja `pyproject.toml` ovat repon juuressa.

**Etusija.** ADR:t ja koodi ovat ensisijaisia. ADR-0011 on luonnos. TILANNE.md:n vanhentuneet kohdat ovat kohdassa C11.

## A. Voimassa olevat sitovat vaatimukset

### A1 Ajotapa ja oikeudet

- **A1.1** LLM ehdottaa, koodi päättää: oikeuksia, reititystä ja budjetteja valvoo koodi, jota malli ei voi muuttaa. — `AGENTS.md:13–14`, `README.md:8`
- **A1.2** Kontti ajetaan aina näin: `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges` ja käyttäjä
  10001, jolla ei ole tiliä isännässä. Lisäksi on muisti-, CPU- ja prosessirajat sekä aikaraja. — `AGENTS.md:29–30`, `ADR-0001:33–40`, `dispatcher.py:156–173`
- **A1.3** Ei koskaan `docker -p`, koska julkaistu portti ohittaa UFW:n. — `AGENTS.md:27`
- **A1.4** elias ei kuulu docker-ryhmään, ja Docker-komennot ajetaan käsin sudolla. Sovellus ei saa edellyttää eliaksen lisäämistä
  ryhmään. — `AGENTS.md:28`, `ADR-0001:28–29`
- **A1.5** Palvelu ei näe kotihakemistoa eikä pysty muuttamaan omaa koodiaan. Asennettu koodi on rootin hakemistossa, ja asennus
  vaatii sudon. — `ADR-0002:8–9`, `ADR-0002:17`, `ADR-0002:24–26`
- **A1.6** Hyväksyntävalta syntyy vain allekirjoituksesta (Ed25519 tai puhelimen passkey), jonka dispatcher tarkistaa root-omisteisella
  julkisella avaimella. Kirjoitusoikeus tietokantaan ei anna valtaa hyväksyä. — `ADR-0007:12–14`, `ADR-0007:18–19`, `ADR-0010:12–14`, `ADR-0010:29–32`
- **A1.7** (alusta) Politiikan tasot ovat AUTO, HYVÄKSYNTÄ ja KIELLETTY. Tuntematon toiminto on KIELLETTY, ja ainoa tunnettu on nyt
  `run_job`. Pyytäjää (`submitted_by`) ei käytetä säännöissä ennen kuin se on todennettu. — `ADR-0007:23`, `ADR-0007:30`, `policy.py:34–35`, `policy.py:66–69`, `ADR-0010:69–72`
- **A1.8** (alusta) Dispatcher ei luota jonoon vaan tarkistaa jokaisen työn uudelleen. Työmäärityksessä ei ole verkkoa, Docker-lippuja,
  ympäristömuuttujia eikä vapaita liitoksia. — `ADR-0002:50–51`, `spec.py:6–8`, `dispatcher.py:134–150`
- **A1.9** (alusta) Dispatcher ajaa vain sallittujen listan imageja. Puuttuva lista ei salli mitään, ja listan muutos on isäntämuutos. — `ADR-0001:31–32`, `dispatcher.py:124–131`, `MUUTOSLOKI:57–60`
- **A1.10** (alusta) Dispatcher on GPU:n ainoa omistaja, ja kaikki GPU:ta käyttävä kulkee sen kautta (`ADR-0009:63–65`, `ADR-0009:145`). VRAM-budjetti
  on kortin muisti miinus 2 GiB, kernelin on valmistuttava sekunneissa (`ADR-0006:17–20`), ja CUDA tulee imagesta, enintään 13.2 (`ADR-0005:16–18`, `ADR-0005:32`).
- **A1.11** Ulkopuolisen tahon koodi ajetaan kovennetussa kontissa, ja ADR-0001 tarkistetaan, kun sellaista tulee. — `ADR-0001:60`, `ADR-0009:151–152`

### A2 Verkko ja pääsy

- **A2.1** SSH-palvelinta ei asenneta V1:ssä. Tailscale SSH ja Tailscale Funnel ovat kiellettyjä. Ei porttiohjausta reitittimessä
  eikä julkista tunnelia. — `ADR-0004:14–17`, `ADR-0004:29`, `AGENTS.md:34`
- **A2.2** UFW on päällä, ja saapuvat yhteydet ovat oletuksena kiinni. — `ADR-0004:18`, `MUUTOSLOKI:6`
- **A2.3** Tailscale päästää tailnetin liikenteen ennen UFW:tä, joten tailnetissä ainoa suodatin on Tailscalen politiikka. Se päästää
  omat laitteet työasemaan vain porttiin tcp:443, eikä työasema saa avata yhteyksiä muihin laitteisiin. — `ADR-0004:38`, `policy.hujson:2–12`, `ADR-0010:24`
- **A2.4** Tailscale Serve julkaisee portin 443 vain tailnetiin ja ohjaa sen gatewayn Unix-sokettiin. — `ADR-0010:43–44`, `TILANNE:321`
- **A2.5** (alusta) Gateway ja dispatcher ovat verkottomia (`PrivateNetwork=yes`, `RestrictAddressFamilies=AF_UNIX`). Ulospäin
  suuntautuva HTTPS on päätetty vain erilliselle välittäjälle, jota ei ole vielä toteutettu. — `ADR-0010:45–47`, `gateway.service:43–45`,
  `dispatcher.service:43–45`, `ADR-0009:92–94`, `TILANNE:16–17`
- **A2.6** (alusta) Alustan palvelut eivät käytä isännän Ollamaa eivätkä yllä siihen, koska pääsy Ollamaan on käytännössä pääsy
  verkkoon. — `ADR-0009:27–30`, `ADR-0009:87–88`
- **A2.7** (alusta) Gatewayn sivuilla GET ei muuta mitään, ja POST hyväksytään vain omalta alkuperältä (Origin, Sec-Fetch-Site). Osoite tarkistetaan,
  CSP sallii vain oman alkuperän, JavaScript tulee reposta eikä CDN:stä, ja Funnel-otsake hylätään. — `ADR-0010:36–38`, `ADR-0010:80–85`, `ADR-0010:204–212`, `ADR-0010:219–220`

### A3 Data ja luokat (ADR-0003)

- **A3.1** Datan luokka on hakemisto: `public`, `private` tai `restricted` hakemistossa `/srv/aiops/data/`. — `ADR-0003:13–19`, `ADR-0002:21`, `spec.py:24`
- **A3.2** Ulkoiseen API:in public-datasta saa viedä kaiken budjetin sisällä. Private-datasta skeemat ja koodin laskemat yhteenvedot
  ovat AUTO, mutta rivit ja otokset vain hyväksynnällä. Restricted-datasta ei mitään, ei edes yhteenvetoja. — `ADR-0003:15–19`
- **A3.3** Luokkaa ei voi muuttaa järjestelmän kautta, vaan ihminen siirtää aineiston käsin. — `ADR-0003:21–22`
- **A3.4** Luonnonvarakeskuksen (työnantajan) dataa ei tuoda järjestelmään ennen työnantajan linjausta. Linjaus on yhä
  selvittämättä. — `ADR-0003:23–24`, `AGENTS.md:35`, `TILANNE:608`
- **A3.5** Restricted-datasta näytetään vain tiedostojen nimet ja koot. Restricted-dataa käyttävä työ vaatii hyväksynnän. — `ADR-0010:97–98`, `ADR-0007:24–26`, `policy.py:61–62`
- **A3.6** Datahakemistot ovat elias:aiops 2750. Kontit saavat ne vain luku -liitoksina, eikä datapolku saa osoittaa luokkansa
  ulkopuolelle. — `ADR-0002:21`, `ADR-0002:52–54`, `spec.py:61–70`, `dispatcher.py:142–149`
- **A3.7** Ryhmän aiops jäsen näkisi kaiken datan, joten gatewaylta data on piilotettu (`InaccessiblePaths`). — `ADR-0010:22–23`, `ADR-0010:48–49`, `gateway.service:41`
- **A3.8** Restricted-dataa ei kopioida pilveen, ei myöskään varmuuskopioina. — `ADR-0008:45–46`

### A4 Salaisuudet

- **A4.1** Salaisuuksia ei viedä koskaan chattiin eikä repoon. `.gitignore` torjuu mm. `*.key`, `*.pem`, `.env` ja `credentials/`. — `AGENTS.md:31`, `ADR-0008:42–43`, `.gitignore:1–7`
- **A4.2** Hyväksyjän yksityistä avainta ei lueta, pyydetä eikä näytetä koskaan, eikä sitä anneta agentille. — `AGENTS.md:32–33`, `ADR-0007:41–42`, `ADR-0007:57–58`
- **A4.3** API-avain on salattuna systemd-credentialina hakemistossa `/etc/aiops/credentials` (hakemisto 0700 root, tiedosto 0600).
  Elias syötti sen piilotetussa kehotteessa. Koordinaattori (CEO) ei näe avainta. — `ADR-0009:92–94`, `ADR-0002:52–53`, `MUUTOSLOKI:247`
- **A4.4** Salaisuuksia ei varmisteta: niiden menetys hyväksytään, ja ne luodaan uudelleen. — `ADR-0008:42–43`

### A5 Riippuvuudet (systemd, Docker, Python, SQLite, uv)

- **A5.1** Tylsä infrastruktuuri: systemd, Docker, Python, SQLite ja uv. Ei Kubernetesia eikä agenttikehyksiä. — `AGENTS.md:17–18`, `README.md:10`
- **A5.2** (alusta) Python 3.12. Riippuvuudet lukitaan `uv.lock`-tiedostoon, ja asennus käyttää komentoa `uv sync --frozen --no-dev`. — `pyproject.toml:5`, `deploy.sh:82`, `TILANNE:421`
- **A5.3** Docker on rootful. Dispatcher (aiops-run, docker-ryhmässä) käynnistää työkontit; gateway (aiops-gw) ei kuulu docker-ryhmään. — `ADR-0001:20–26`
- **A5.4** (alusta) Palvelutiedosto on repossa (`config/systemd/`), sen asentaa deploy.sh ja sen kovennusta vahtii testi. — `TILANNE:343`, `ADR-0010:51`, `gateway.service:15`
- **A5.5** (alusta) SQLite-kanta on `/srv/aiops/db`, ja skeema on versiossa 3. Skeemamuutoksen jälkeen koodin palautus vaatii
  kannan palautuksen. — `ADR-0002:20`, `TILANNE:352`, `ADR-0010:180–181`
- **A5.6** Imagen rakennusohje on repossa. ADR-0009:n imageissa kaikki ulkopuolinen on kiinnitetty: pohja tiivisteellä, lähde
  commitilla ja Python uv.lockilla. Käännös ajetaan ilman verkkoa. — `ADR-0008:89–92`, `ADR-0009:169–172`
- **A5.7** Ajuripaketteja ei asenneta NVIDIAn reposta. Uusi pakettilähde on toimitusketjupäätös, joka tehdään omana kirjattuna
  muutoksenaan. — `ADR-0005:19–20`, `TILANNE:581–583`

### A6 Testit molempiin suuntiin

- **A6.1** Testaa sekä sallittu että kielletty suunta, ja pidä ainakin yksi riippumaton, käsin kirjoitettu totuus. — `AGENTS.md:21–22`
- **A6.2** Ennen toimitusta ajetaan `uv run pytest -q`, ja skripteille `bash -n` ja `shellcheck`. Kerro, mitä testasit. — `AGENTS.md:45–46`
- **A6.3** Riskialttiit muutokset simuloidaan ensin, ja niitä ennen otetaan puhdas lähtötilanne. Yksi muuttuja kerrallaan. Ennen
  muutosta pyydetään vain luku -tuloste, eikä versioita, polkuja tai tiloja oleteta. — `AGENTS.md:15–16`, `AGENTS.md:19–20`, `README.md:9`

### A7 Toimitus

- **A7.1** Toimitus tehdään pull requestina, ei koskaan suorana pushina main-haaraan. — `AGENTS.md:47–48`
- **A7.2** Rakentaja ei näe isäntäkonetta. PR:n kuvauksessa ovat tarkistuskomennot, jotka Elias ajaa ennen asennusta, ja jokaisen
  komennon odotettu tulos. — `AGENTS.md:44`, `AGENTS.md:49–50`
- **A7.3** Komennot ovat kopioitavia, ilman `<paikkamerkkejä>` (esim. `ID=$(...)`). Palvelukäyttäjän komennot ajetaan
  juurihakemistosta. — `AGENTS.md:41–43`
- **A7.4** Vain commitoitua koodia asennetaan. deploy.sh pysähtyy, jos työpuussa on muutoksia tai jokin työ on käynnissä. — `AGENTS.md:51`, `deploy.sh:37–51`
- **A7.5** Isäntämuutokset ja asennukset tekee Elias. Rakentaja valmistelee tiedostot ja antaa komennot odotettuine tuloksineen. — `TILANNE:21–24`
- **A7.6** PR yhdistetään vain tarkistetusta kärjestä (`--match-head-commit`). — `TILANNE:465`, `TILANNE:557`
- **A7.7** Vastaa suomeksi. Selitä ensin intuitiivisesti, mitä tehdään ja miksi, ja anna vasta sitten komennot. — `AGENTS.md:3`, `AGENTS.md:38–40`
- **A7.8** (alusta) Codexissa päivitetty docs/TILANNE.md toimitetaan kokonaisena samassa PR:ssä. — `AGENTS.md:54`

### A8 Isäntämuutokset muutoslokiin

- **A8.1** Jokainen isäntäkoneen muutos kirjataan tiedostoon `docs/muutosloki.md` (mitä, miksi, miten perutaan) ja commitoidaan.
  Kaiken voi perua. — `AGENTS.md:23–24`, `MUUTOSLOKI:3`, `ADR-0008:41–42`
- **A8.2** Muoto on nykyisten merkintöjen mukainen: otsikko `## PVM Vaihe: nimi` ja kohdat Mitä, Miksi ja Peruminen sekä tarvittaessa
  Todennettu. — `MUUTOSLOKI:5–8`, `MUUTOSLOKI:71–75`
- **A8.3** Suunniteltu ja toteutunut pidetään erillään: asennusta tai testien onnistumista ei merkitä valmiiksi ennakolta. — `MUUTOSLOKI:113–114`, `MUUTOSLOKI:123`
- **A8.4** Jokaisesta isännän konfiguraatiotiedostosta on repossa malli tai sisältö. — `ADR-0008:41–43`, `ADR-0008:89–92`

### A9 Varmistus (ADR-0008)

- **A9.1** Varmistus on GitHub-repo (koodi, ADR:t, muutosloki, konfiguraatiomallit), ja siinä on kaikki, mitä uudelleenrakennus
  tarvitsee. Ajonaikainen tila saa hävitä levyn menetyksessä. — `ADR-0008:31–33`, `ADR-0008:41–43`
- **A9.2** Ennen migraatiota tai muuta riskialtista muutosta otetaan SQLite backup API -kopio (0600; integrity, SHA-256 ja rivimäärät
  kirjataan) ja kirjoitetaan palautusohje muutoslokiin. — `ADR-0008:35–36`
- **A9.3** Mikään palvelu ei varmista itseään automaattisesti, eikä mitään kopioida pilveen automaattisesti. Mallien painot eivät kuulu
  varmistukseen; repossa on niiden manifesti. — `ADR-0008:47`, `ADR-0008:98–99`, `ADR-0002:65–69`

### A10 Kielimallit (ADR-0009)

Koskee alustan koordinaattoria ja pilvikumppania. Koskeeko se sovellusta, on päätös C9.

- **A10.1** Paikallinen malli ajetaan dispatcherin GPU-työnä kovennetussa kontissa vain Unix-soketin kautta, ilman TCP:tä. — `ADR-0009:56–58`, `ADR-0009:62–71`
- **A10.2** Painot ovat hakemistossa `/srv/aiops/models` (root, liitos vain luku). Niiden SHA-256, julkaisija, lähde ja lisenssi
  kirjataan. Vain tunnettujen julkaisijoiden mallit kelpaavat, ja uusi malli kulkee polun karanteeni → mittaus → hyväksyntä. — `ADR-0009:72–77`
- **A10.3** `gpt-6.1-sol` on käytettävissä vain erillisen välittäjän kautta. Viikkokatto 10 € on kova ja koodissa valvottu, ja
  kustannus varataan ennen kutsua. — `ADR-0009:92–98`
- **A10.4** Korkein vedenkorkeus: julkinen data ja koodin laskemat yhteenvedot ovat AUTO, yksityiset rivit vaativat HYVÄKSYNNÄN ja
  restricted on KIELLETTY. Datan käyttö- ja säilytysehdot sekä EU-sijainti tarkistetaan ennen ensimmäistä kutsua. — `ADR-0009:99–107`, `ADR-0009:110`

## B. Suunniteltu, ei vielä käytettävissä (ADR-0011-luonnos)

> **EI SITOVA. EI TOTEUTETTU.** ADR-0011:n tila on "ehdotettu, versio 4", ja hyväksyntä tapahtuu commitilla (`ADR-0011:3`).
> Agenttikytkentää, puhelinohjausta ja pilvikutsuja ei ole toteutettu (`TILANNE:16–17`). Rakentaja ei saa olettaa näitä
> olemassa oleviksi (`AGENTS.md:15–16`).

- **B1** Agentilla (CEO) on oma käyttäjä ja ryhmä `aiops-ceo`, ei ryhmää aiops. Sillä ei ole tietokantaa, dataa, Dockeria, verkkoa
  eikä avaimia, ja se on kovennettu kuten gateway. — `ADR-0011:46–54`
- **B2** Agentille tulee oma soketti `/run/aiops-agent`, ja identiteetti tulee ytimeltä (SO_PEERCRED). Tämä on ehdotus, ei koodia. — `ADR-0011:55–60`
- **B3** Työkalujoukko on suljettu (listaa_tyot, lue_tyo, lue_tulos, ehdota_tyo, pilvikutsu, kirjaa_ehdotus), eikä siinä ole
  hyväksyntätoimintoa. Nyt `KNOWN_ACTIONS` sisältää vain `run_job`. — `ADR-0011:64–77`, `policy.py:34–35`
- **B4** Istunnolla on luokkakatto ja korkein vedenkorkeus. Niitä varten tulee uusi taulu `istunnot` (skeema 4). Istunnon aloittaa
  vain ihminen. — `ADR-0011:84–96`
- **B5** Mallisoketille kääre `umask 007` on pakollinen, ja jokainen ajo saa tuoreen sokettihakemiston. Mallityö on oma työtyyppinsä
  (enintään 60 min), ja palvelimen `--tools`/`--agent` ovat pois. — `ADR-0011:100–110`
- **B6** Johtaja on rooli, jonka hoitaa Qwen tai Sol. Solin istunnon katto on julkinen, ja viikkokaton täyttyessä ohjat siirtyvät
  paikalliselle. Välittäjä on oma palvelunsa. — `ADR-0011:118–130`
- **B7** Agentin työkalutasot ovat T0–T4. T4:ää ei sallita koskaan (repo, commit, deploy, politiikka, avaimet, sudo, kannan suora
  kirjoitus ym.). T0 on käytössä vain kokeena. Kielletyt suunnat todennetaan koodin testeillä. — `ADR-0011:143–151`, `ADR-0011:155–156`
- **B8** Suunnitelma on suostumus: TOML-suunnitelma ja kirjoitettu "kyllä". T1 ja ylemmät tasot vaativat allekirjoitetun suunnitelman. — `ADR-0011:193–198`
- **B9** Puhelinohjaus on gatewayn sivu `/ilmari` (lisaohje, pysayta, ohita_patka). Se on suunnitelma, ei toteutettu. — `ADR-0011:205–216`
- **B10** Aika- ja budjettinäkymä: koodi omistaa totuuden, viikkojakso on puoliavoin ja varaus atominen. — `ADR-0011:218–247`
- **B11** Eliaksen päätökset 6.–7.10. (kiintiöt, aikarajat, tehtäväsarja vähintään 30 skenaariota ja raja 24/30, luonnoshakemisto),
  toteutusjärjestys 8a-3a → 8c ja ennen toteutusta todettavat asiat. — `ADR-0011:324–343`, `ADR-0011:345–355`, `ADR-0011:304–322`

## C. Avoimet päätökset (Elias päättää)

Rakentaja ei valitse näissä. Jokainen kohta kertoo kysymyksen ja sen, mitä lähteet siitä sanovat.

- **C1 Sovelluksen asema.** Onko sovellus osa aiops-alustaa (sama repo, deploy.sh, `/opt/aiops`) vai erillinen ohjelma omassa repossaan?
  deploy.sh asentaa vain palvelut aiops-dispatcher ja aiops-gateway (`deploy.sh:26`) ja tyhjentää `/opt/aiops`-hakemiston jokaisessa
  asennuksessa (`deploy.sh:77–79`). Varmistus on yksi GitHub-repo (`ADR-0008:31–33`), ja toimitus- ja TILANNE-säännöt on kirjoitettu
  aiops-repolle (`AGENTS.md:45–54`). Päätös ratkaisee, sitovatko (alusta)-kohdat sovellusta.
- **C2 Käyttäjä, ryhmä ja kovennus.** Saako sovellus oman palvelukäyttäjän, ja kuuluuko se ryhmään aiops? Ryhmän jäsen voi kirjoittaa
  kantaan ja lukea datahakemistot (`ADR-0007:12`, `ADR-0010:22–23`). ADR-0001 hylkäsi yhden palvelukäyttäjän mallin (`ADR-0001:49–50`),
  ja luonnos jättää agentin ryhmän ulkopuolelle (`ADR-0011:269–270`). Kovennuksen malli on `gateway.service:20–69` (systemd-analyze
  security 0,8, `TILANNE:478`).
- **C3 Tarjoamistapa puhelimelle.** Tarkista ADR-0004:stä ja ADR-0010:stä; tämä dokumentti ei valitse. Lähteet sanovat:
  - Käyttö vain tailnetiin Tailscale Serven HTTPS:llä. Funnel on kielletty, eikä porttiohjausta tai julkista tunnelia käytetä (`ADR-0004:16–17`, `ADR-0004:29`).
  - Tailnet päästää työasemaan vain tcp:443 (`policy.hujson:7–12`), ja Serve ohjaa portin 443 gatewayn sokettiin (`TILANNE:321`).
  - Gateway on postinkantaja, jonka sallitut toimet on lueteltu (`ADR-0010:29–32`, `ADR-0010:89–95`). Keskustelunäkymä hylättiin V1:stä (`ADR-0010:157`).
  - Identiteetti tulee Serven otsakkeesta Tailscale-User-Login. Siihen voi luottaa vain, koska sokettiin pääsee vain tailscaled.
    TCP-portti osoitteessa 127.0.0.1 hylättiin, koska paikallinen prosessi voisi väärentää otsakkeen (`ADR-0010:64–68`, `ADR-0010:153–154`).
  - Julkaisu tailnetin ulkopuolelle muuttaisi ADR-0010:n päätöstä (`ADR-0010:186–187`). Luonnos ehdottaa sivua `/ilmari` (B9).
  - Ratkaisu, joka muuttaa ADR-0004:n tai ADR-0010:n päätöstä, vaatii uuden ADR:n (`AGENTS.md:24`).
- **C4 Verkko.** Tarvitseeko sovellus verkkoa, ja mihin suuntaan? Nykyiset palvelut ovat verkottomia (A2.5). Ulospäin suuntautuva
  verkko on päätetty vain välittäjälle (`ADR-0009:92–94`), eikä työasema saa avata yhteyksiä tailnetin muihin laitteisiin (`policy.hujson:3`).
- **C5 Salaisuuksien lukija (ristiriita).** `ADR-0001:23–24` antaa API-avaimet aiops-gw:lle, ja `ADR-0002:19` nimeää credentials-hakemiston
  lukijaksi vain aiops-gw:n. `ADR-0009:92–94` antaa avaimen vain erilliselle välittäjälle sen omalla käyttäjällä, ja `ADR-0002:52–53`
  asettaa hakemiston tilaksi 0700 root. Gateway on verkoton (`ADR-0010:45–47`). Avoinna on myös, saako sovellus oman credentialin.
- **C6 Data.** Mihin luokkiin sovellus saa koskea? Työnantajan linjaus puuttuu (`TILANNE:608`). Datan varmistus päätetään erikseen,
  kun säilytettävää dataa tulee (`ADR-0008:44–45`).
- **C7 Kuka tekee commitit ja PR:t (ristiriita).** `AGENTS.md:47–48`: Codexissa toimitus on pull request, chatissa tar.gz.
  `TILANNE:21–26` ja `TILANNE:554–557`: Elias hoitaa commitit, pushit ja PR-toimet, ja tämä korvaa avustajan aiemman luvan commitoida.
- **C8 Sovelluksen tila ja varmistus.** Tuottaako sovellus tilaa, jonka menetys olisi haitallista (esim. audit-loki, muisti,
  kirjanpito)? Sellainen tila muuttaisi ADR-0008:n päätöstä (`ADR-0008:81–85`).
- **C9 Kielimallit.** Käyttääkö sovellus kielimallia, ja sitovatko A10 ja osa B sitä? Isännän Ollama on pois käytöstä (`TILANNE:254`).
- **C10 Uusien imagejen kiinnitys.** Vaaditaanko pohjaimagelta tiiviste kuten ADR-0009:ssä (`ADR-0009:169–172`), vai riittääkö tagi,
  kuten vanhemmille imageille hyväksyttiin (`ADR-0008:95–97`)?
- **C11 Vanhentuneet kohdat (ristiriidat, ei valita).** Tämä dokumentti ei nojaa näihin kohtiin:

| Kohta | Väite | Ristiriidassa |
| --- | --- | --- |
| `TILANNE:323` | main = `5628b20`, PR #12 avoin luonnos | `TILANNE:1`, `TILANNE:65–66`, `TILANNE:202`; mainin kärki `10775e2` (git ls-remote 8.10.) |
| `TILANNE:522` | root-kopio "PR #12, luonnos" | `TILANNE:65–66` |
| `TILANNE:561` | root-kopion tuloskirjaus odottaa uutta committia | `TILANNE:65–66`, `MUUTOSLOKI:264` |
| `TILANNE:443` | "mainissa (PR #11)" 761 passed | `TILANNE:49` (PR #12: 802 passed); `AGENTS.md:45` neuvoo hakemaan odotetun tuloksen TILANNE.md:stä |
| `TILANNE:598` | ADR-0009 "ennen vaihetta 8", painojen säilytys päätettävä | `ADR-0009:3`, `ADR-0009:72–74` |
| `TILANNE:611` | paikallinen LLM vasta V1.5:ssä | `ADR-0009:114–115` |
| `README.md:17–26` | vaiheet 2–8 tekemättä | `TILANNE:3`, `TILANNE:573` |

## Tarkistuslista ennen käyttöönottoa (Elias)

Komennot ja odotetut tulokset ovat lähteistä. Aja ne työasemalla aiops-repon juuresta `~/code/aiops` (`AGENTS.md:42`); vaiheen 1
PR- ja testikomennot ajetaan sovelluksen repossa, jos se on erillinen (C1).

**1. PR ja koodi**

- [ ] Aseta muuttujat `PR` ja `HAARA`. `gh pr view "$PR" --json number,state,isDraft,headRefOid,mergeable` → `headRefOid` on sama
  commit, jonka tarkistit (`TILANNE:465`; gh 2.45 kaatuu ilman `--json`, `TILANNE:317`).
- [ ] `git diff --stat main...origin/"$HAARA"` → vain odotetut tiedostot. Ei salaisuuksia, avaimia eikä työnantajan dataa (A3.4, A4.1).
- [ ] `uv run --frozen pytest -q` → PR:n kuvauksessa ilmoitettu tulos, ja kielletyt suunnat ovat mukana (A6.1). Skripteille `bash -n`
  ja `shellcheck` → ei virheitä (`AGENTS.md:45–46`).
- [ ] Osa A on käyty läpi, ja sovellusta koskevat C-kohdat on päätetty tai kirjattu ADR:ksi (`AGENTS.md:24`).
- [ ] Muutoslokissa on jokaiselle isäntämuutokselle Mitä, Miksi ja Peruminen (A8).

**2. Lähtötila ennen asennusta (vain luku, tallenna tulosteet)**

- [ ] `systemctl status aiops-dispatcher aiops-gateway` → molemmat active (`TILANNE:448`, `TILANNE:241`).
- [ ] `sudo journalctl -u aiops-dispatcher -b --no-pager | grep käynnissä` → hyväksyjät `elias (ed25519), elias-puhelin (webauthn)` (`TILANNE:450`, `MUUTOSLOKI:156`).
- [ ] `(cd / && sudo -u aiops-gw aiops-gateway --check)` → konfiguraatio kelpaa, skeema 3 (`TILANNE:449`, `MUUTOSLOKI:152`).
- [ ] `tailscale serve status` → vain portti 443 gatewayn sokettiin, Funnel pois (`TILANNE:321`, `TILANNE:451`).
- [ ] `sudo docker ps -a` → ei odottamattomia kontteja (`TILANNE:570`).
- [ ] `cat /opt/aiops/DEPLOYED` → asennettu commit; viimeksi kirjattu `58cd1eb` (`TILANNE:241`).
- [ ] `bash scripts/aiops-audit.sh` → raportti `~/aiops-audit-AIKALEIMA.txt`. Skripti ei käytä sudoa eikä muuta mitään (`aiops-audit.sh:5–15`).
- [ ] Jos kanta tai muu riskialtis asia muuttuu: palautuspiste ja palautusohje muutoslokiin (A9.2).

**3. Asennuksen jälkeen**

- [ ] Toista vaiheen 2 komennot: palvelut active, hyväksyjät ja Serve ennallaan (ellei C3:n päätös toisin sano), ei uusia kontteja.
- [ ] Uusi `bash scripts/aiops-audit.sh`: kohdassa "Kuuntelevat portit" ei uusia kuuntelijoita osoitteissa 0.0.0.0 tai [::], UFW-rivi
  `ENABLED=yes`, eikä eliasta ole docker-ryhmässä (`aiops-audit.sh:143`, `aiops-audit.sh:183–190`; A1.3, A1.4, A2.2).
- [ ] `diff <(grep -v '^#' examples/sallitut-imaget.txt) <(grep -v '^#' /etc/aiops/sallitut-imaget.txt)` → ei tulostetta (`ADR-0008:94`).
- [ ] Uudelle palvelulle `systemd-analyze security` palvelun nimellä; vertailukohdat gateway 0,8 ja dispatcher 1,4 (`TILANNE:475`, `TILANNE:478`).
- [ ] Muutoslokin merkintä on päivitetty toteutuneeksi ja commitoitu (A8.3).
