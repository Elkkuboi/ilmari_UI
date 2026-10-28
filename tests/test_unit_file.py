"""Hubin palvelutiedosto käsin kirjoitettuna totuutena (aiops ADR-0013 kohta 2).

Malli on aiops-repon config/systemd/aiops-gateway.service. Erot on kirjoitettu tähän näkyviin: julkaisuryhmä,
/srv:n piilotus julkaisua, peruskirjaa ja dokumentteja lukuun ottamatta, /etc/aiops:n piilotus, ei kirjoitettavia polkuja ja UMask 0077.
"""

from pathlib import Path

UNIT = Path(__file__).parents[1] / "config" / "systemd" / "ilmari-hub.service"


def settings() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in UNIT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        key, _, value = line.partition("=")
        result.setdefault(key.strip(), []).append(value.strip())
    return result


def test_unit_matches_hand_written_specification():
    assert settings() == {
        "Description": ["Ilmari Hub: julkaistujen ajojen lukunäkymä Tailscale Serven polussa /hub"],
        "Type": ["simple"],
        "User": ["ilmari-hub"],
        "Group": ["ilmari-hub"],
        "SupplementaryGroups": ["ilmari-julkaisu"],
        "UMask": ["0077"],
        "WorkingDirectory": ["/"],
        "ExecStart": ["/opt/ilmari-hub/.venv/bin/ilmari-ui --config /etc/ilmari-hub/hub.toml --socket /run/ilmari-hub/hub.sock"],
        "Restart": ["on-failure"],
        "RestartSec": ["5"],
        "TimeoutStopSec": ["20"],
        "RuntimeDirectory": ["ilmari-hub"],
        "RuntimeDirectoryMode": ["0700"],
        "NoNewPrivileges": ["yes"],
        "ProtectSystem": ["strict"],
        "ProtectHome": ["yes"],
        "PrivateTmp": ["yes"],
        "TemporaryFileSystem": ["/srv:ro"],
        "BindReadOnlyPaths": ["/srv/aiops/ilmari/ajot", "-/srv/aiops/ilmari/peruskirja",
                              "-/srv/aiops/ilmari/dokumentit"],
        "InaccessiblePaths": ["/etc/aiops"],
        "PrivateNetwork": ["yes"],
        "RestrictAddressFamilies": ["AF_UNIX"],
        "PrivateDevices": ["yes"],
        "ProtectClock": ["yes"],
        "ProtectKernelTunables": ["yes"],
        "ProtectKernelModules": ["yes"],
        "ProtectKernelLogs": ["yes"],
        "ProtectControlGroups": ["yes"],
        "ProtectHostname": ["yes"],
        "ProtectProc": ["invisible"],
        "CapabilityBoundingSet": [""],
        "RestrictNamespaces": ["yes"],
        "RestrictSUIDSGID": ["yes"],
        "LockPersonality": ["yes"],
        "RestrictRealtime": ["yes"],
        "MemoryDenyWriteExecute": ["yes"],
        "RemoveIPC": ["yes"],
        "SystemCallArchitectures": ["native"],
        "SystemCallFilter": ["@system-service"],
        "SystemCallErrorNumber": ["EPERM"],
        "WantedBy": ["multi-user.target"],
    }


def test_no_writable_paths_privileged_groups_or_demo():
    s = settings()
    assert "ReadWritePaths" not in s and "BindPaths" not in s
    assert not ({"aiops", "docker", "root", "sudo", "adm"} & set(" ".join(s["SupplementaryGroups"]).split()))
    assert "--demo" not in s["ExecStart"][0] and "--runs-dir" not in s["ExecStart"][0]
