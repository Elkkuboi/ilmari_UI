# PR: Istunto 2: Dokumentit- ja Kehitä-näkymät (aiops ADR-0024)

Haara `istunto-2` → `main`. Asennettu välitila `6d010ec` (vartija sallii ylätason navigoinnin muualta).

## Mitä

- **Dokumentit** `/hub/dokumentit` ja `/hub/dokumentit/<tunniste>`: asennetun aiops-commitin dokumentit
  (`/srv/aiops/ilmari/dokumentit`, root:ilmari-julkaisu, SHA-256-meta), haku, rajattu Markdown ilman raakaa HTML:ää.
- **Kehitä** `/hub/kehita` ja `/hub/kehita/<työ>`: kehitystyöt (`/srv/aiops/ilmari/kehitys`, gatewayn ja rootin
  kirjoittamat), diff, testit, lokit, päätökset, käyttöönottojen historia (`/srv/aiops/ilmari/kayttoonotot`), yöajon
  ehdotukset toiveiksi ja Claude Code -linkki. Hub vain lukee; toiminnot linkkeinä gatewayn sivuille (passkey).
- Palvelutiedosto: `BindReadOnlyPaths` dokumentit, kehitys ja kayttoonotot (käsin kirjoitettu odotus päivitetty).
- Esimerkkiaineisto `demo/dokumentit`, `demo/kehitys`, `demo/kayttoonotot`; testit `tests/test_dokumentit*.py`,
  `tests/test_kehitys*.py`; `docs/TILANNE.md` päivitetty.

## Tarkistukset ennen asennusta (Elias)

```
cd ~/code/ilmari_UI && git switch istunto-2 && uv run --frozen pytest -q     # odotettu: 650 passed, 69 skipped
```

## Asennus ja tarkistus

```
sudo scripts/asenna.sh "$(command -v uv)"
sudo curl --unix-socket /run/ilmari-hub/hub.sock -H 'Host: tyoasema.taild1a5b7.ts.net' \
  -H 'Tailscale-User-Login: Elkkuboi@github' -H 'Sec-Fetch-Site: none' http://tyoasema.taild1a5b7.ts.net/hub/dokumentit
```
Odotettu: HTML, jossa dokumenttilista (ARKKITEHTUURI, TILANNE, ADR:t). Sama polulla `/hub/kehita`: "Kehitystöitä ei ole
julkaistu" kunnes aiopsin isäntäaskeleet on tehty (aiops `docs/TILANNE.md`).

## Peruminen

`git revert` ja `sudo scripts/asenna.sh` edellisestä commitista; julkaisuhakemistot jäävät (vain luku).
