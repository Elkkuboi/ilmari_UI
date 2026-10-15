# Ilmari UI:n kehitys

Käyttäjä on tilannut tämän erillisen, alun perin tyhjän repon toteutuksen annettujen Ilmari-dokumenttien perusteella. Vastaa suomeksi. Lue README, docs/valmistelu/ilmari-hub-ui.md ja docs/TILANNE.md ennen muutoksia.

- Python 3.12, FastAPI, Jinja2, uv ja paikallinen CSS; ei Node-tuotantoalustaa, CDN:ää tai kolmannen osapuolen verkkopyyntöjä.
- Käytä nykyistä checkoutia. Pilvitehtävä on valmiiksi eristetty; älä tee Git-worktreeä ilman käyttäjän pyyntöä.
- LLM ehdottaa, koodi päättää. UI on vain lukija: ei työn hyväksyntää, salaisuuksia, mallikutsuja, GPU-ohjausta tai tietokannan kirjoitusta.
- Kehityspalvelin käyttää vain omistajan Unix-sokettia. Ei TCP-porttia, docker -p:tä, SSH:ta, Tailscale Serve/Funnel -muutosta tai isäntäasennusta.
- Tuotantoliitäntä on päätetty aiops-repon ADR-0013:ssa (14.10.2026): oma käyttäjä ilmari-hub, Tailscale Serven polku /hub suoraan Hubin sokettiin, ja Hub toistaa gatewayn vartijan säännöt tuotantotilassa (`--config`). Vartijan, etuliitteen palautuksen ja palvelutiedoston muutokset vaativat samat testit molempiin suuntiin; gatewayn sääntöjen muutos tehdään molempiin repoihin.
- Näytä synteettinen aineisto vain erikseen aktivoidussa esimerkkitilassa ja merkitse se jokaisessa sisältönäkymässä. Puuttuva tieto ei ole nolla tai reaaliaikainen mittaus.
- Teema ja esitysmieltymykset ovat GET-parametreja. Ei evästeitä, istuntoja, localStoragea, JavaScriptiä tai pysyvää arkaluonteisen sisällön välimuistia.
- Säilytä JSON-, tiedosto-, polku- ja kokorajat, tekstin escapetus ja tiukka CSP. Älä lisää mark_safe/safe-, innerHTML- tai eval-polkuja.
- Aja `UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen pytest -q`. Selaintestit: `uv sync --frozen --group browser`, Chromium järjestelmästä. Testaa onnistuminen ja kielletty suunta; pidä riippumattomat käsin kirjoitetut odotukset.
- Elias hoitaa commitit, pushit, PR-toimet ja isäntäasennukset, ellei hän valtuuta niitä erikseen. Valmistele tiedostot ja PR-kuvaus. Älä pushaa mainiin.
- Päivitä docs/TILANNE.md samassa toimituksessa. Älä kirjaa aiops-isäntämuutosta tai hyväksy ADR:ää, jota ei ole tehty tai hyväksytty.
