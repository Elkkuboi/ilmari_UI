#!/usr/bin/env bash
# =====================================================================
# asenna.sh: asentaa Ilmari Hubin viimeisimmän commitin hakemistoon /opt/ilmari-hub (aiops ADR-0013 kohta 1).
#
# Käyttö repon juuresta:   sudo scripts/asenna.sh "$(command -v uv)"
#
# Samat periaatteet kuin aiops-repon scripts/deploy.sh:ssa:
#   - Asennetaan vain commitoitu koodi (git archive HEAD). Likainen työpuu pysäyttää asennuksen.
#   - /opt/ilmari-hub on rootin omistama. Palvelu voi lukea koodin mutta ei muuttaa sitä.
#   - Asennettu commit kirjataan tiedostoon /opt/ilmari-hub/DEPLOYED.
#   - Palvelutiedosto asennetaan hakemistoon /etc/systemd/system. Käynnissä ollut palvelu pysäytetään koodin
#     vaihdon ajaksi ja käynnistetään sen jälkeen. Asennus ei koskaan käynnistä palvelua, joka ei ollut käynnissä.
#   - Skripti ei luo käyttäjää, ryhmää, konfiguraatiota eikä Serve-polkua. Ne ovat erillisiä isäntämuutoksia,
#     jotka kirjataan aiops-repon muutoslokiin.
# =====================================================================
set -euo pipefail

TARGET=/opt/ilmari-hub
UNIT=ilmari-hub.service
SERVICE_USER=ilmari-hub
UV="${1:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
GIT=(git -c "safe.directory=$REPO" -C "$REPO")

[ "$(id -u)" -eq 0 ] || { echo "Aja sudolla: sudo scripts/asenna.sh \"\$(command -v uv)\"" >&2; exit 1; }
[ -x "$UV" ] || { echo "Anna uv:n polku ensimmäisenä argumenttina: \"\$(command -v uv)\"" >&2; exit 1; }
[ $# -le 1 ] || { echo "Tuntematon argumentti: $2" >&2; exit 1; }
getent passwd "$SERVICE_USER" >/dev/null || { echo "Käyttäjää $SERVICE_USER ei ole. Luo se ensin (aiops-muutosloki)." >&2; exit 1; }
if [ -n "$("${GIT[@]}" status --porcelain)" ]; then
  echo "Repossa on tallentamattomia muutoksia. Commitoi ensin: asennetaan vain commitoitu koodi." >&2
  "${GIT[@]}" status --short >&2
  exit 1
fi

COMMIT="$("${GIT[@]}" rev-parse --short HEAD)"
echo "Asennetaan commit $COMMIT hakemistoon $TARGET"

WAS_ACTIVE=0
if systemctl is-active --quiet "$UNIT"; then
  WAS_ACTIVE=1
  echo "Pysäytetään $UNIT koodin vaihdon ajaksi"
  systemctl stop "$UNIT"
fi

STAGE="$(mktemp -d)"
cleanup() {
  rm -rf "$STAGE"
  if [ "$WAS_ACTIVE" -eq 1 ] && ! systemctl is-active --quiet "$UNIT"; then
    echo "HUOM: $UNIT on pysäytettynä, koska asennus keskeytyi. Korjaa virhe ja aja asennus uudelleen." >&2
  fi
}
trap cleanup EXIT
"${GIT[@]}" archive HEAD | tar -x -C "$STAGE"

install -d -o root -g root -m 0755 "$TARGET"
find "$TARGET" -mindepth 1 -delete
cp -r "$STAGE/src" "$STAGE/pyproject.toml" "$STAGE/uv.lock" "$STAGE/.python-version" "$TARGET/"

cd "$TARGET"
"$UV" sync --frozen --no-dev --no-editable --python /usr/bin/python3.12 --quiet
echo "$COMMIT $(date -Iseconds)" > "$TARGET/DEPLOYED"
chown -R root:root "$TARGET"
chmod -R u=rwX,go=rX "$TARGET"

if ! (cd / && sudo -u "$SERVICE_USER" "$TARGET/.venv/bin/ilmari-ui" --help >/dev/null); then
  echo "VIRHE: $SERVICE_USER ei pysty käynnistämään Hubia" >&2
  exit 1
fi
echo "OK: $SERVICE_USER pystyy käynnistämään Hubin"

install -o root -g root -m 0644 "$STAGE/config/systemd/$UNIT" "/etc/systemd/system/$UNIT"
echo "OK: palvelutiedosto /etc/systemd/system/$UNIT asennettu"
systemctl daemon-reload

if [ "$WAS_ACTIVE" -eq 1 ]; then
  systemctl start "$UNIT"
  sleep 3
  if systemctl is-active --quiet "$UNIT"; then
    echo "OK: $UNIT käynnistetty uudelleen"
  else
    echo "VIRHE: $UNIT ei käynnistynyt. Katso: sudo journalctl -u $UNIT -n 50" >&2
    exit 1
  fi
else
  echo "$UNIT ei ollut käynnissä, joten se jää pysäytetyksi. Käynnistys: sudo systemctl enable --now $UNIT"
fi
echo "Valmis: $(cat "$TARGET/DEPLOYED")"
