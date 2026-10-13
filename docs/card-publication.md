# Sovelluskorttien ehdotettu julkaisusopimus

`ilmari.card.v1` on tässä repositoriossa toteutettu ja testattu **ehdotus**, ei
aiops-isännällä käytössä oleva API. Lukija ei yhdistä Ravintopolkuun, UniCafeen,
Jarvisiin, malliin tai tietokantaan. Se lukee vain erikseen määritetyn, eristetyn
julkaisuhakemiston rajattuja JSON-tiedostoja. Tuotantoon julkaiseminen, yksityisen
tiedon käsittely ja julkaisijan käyttöoikeudet tarvitsevat omat päätöksensä.

Hakemistorakenne on `JULKAISUJUURI/app_id/card_id.json`. Juuri annetaan absoluuttisena
palvelinasetuksena; oletuksena yhteyttä ei ole. Juurta ei saa osoittaa sovelluksen
raakadataan, agentin työkopioon tai `/srv/aiops/data`-hakemistoon. Samassa juuressa
ei säilytetä agentin salaisuuksia, avaimia tai työnantajan tietoja.

## Yhteiset kentät

Kaikki kentät ovat pakollisia. Nullable-kentän puuttuminen ei tarkoita samaa kuin
eksplisiittinen `null`. Tuntemattomat kentät hylätään jokaisella tasolla.

| Kenttä | Sopimus |
| --- | --- |
| `schema_version` | Täsmälleen `ilmari.card.v1` |
| `app_id`, `card_id` | `^[a-z][a-z0-9_-]{0,63}$`; molemmat vastaavat julkaisupolkua |
| `kind` | `metric`, `time_series`, `recommendation_list`, `idea_list` tai `update_feed` |
| `title` | 1–160 merkkiä, epäluotettavaa tavallista tekstiä |
| `data_class` | `public`, `private` tai `restricted`; vertailu palvelimen luotettuun app→luokka-määritykseen |
| `published_at`, `observed_until`, `fresh_until` | ISO 8601 -aikaleima sekunteineen ja aikavyöhykkeineen; `observed_until ≤ published_at ≤ fresh_until` |
| `source` | `{ "name": "1–160 merkkiä", "url": "https://... tai null" }` |
| `units` | 1–32 merkkiä tai `null`; esim. `kcal`; julkaisu ei saa keksiä yksiköitä |
| `data` | Korttityypin mukaan tiukasti tyypitetty objekti |

Numero hyväksytään vain JSON-numerona, ei totuusarvona tai merkkijonona. Sen on
oltava äärellinen, ja itseisarvon enintään 10¹⁵. `NaN`, äärettömät arvot,
duplikaattiset JSON-avaimet ja virheellinen UTF-8 hylätään. Yksi tiedosto saa olla
enintään 65 536 tavua, sovelluksella enintään kahdeksan korttia ja sen
julkaisuhakemistossa enintään 32 hakemistomerkintää. Lukija lukee rajatun määrän
tavuja, vaikka tiedosto kasvaisi lukemisen aikana.

Ajantasaisuus tarkistetaan tietolähteen `fresh_until`-ajasta. Täsmälleen rajan
saavuttanut tieto on vanhentunutta. Yli kaksi minuuttia tulevaisuuteen päivätty
julkaisu hylätään kellovirheenä. Päiväkohtaisissa ruokalistoissa nykyinen päivä
ratkaistaan aikavyöhykkeessä **Europe/Helsinki**, eikä eilisen ruokalista muutu
tämän päivän tiedoksi, vaikka julkaisijan TTL olisi pitkä.

## Korttityyppien `data`

`metric`:

```json
{"value": 12, "note": null}
```

`value` on numero tai `null`. `note` on 1–1 000 merkkiä tai `null`.

`time_series`:

```json
{
  "period_start": "2026-10-11",
  "period_end": "2026-10-13",
  "points": [
    {"date": "2026-10-11", "value": 2100},
    {"date": "2026-10-13", "value": null}
  ]
}
```

Päivämäärä on tiukasti `YYYY-MM-DD`. Havaintojakso on enintään 366 päivää, ja
pisteitä on enintään 366. Päivät ovat yksilöllisiä ja nousevassa järjestyksessä,
jakson sisällä. Jakso ei pääty `observed_until`-päivän jälkeen. Julkaisematta jäänyt
päivä ja eksplisiittinen `null` ovat puuttuvia havaintoja. Lukijan
`data.complete_points` täydentää päivät `null`-arvoilla; se ei laske keskiarvoja,
interpoloi tai korvaa puuttuvaa tietoa nollalla. `observed_count` ja `missing_count`
kuvaavat havaintojen kattavuutta.

`recommendation_list`:

```json
{
  "for_date": "2026-10-13",
  "criteria": ["Käyttäjän nimenomaisesti valitsema kriteeri"],
  "items": [
    {
      "title": "Esimerkkiruoka",
      "description": "DEMO – ESIMERKKIDATA",
      "dietary_tags": ["Julkaisijan tunnistama merkintä"],
      "reason": "Lähteessä ilmoitettu suositusperuste",
      "source_url": null
    }
  ]
}
```

Enintään 12 kriteeriä, 30 annosta ja 12 ruokavaliomerkintää per annos. Otsikot,
kriteerit ja merkinnät ovat 1–160 merkkiä; kuvaus ja peruste ovat 1–1 000 merkkiä.
Tyhjä lista sallitaan: tiedon puuttuminen ei vaadi tekaistua annosta. Menneelle
päivälle julkaistu lista merkitään vanhentuneeksi. Tulevan päivän lista ei näy
tämän päivän saatavilla olevana tietona. Lukija ei päättele käyttäjän kriteerejä
eikä hae ruokalistoja verkosta.

`idea_list`:

```json
{
  "ideas": [
    {
      "idea_id": "example-one",
      "title": "Idean nimi",
      "problem": "Selvitettävä ongelma",
      "solution": "Ehdotettu ratkaisu",
      "assumption": "Tärkein testaamaton oletus",
      "next_experiment": "Seuraava rajattu koe",
      "stage": "hypothesis",
      "risks": ["Tunnettu epävarmuus"]
    }
  ]
}
```

Yllä näkyy yhden idean rakenne; kelvollisessa julkaisussa on **täsmälleen kolme**
ideaa yksilöllisillä tunnuksilla. `stage` on `idea`, `hypothesis` tai `tested`.
Otsikko on 1–160 merkkiä ja muut tekstikentät 1–1 000 merkkiä. Riskejä on enintään
kahdeksan. Vaihemerkintä on julkaisijan ilmoitus, ei Hubin vahvistama näyttö.
Tyhjä ideatilanne mallinnetaan puuttuvalla julkaisulla, ei kolmella täyteidealla.

`update_feed`:

```json
{
  "updates": [
    {
      "update_id": "example-update",
      "published_at": "2026-10-13T10:00:00+03:00",
      "title": "Nimenomaisesti jaettu päivitys",
      "summary": "Rajattu yhteenveto",
      "detail": null,
      "source_url": null
    }
  ]
}
```

Enintään 30 päivitystä yksilöllisillä tunnuksilla. Otsikko on 1–160 merkkiä,
yhteenveto 1–1 000 merkkiä ja tarkempi sisältö 1–4 000 merkkiä tai `null`.
Päivitys ei saa olla kortin viimeistä havaintoa uudempi. Tyhjä syöte sallitaan.
Jarvisin julkaisukanavaa tai jakolupaa ei synny tällä skeemalla.

## Luottamus, linkit ja HTML

`load_cards()` saa palvelimelta luotetun `app_classes`-määrityksen. Kortin oma
`data_class` ei määrää käyttöoikeutta. `restricted`-yhteenvetoja ei lueta lainkaan;
nykyisen aiops-politiikan mahdollinen metatietorajapinta on erillinen. `private`
luetaan vain, jos juuri kyseinen sovellus kuuluu palvelinasetuksen
`allowed_private_apps`-joukkoon. Tämä asetus edellyttää erillistä hyväksyttyä
käyttötarkoitusta ja julkaisulupaa; UI:n GET-parametri ei voi antaa sitä.

Lähdeviitteet ovat valinnaisia. Linkki hyväksytään vain HTTPS-osoitteena, jonka
tarkka hostname on palvelimen `allowed_source_hosts`-listassa. IP-osoitteet,
paikalliset nimet, tunnukset URL:ssa, muut portit kuin 443, ohjausmerkit,
kenoviivat ja `javascript:`/`data:`/`http:` hylätään. Sama sääntö koskee listojen
sisäisiä lähdelinkkejä. Lukija tai kortti ei koskaan seuraa linkkiä, esilataa sitä
tai avaa verkkoa. Mahdollinen käyttäjän avaama lähdelinkki esitetään tavallisena
turvallisesti escapettuna ankkurina; uuteen ikkunaan avattavaan linkkiin kuuluu
`rel="noopener noreferrer"`.

Kaikki ulkopuolinen sisältö säilyy tavallisena epäluotettavana tekstinä. Jinja2:n
HTML-autoescape on pakollinen; näihin kenttiin ei käytetä `safe`-suodatinta,
HTML:n renderöintiä, Markdownin raakaa HTML:ää tai `innerHTML`-kirjoitusta.
Validointi ei muuta HTML:ää luotetuksi. Virheen syytä, tiedostopolkua tai hylättyä
sisältöä ei palauteta käyttäjälle virheilmoituksessa.

## Lukija ja tilat

```python
states = load_cards(
    configured_publication_root,  # Path | None; palvelinasetus
    app_classes={"unicafe": "public", "ravintopolku": "private"},
    allowed_private_apps=frozenset(),
    allowed_source_hosts=frozenset({"unicafe.fi"}),
)
```

Tuloksena on `dict[str, CardState]`. Jokaisessa tilassa ovat `app_id`, `status`,
validoitujen `cards`-olioiden tuple, turvallinen suomenkielinen `message` ja
`rejected_count`. Kortti on diskriminoitu Pydantic-malli; tyyppi määräytyy
`kind`-kentästä. Tila on `ajantasainen`, `vanhentunut`, `ei yhdistetty`,
`tietoa ei saatavilla`, `virhe` tai nimenomaisessa kehitystilassa `esimerkkidata`.
Demo-tila on palvelimen erillinen kehityspäätös, ei julkaisun itse asettama kenttä.

Yhden kortin virhe ei kaada muiden korttien tai sovellusten lukemista. Saman
sovelluksen kelvolliset kortit palautetaan myös osittaisessa virhetilassa, jolloin
tila kertoo virheestä. Pelkkiä null-arvoja tai tyhjiä listoja sisältävässä
julkaisussa tila on `tietoa ei saatavilla`; metatiedot säilyvät näytettävinä.
Yhden sovelluksen useiden korttien tila on konservatiivinen: yksikin vanhentunut
kortti tekee sovelluksen yhteistilasta vanhentuneen. Näytössä korttikohtaiset
ajat säilyvät näkyvissä.

Lukija avaa juuren jokaisen polkukomponentin `O_DIRECTORY | O_NOFOLLOW`-lipuilla,
pitää hakemistodeskriptorit auki ja avaa sovelluksen sekä tiedoston niiden
`dir_fd`:n kautta. Symlinkkejä ei ratkaista. Hakemiston tai tiedoston vaihtaminen
avaamisen jälkeen ei vaihda jo avattua kohdetta. Vain tavallinen tiedosto, jonka
linkkilukumäärä on yksi, hyväksytään. Erikoistiedostot avataan nonblocking-lipulla
ja hylätään ennen lukemista. Hakemistolistaus ja luettavat tavut on rajattu.

Julkaisijan tulee kirjoittaa uusi rajattu tiedosto samaan julkaisuhakemistoon
väliaikaisella, ei-`.json`-nimellä ja korvata lopullinen tiedosto atomisella
renamella. Ei symlinkkejä, hardlinkkejä, samanaikaista sisällön muokkausta tai
omistavan sovelluksen datakansion näkyvyyttä lukijalle. Palvelukäyttäjä ja
tiedostooikeudet päätetään erillisessä käyttöönottosuunnitelmassa. Tämä moduuli ei
luo käyttäjää, myönnä oikeuksia, käynnistä palvelua tai asenna julkaisijaa.

## Todennus

`UV_CACHE_DIR=/workspace/.cache/uv uv run pytest tests/test_cards.py -q` testaa
kaikki viisi korttityyppiä, null-arvot ja aikasarjan aukot, aikavyöhykkeet,
vanhentumisen, ruokalistan päivän, erillisen demo-tilan, numerot, pituus- ja
kokorajat, sovellusidentiteetin ja luokkapolitiikan, lähdelinkkien hyväksynnän,
HTML:n escapettavan tekstin, JSON-virheet, puuttuvat julkaisut, riippumattomat
sovellusvirheet, hakemisto- ja tiedostosymlinkit, FIFO:n, hardlinkit sekä
hakemiston ja tiedoston vaihtokilpailut. Testit käyttävät synteettistä dataa ja
väliaikaisia julkaisuhakemistoja; tuotantotietolähteitä ei tarvita.
