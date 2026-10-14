# Ilmari Hubin integraatioraja ja vain lukevat ennakkotarkistukset

**Päivitys 14.10.2026:** tuotantoliitäntä on päätetty aiops-repon ADR-0013:ssa, ja tämä repo toteuttaa sen
(ks. [ADR-UI-0001:n päätösosa](adr/0001-hub-integration-proposal.md)). Alla oleva teksti on kirjoitettu ennen päätöstä:
sen "gatewayn vartijan alle" -muotoilut ja C2/C3:n avoimuus eivät ole enää voimassa. Julkaisumuoto on kuvattu
aiops-repon tiedostossa `apps/ilmari-selain/MUODOT.md` (kohta 8: julkaisu).

Tämä erillinen repo toimittaa Hubin käyttöliittymän ja eristetyt lukukomponentit. Se ei asenna palvelua työasemalle tai muuta aiops-alustan turvallisuusrajoja. [ADR-ehdotus](adr/0001-hub-integration-proposal.md) on tarkistettavissa, mutta tuotannon C2/C3-päätökset ovat avoimet. Tässä dokumentissa ei ole deploy-, sudo-, Serve-muutos-, käyttäjänluonti- tai kannanmuutoskomentoja.

## Todennettu lähdepohja

| Lähde | Mitä siitä voidaan käyttää | Mitä se ei todista tässä ympäristössä |
| --- | --- | --- |
| Käyttäjän toimeksianto | Python/FastAPI/Jinja, kahdeksan näyttöä, neljä skiniä, turvarajat | Olemassa olevaa sallittua agentti-/sovellus-API:a |
| 13.10. `TILANNE.md`:n alun päivitys | Julkaisukohde `/srv/aiops/ilmari/ajot`; taustalla asennettu 8a-3d; ADR-0011 v5 hyväksytty | Työaseman nykyistä committia, oikeuksia, palvelutilaa tai PR #22:n/MUODOT-PR:n yhdistymistä |
| 8.10. `ilmari-ready.md` | A-osan turvarajat; C-kohtien arviointikehikko | B-osan vanhentunutta ADR-/puhelinohjaustilaa |
| Uuden repon tarkastus | Tyhjä lähtörepo, jonka käyttäjä valitsi tarkoituksella | aiops-repon `AGENTS.md`:n, koodin, ADR:ien ja `MUODOT.md`:n sisältöä |

`MUODOT.md`:n todellinen sisältö täytyy saada ennen tuotannon tiedostojen yhteensopivuusväitettä. Lähteissä mainittuja `meta.json`:n kenttiä `loppu`, `tila` ja `sol_tulos` ei saa keksiä: tilannekuva kertoo niiden olleen aiemman SUUNNITELMA.md:n virheitä. Myös Sol-tuloksen rakenne oli siinä väärä. Uuden repon tiedostolukija toimii eristetysti ja näyttää JSON/JSONL:n turvallisesti; tuotannon semanttisten kenttien tulkinta tarvitsee tarkistetun adapterin.

## Reitit ja vartijoiden omistaja

Hubilla on vain GET-näkymiä ja staattinen CSS. Se ei vastaanota keskusteluviestejä, jätä töitä, hyväksy, peru, muuta mallia tai budjettia eikä tallenna uusia agenttiohjeita.

Taustadokumentista tunnetaan aiops-alustan `/ilmari`, `/passkey`, `/kuka`, `/tyo/ID` ja `/tyo/ID/hyvaksy`. Niiden olemassaolo tässä työasemassa on tarkistettava nykykoodista. Työkohtaisessa URL:ssa ID tulee todennetusta työmetadatasta, eikä UI päättele uutta työtä ajotunnuksesta. Hyväksyntälinkki johtaa alkuperäiselle WebAuthn-sivulle; Hub ei tee vaihtoehtoista hyväksyntää. Nykyinen `/ilmari`-lisäohjekenttä on yöajon ohjaus, ei yleisen keskustelun API.

Tailscale-identiteettiotsakkeet ovat luotettavia vain aiops-ADR:ssä määritellyssä Serve → suojattu gateway-soketti -ketjussa. Hubin eristetty ASGI-testiympäristö ei todenna tailnet-käyttäjää. Tuotantoliitäntä täytyy tehdä nykyisen gatewayn vartijan alle; vahvistettu osoite, sallitut käyttäjät ja ei-Funnel-raja säilyvät ennen kaikkia Hubin reittejä, myös staattisia tiedostoja. Tavalliseen TCP-palvelimeen lähetetty otsake ei ole tunnistus.

## Eliaksen ajamat ennakkotarkistukset aiops-työasemalla

Seuraavat komennot vain lukevat. Ne eivät asenna tai julkaise UI:ta. Aja ensimmäinen lohko aiops-repon juuresta, joka on liitteen mukaan `~/code/aiops`. Odotettu historiallinen minimitieto on `11746d6`, mutta nykyisen kärjen täytyy tulla tulosteesta; älä vertaa vanhaa testimäärää automaattiseksi hyväksymisehdoksi.

```bash
cd "$HOME/code/aiops"
git status --short --branch
git --no-pager log --oneline -5
gh pr list --state all --limit 100 --json number,title,state,headRefName,headRefOid,mergedAt
gh pr view 22 --json number,state,headRefName,headRefOid,mergedAt
rg --files docs/adr apps/ilmari-selain src/aiops/gateway config/systemd scripts
```

Odotettu tulos: todellinen työpuu ja main-kärki näkyvät; PR #22:n ja `apps-ilmari-selain-muodot`-haaran tila on selvä; nykyiset ADR:t, MUODOT.md ja gateway-/palvelu-/deploy-tiedostot löytyvät. Jos MUODOT-PR on yhdistämättä, päähaaran tiedosto ei yksin riitä. `gh`-tunnistuksen epäonnistuminen ei todista Git-HTTPS-oikeuden puutetta; Git- ja PR-API ovat eri tarkistuksia. Komennoissa ei tulosteta token-arvoja tai credentials-tiedostoja.

Lue löydetty formaatti ja rajojen nykyinen koodi:

```bash
cd "$HOME/code/aiops"
if test -f apps/ilmari-selain/MUODOT.md; then
  sed -n '1,320p' apps/ilmari-selain/MUODOT.md
else
  echo 'MUODOT.md puuttuu: tuotantoadapteria ei voi vielä vahvistaa.'
fi
rg -n 'Tailscale-User-Login|X-Forwarded-Host|Sec-Fetch-Site|Origin|Funnel|Content-Security-Policy|/ilmari|/passkey|hyvaksy|@.*get|@.*post' src/aiops/gateway
rg -n 'PrivateNetwork|RestrictAddressFamilies|InaccessiblePaths|ProtectHome|User=|Group=|RuntimeDirectory|ReadWritePaths' config/systemd
sed -n '1,220p' scripts/deploy.sh
```

Odotettu tulos: korjattu MUODOT on nähtävissä; vartijan koodisijainti ja reittien järjestys ovat selvät; WebAuthn-sivujen CSP-poikkeukset ovat tarkkarajaisia; deploy-skriptin soveltuvuus selviää. Tämä on lähdekoodin luku, ei vartijoiden live-testi. Älä tulosta `/etc/aiops/credentials`:n sisältöä tai purkaa avaimia tätä tarkistusta varten.

Lue isännän tila ilman palvelumuutoksia:

```bash
systemctl is-active aiops-dispatcher aiops-gateway
cat /opt/aiops/DEPLOYED
tailscale serve status
systemctl show aiops-gateway --property=User,Group,PrivateNetwork,RestrictAddressFamilies,InaccessiblePaths,ProtectHome,RuntimeDirectory,RuntimeDirectoryMode
getent group aiops
namei -l /srv/aiops/ilmari/ajot
stat -c '%n %U:%G %a %F' /srv/aiops/ilmari /srv/aiops/ilmari/ajot /run/aiops-gw
ss -ltn
```

Odotettu tulos: molemmat palvelut ovat aktiivisia; asennettu commit tulee DEPLOYED-tiedostosta; Serve 443 osoittaa nykyiseen gateway-sokettiin ja Funnel on pois; nykyinen gatewayn kovennus näkyy nimetyissä ominaisuuksissa. Julkaisuhakemisto saattaa vielä puuttua, koska liite kuvaa sen 13.10. päätöstä eikä luontia. Puuttuminen on käyttöönottoprerequisite, ei syy lukea kotihakemistoa. `namei` kertoo myös vanhempien traversal-oikeudet. `ss` dokumentoi olemassa olevat TCP-kuuntelijat; UI ei saa lisätä niitä. Permission denied kirjataan rajoituksena, eikä tämän tehtävän vuoksi nosteta oikeuksia.

Julkaisupuusta luetaan vain nimet ja tiedostotyyppien/oikeuksien tiedot, mikäli puu on jo olemassa:

```bash
python3 - <<'PY'
import os
from pathlib import Path
root = Path('/srv/aiops/ilmari/ajot')
if root.is_symlink():
    print('Julkaisujuuri on symlinkki: luetteloa ei avata.')
elif not root.exists():
    print('Julkaisuhakemistoa ei vielä ole.')
else:
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 30:
                print('Näyttö rajattu ensimmäiseen 30 hakemistomerkintään.')
                break
            details = entry.stat(follow_symlinks=False)
            print(repr(entry.name), oct(details.st_mode & 0o7777),
                  'symlink' if entry.is_symlink() else 'hakemisto' if entry.is_dir(follow_symlinks=False) else 'muu')
PY
```

Odotettu tulos: vain tiukan ajotunnusmuodon mukaisia hakemistoja; ei symlinkkejä; oikeudet eivät anna UI:lle kirjoitusta. Tämä rajattu luettelo ei lue julkaisuja tai henkilökohtaisia raportteja eikä todista lukijan snapshotin eheyttä.

## Tuotantoliitännän toteutusjärjestys

1. Kokoa yllä olevat tulosteet, aiops-repon nykyiset ADR:t ja MUODOT.md. Päätä C2/C3 ennen palvelun tai verkkoreitin suunnittelun viimeistelyä.
2. Tarkista vartioitu integraatiopiste koodista. Vartija suojaa kaikki Hubin polut. Osoita testillä, ettei suora kutsuja voi väärentää identiteettiä.
3. Sovita ajosopimus MUODOT.md:hen riippumattomilla esimerkkitiedostoilla. Julkaisija saa viedä vain sallittuja tiedostoja ja sulkea julkaisun atomisesti; rajat ja oikeudet testataan.
4. Hyväksy korttijulkaisija ja sen dataluokka erikseen. Käynnistys ei ota yhteyksiä sovelluksiin, terveystietoihin tai Jarvisiin.
5. Aja alkuperäisen aiops-haaran koko regressiosarja ja uuden UI:n testit. Mukaan nykyiset Host/Origin/Sec-Fetch-Site-, identiteetti-, CSP-, WebAuthn- ja dispatcher-politiikkakokeet sekä Hubin oikeus-, polku-, kokoraja- ja XSS-kokeet.
6. Kirjoita valitulle asennukselle tarkka ennakkotarkistus, odotettu tulos, muutos, jälkitarkistus ja palautus. Asennus- ja muutoslokimerkintä tehdään vasta toteutuneen isäntämuutoksen jälkeen. Tämä toimitus ei valtuuta tai suorita niitä.

## Palautus

Tämä UI ei muuta tietokantaa, skeemaa tai pilvibudjettikirjanpitoa. Tässä cloud-checkoutissa valmisteltu koodi voidaan hylätä tai korvata tarkistetulla versiolla ilman tuotannon palautusoperaatiota. Älä poista käyttäjän muita muutoksia tai käytä `git clean`/`git reset --hard` -komentoja.

Jos UI myöhemmin mountataan gatewayhin, palautus tarkoittaa tarkistetun UI-mountin/adaptaation poistamista tai edellisen hyväksytyn koodiversion palauttamista kyseisen integraation asennusohjeella. Nykyiset `/ilmari`, `/passkey`, työn ja hyväksynnän reitit sekä Serve-kohde säilyvät. Julkaistut ajot eivät ole UI:n omistamaa poistettavaa tilaa. Alustan aiemman skeema 4 -muutoksen palautusohjetta ei sovelleta UI:hin: UI ei tee migraatiota.

Erillisen palvelun mahdolliset soketti-, ACL- ja käyttäjämuutokset tarvitsevat valitun C2/C3-ratkaisun täsmällisen palautusohjeen. Sellaista host-muutosta ei ole tehty tai ennakkoon hyväksytty tässä tehtävässä.
