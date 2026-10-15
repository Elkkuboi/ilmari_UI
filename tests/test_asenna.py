"""scripts/asenna.sh: samat periaatteet kuin aiops-repon deploy.sh:ssa (aiops ADR-0013 kohta 1).

Skriptiä ei ajeta testeissä (se vaatii rootin ja systemd:n). Tarkistetaan syntaksi ja sitovat kohdat tekstistä.
"""

from pathlib import Path
import shutil
import subprocess

import pytest

SKRIPTI = Path(__file__).parents[1] / "scripts" / "asenna.sh"
TEKSTI = SKRIPTI.read_text(encoding="utf-8")


def test_syntaksi_ja_shellcheck():
    assert subprocess.run(["bash", "-n", str(SKRIPTI)], capture_output=True).returncode == 0
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck puuttuu")
    assert subprocess.run(["shellcheck", str(SKRIPTI)], capture_output=True).returncode == 0


@pytest.mark.parametrize("kohta", [
    "set -euo pipefail",
    "TARGET=/opt/ilmari-hub",
    'status --porcelain',                       # vain commitoitu koodi
    '"${GIT[@]}" archive HEAD | tar -x -C "$STAGE"',
    'install -d -o root -g root -m 0755 "$TARGET"',
    '"$UV" sync --frozen --no-dev --no-editable --python /usr/bin/python3.12 --quiet',
    'echo "$COMMIT $(date -Iseconds)" > "$TARGET/DEPLOYED"',
    'chown -R root:root "$TARGET"',
    '(cd / && sudo -u "$SERVICE_USER" "$TARGET/.venv/bin/ilmari-ui" --help >/dev/null)',
    'install -o root -g root -m 0644 "$STAGE/config/systemd/$UNIT" "/etc/systemd/system/$UNIT"',
])
def test_sitova_kohta_on_mukana(kohta):
    assert kohta in TEKSTI


def test_vaatii_rootin_ja_palvelukayttajan_ennen_muutoksia():
    ensimmainen_muutos = TEKSTI.index("systemctl stop")
    for ehto in ('[ "$(id -u)" -eq 0 ]', 'getent passwd "$SERVICE_USER"', "status --porcelain"):
        assert TEKSTI.index(ehto) < ensimmainen_muutos


def test_ei_kaynnista_palvelua_joka_ei_ollut_kaynnissa():
    alku = TEKSTI.index('if [ "$WAS_ACTIVE" -eq 1 ]; then\n  systemctl start')
    assert "systemctl enable" not in TEKSTI.replace("Käynnistys: sudo systemctl enable --now $UNIT", "")
    assert TEKSTI.count("systemctl start") == 1 and alku > 0


def test_tyhjentaa_vain_oman_kohteensa():
    assert TEKSTI.count("-delete") == 1 and 'find "$TARGET" -mindepth 1 -delete' in TEKSTI
    assert "/opt/aiops" not in TEKSTI.replace("aiops-repon", "")
