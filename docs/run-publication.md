# Ajotulosten turvallinen lukija

`src/ilmari_ui/runs.py` lukee vain sovitun julkaisuhakemiston välittömiä
ajohakemistoja. Tuotannon suunniteltu juuri on `/srv/aiops/ilmari/ajot`.
Lukija ei julkaise tuloksia, lue `~/ilmari-yo`-raakahakemistoa, työkopiota,
repositorion sisältöä, tietokantaa tai `/srv/aiops/data`-hakemistoa eikä tee
verkkokutsuja. Testit käyttävät eristettyä väliaikaista julkaisua.

## Todennetut tiedot ja formaatin raja

Käyttäjän `CODEX-ILMARI-HUB-ARCTIC-COMMAND-PROMPT.md` ja `TILANNE.md`:n
13.10.2026 päivitys nimeävät viisi julkaistavaa tiedostoa:
`meta.json`, `raportti.md`, `ehdotukset.jsonl`, `sol-tulos.json` ja
`luonnos.patch`. Ajotunnuksen sovittu muoto on
`[0-9]{8}-[0-9]{6}-yo-[a-z0-9]+`. Toteutus rajoittaa loppuosan 32 merkkiin.
Tunnus on tunniste; sen numeroita ei tulkita aikaleimaksi.

Todellista, korjattua `apps/ilmari-selain/MUODOT.md`:tä ei voitu lukea.
Vain lukeva `git clone --depth 1 --single-branch --branch
apps-ilmari-selain-muodot https://github.com/Elkkuboi/aiops-tyoasema.git`
sekä kyseisen haaran `git ls-remote` palauttivat HTTP 403 ja palvelimen
viestin `Write access to repository not granted`. Tämä on havaitun
**lukuoperaation** pääsyvirhe; siitä ei päätellä tokenin puuttumista tai
kirjoitusvaltuuksia. Liitteet eivät sisällä täydellistä julkaisuskeemaa.
Lähderepositorioon ei tehty muutoksia.

Siksi lukija hyväksyy rajattua, rakenteellisesti validoitua JSONia
metatietojen tarkasteluun. Se **ei väitä validoivansa nykyisen yöajon
semanttista skeemaa**. JSON-kentistä ei päätellä ajon tilaa, mallia,
alku-/loppuaikaa, budjettia tai Solin tuomiota. Käyttöliittymä näyttää
ne nimellä **Julkaisun metatiedot** ja ilmoittaa formaatin vahvistuksen
puuttuvan. Tuomioiden T/O/V/E semanttinen esitys ja kenttien tiukka
sallittujen lista voidaan kytkeä vasta todellisen `MUODOT.md`:n ja
julkaisijan koodin tarkistamisen jälkeen.

## Python-rajapinta

```python
reader = RunReader("/srv/aiops/ilmari/ajot")
listing = reader.list_runs()
detail = reader.read_run("20261013-001914-yo-q6")
```

`RunList` sisältää `runs`, `errors`, `state` ja `truncated`.
`RunSummary` sisältää `run_id`, `meta` ja `errors`; `title` on ajotunnus.
`RunDetail` sisältää `run_id`, `meta`, `report`, `proposals`,
`sol_result`, `patch` ja `errors`. `ReadError` sisältää `code`, `file`
ja suomenkielisen, polkuja paljastamattoman `message`-tekstin.

Listan tilat ovat `ready`, `empty`, `not_available` ja `error`.
Virheellinen yhden ajon metadata jää kyseisen ajon `errors`-listaan;
se ei kaada muuta listausta. Virheellinen tai puuttuva yksittäinen
tiedosto jää yksityiskohtasivun `errors`-listaan; muut tiedostot voivat
olla luettavissa. Kokonaisuudessaan turvaton, puuttuva tai lukemisen
aikana vaihtunut ajohakemisto aiheuttaa `ReadFailure`-poikkeuksen.
Listauksen juuren virhe hylkää kaikki osittaiset tulokset.

`meta` on JSON-olio tai `None`. `proposals` on JSON-olioiden tuple;
virheellisen JSONL-tiedoston osittaista alkua ei palauteta.
`sol_result` on JSON-olio, JSON-lista tai `None`.
`report` ja `patch` ovat tavallisia UTF-8-tekstejä tai `None`.
Teksti voi sisältää HTML:n näköistä sisältöä; esityskerros escapettaa
sen tekstiksi. Lukija ei tulkitse Markdownia tai HTML:ää, suorita
diffiä eikä luo ulkoisia linkkejä.

## Lukurajat ja hylkäykset

| Tiedosto tai rakenne | Raja |
| --- | ---: |
| `meta.json` | 64 KiB |
| `raportti.md` | 512 KiB |
| `ehdotukset.jsonl` | 512 KiB |
| `sol-tulos.json` | 256 KiB |
| `luonnos.patch` | 1 MiB |
| JSONL-rivi | 16 KiB |
| JSONL-tietueet | 512 |
| Yhden JSON-olion kentät | 64 |
| Kentän nimen merkit | 100 |
| JSON-tekstiarvon merkit | 16 384 |
| JSON-listan alkiot | 1024 |
| Yhden JSONin rakenteen solmut | 4096 |
| JSONin syvyys | 12 |
| Listattavat ajot | 100 oletuksena, enintään 1000 |
| Tarkasteltavat hakemistomerkinnät | 2000 |
| Operaation yhteistyöhön perustuva aikaraja | 1 s oletuksena, enintään 10 s |

JSON torjuu päällekkäiset avaimet, tyhjät ja liian pitkät kenttänimet,
rikkinäisen UTF-8:n ja Unicode-sijaismerkit, kielletyt ohjaus- ja
suunnanohjausmerkit, NaN/Infinity-arvot, yli 30-numeroiset kokonaisluvut
ja äärellisetkin liukuluvut, joiden itseisarvo ylittää `1e100`.
Bool-arvo on oma tyyppinsä; se ei muutu numeroksi.
Aikaleimasemantiikkaa ei oleteta vahvistamattomille kentille.
JSONL käyttää LF-rivejä, hyväksyy CRLF:n ja mahdollisen viimeisen
rivinvaihdon; tyhjät tietuerivit ja muut kuin JSON-oliot hylätään.

Absoluuttinen juuripolku avataan `/`-hakemistosta komponentti
kerrallaan käyttäen `dir_fd`, `O_DIRECTORY` ja `O_NOFOLLOW`-lippuja.
Ajotunnus validoidaan ennen ensimmäistä tiedostojärjestelmäoperaatiota.
Tiedostoilla on kiinteä sallittujen nimien lista; asiakas ei voi antaa
omaa tiedostonimeä. Symlinkit, FIFO:t, laitteet, hakemistot tiedostona,
hardlinkit ja polkujen `..`-osat hylätään. Tiedosto avataan
`O_NOFOLLOW | O_NONBLOCK`-lipuilla ja tarkastetaan tavalliseksi
tiedostoksi ennen lukemista. Nimetyn kohteen ja avatun descriptorin
laite/inode/tyyppi sekä tiedoston koko, muutosajat ja linkkimäärä
verrataan ennen ja jälkeen lukemisen. Kaikki juuripolun hakemistot
ja ajohakemisto verrataan uudelleen ennen tuloksen palauttamista.
Descriptoreista suljetaan jokainen myös virhepoluilla.

Aikaraja tarkastetaan polkujen avaamisen, hakemistoselauksen, lukupalojen
ja JSONL-rivien välissä. Se ei voi keskeyttää käyttöjärjestelmän
jumittunutta tiedostojärjestelmäkutsua. Julkaisujuuren tulee olla
luotetulla paikallisella tiedostojärjestelmällä; verkkomountin tai
epäluotetun FUSE-tiedostojärjestelmän käyttö ei kuulu tähän sopimukseen.
Tuotannon prosessin resurssi- ja palvelurajat tulee määritellä
käyttöönottopäätöksessä.

Virhekoodit: `invalid_run_id`, `unsafe_path`, `unsafe_file`, `changed`,
`too_large`, `invalid_json`, `invalid_jsonl`, `invalid_text`, `not_found`,
`forbidden`, `timeout` ja `read_error`. UI ei näytä raakoja
käyttöjärjestelmän poikkeuksia, salaisuuksia tai absoluuttisia polkuja.

## Julkaiseminen ja vähimmäisoikeudet — käyttöönottoehdotus

Tätä repositoriota varten ei asennettu julkaisijaa, palvelukäyttäjää tai
systemd-palvelua eikä muutettu gatewayta tai Tailscale Serveä.
Tuotantokytkentä edellyttää erikseen hyväksyttyä palvelu-, reititys-
ja julkaisupäätöstä. Turvallinen lähtökohta on oma selaimen käyttäjä
ja erillinen julkaisuryhmä tai vain julkaisupolkuun rajattu POSIX ACL.
Selaimen käyttäjää **ei lisätä yleiseen `aiops`-ryhmään** pelkkää
lukuoikeutta varten, koska se voisi avata muita tietoja.

Selaimella on polun vanhempiin vain läpikulkuoikeus, julkaisujuureen ja
ajohakemistoihin listaus/luku/läpikulku sekä julkaisutiedostoihin luku.
Selaimella ei ole kirjoitusoikeutta mihinkään julkaisupolun osaan,
omistussuhteisiin, raakadataan tai työkopioon. Julkaisija hyväksytään
erikseen; sen kuuluu suodattaa dataluokka ennen vientiä. Lukija ei voi
päätellä pelkästä metatiedosta, onko yksityisen sisällön julkaisu sallittu.

Julkaisijan ehdotettu menetelmä on luoda uusi väliaikainen hakemisto
samalle paikalliselle tiedostojärjestelmälle, kopioida siihen vain viisi
sallittua tiedostoa, validoida todellinen lähdeskeema ja kokorajat,
asettaa rajatut oikeudet sekä julkaista hakemisto atomisella rename:lla.
Valmista julkaisua ei muokata paikallaan. Symlinkkejä tai kovia linkkejä
raakadataan ei julkaista. Ei työkopiota, avaimia tai automaattista
`restricted`-sisältöä. Tämä on ehdotus, ei väite nykyisestä yöajon
toteutuksesta.

Tuotannon verkkokytkentä tulee kulkea nykyisen ainoan Tailscale Serve
443 → gateway Unix-soketti -mallin kautta säilyttäen gatewayn
tunnistus-, Host-, Origin-, Sec-Fetch-Site- ja CSP-vartijat. Tämän
lukijan toteutus ei anna lupaa uuteen kuunteluporttiin, Serve-julkaisuun
tai tunnistusotsakkeiden luottamiseen suoralta asiakkaalta.

## Testien toistaminen

```bash
cd /workspace/ilmari_UI
UV_CACHE_DIR=/tmp/ilmari-uv-cache uv run pytest -q tests/test_runs.py
```

Testit kattavat itsenäisen onnistumisen, tiedostokohtaisen
virhe-eristyksen, traversal- ja Unicode-tunnukset, root/run/file-
symlinkit, hardlinkit, FIFO:n, laitemoodin, tiedostorajojen ylitykset,
tiukan JSON/JSONL-rakenteen, rikkinäisen UTF-8:n, tiedoston vaihdon ja
muutoksen kesken lukemisen, ajo- ja juurihakemiston vaihtokilpailun,
aikarajan sekä sen, ettei lukija kirjoita julkaisuun.
