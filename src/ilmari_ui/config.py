"""Tuotantokonfiguraatio /etc/ilmari-hub/hub.toml (aiops ADR-0013 kohta 2).

    [hub]
    rp_id = "tyoasema.tailnet.ts.net"          # työaseman nimi tailnetissä; sama kuin gatewayn RP ID
    julkaisut = "/srv/aiops/ilmari/ajot"       # julkaisuhakemisto, josta Hub lukee ajot
    peruskirja = "/srv/aiops/ilmari/peruskirja" # valinnainen; oletus tämä (ADR-0013 tarkennus 2026-10-20)

    [hub.kayttajat]
    "tunnus@github" = "elias"                  # Tailscale-tunnus (LoginName) = nimi

Tiedosto luetaan tiukasti kuten aiops.toml: tuntematon avain on virhe, ja puuttuva tai kelvoton tiedosto estää
käynnistyksen. Tiedosto on root:ilmari-hub 0640, joten Hub voi lukea sen mutta ei muuttaa. Hub ei voi lukea
tiedostoa /etc/aiops/aiops.toml, joten tunnuslista on sen [gateway.kayttajat]-taulun kopio (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from types import MappingProxyType

DEFAULT_CONFIG = Path("/etc/ilmari-hub/hub.toml")
DEFAULT_RULES_DIR = Path("/srv/aiops/ilmari/peruskirja")

# Samat muodot kuin aiops-repon src/aiops/config.py:ssä.
_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_LOGIN = re.compile(r"^[!-~]{1,254}$")
_PATH = re.compile(r"^(/[A-Za-z0-9._-]+)+$")


class ConfigError(Exception):
    """Konfiguraatio puuttuu tai ei kelpaa; viesti kertoo, mitä korjata."""


@dataclass(frozen=True)
class HubConfig:
    rp_id: str
    users: MappingProxyType  # Tailscale-tunnus → nimi
    runs_dir: Path
    rules_dir: Path = DEFAULT_RULES_DIR  # peruskirja (aiops docs/saannot.md), jonka aiopsin deploy.sh julkaisee

    @property
    def origin(self) -> str:
        """Serve julkaisee portissa 443, joten alkuperässä ei ole porttia (kuten aiopsin origin_for)."""
        return f"https://{self.rp_id}"


def _unknown(table: dict, known: set[str], where: str, problems: list[str]) -> None:
    for key in sorted(set(table) - known):
        problems.append(f"{where}: tuntematon avain {key!r}")


def parse_config(data: dict) -> HubConfig:
    problems: list[str] = []
    _unknown(data, {"hub"}, "tiedosto", problems)
    hub = data.get("hub")
    if not isinstance(hub, dict):
        raise ConfigError("[hub] puuttuu")
    _unknown(hub, {"rp_id", "julkaisut", "peruskirja", "kayttajat"}, "[hub]", problems)

    rp_id = hub.get("rp_id")
    if not isinstance(rp_id, str) or not _HOSTNAME.fullmatch(rp_id):
        problems.append("[hub] rp_id: anna nimi pienillä kirjaimilla ilman porttia ja pistettä lopussa")

    julkaisut = hub.get("julkaisut")
    if not isinstance(julkaisut, str) or not _PATH.fullmatch(julkaisut) or {".", ".."} & set(julkaisut.split("/")):
        problems.append("[hub] julkaisut: anna absoluuttinen polku, jossa on vain nimiä (ei '.'- tai '..'-osia)")

    peruskirja = hub.get("peruskirja", str(DEFAULT_RULES_DIR))
    if not isinstance(peruskirja, str) or not _PATH.fullmatch(peruskirja) or {".", ".."} & set(peruskirja.split("/")):
        problems.append("[hub] peruskirja: anna absoluuttinen polku, jossa on vain nimiä (ei '.'- tai '..'-osia)")
    elif peruskirja == julkaisut:
        problems.append("[hub] peruskirja: polku ei saa olla sama kuin julkaisut")

    users: dict[str, str] = {}
    kayttajat = hub.get("kayttajat")
    if not isinstance(kayttajat, dict) or not kayttajat:
        problems.append("[hub.kayttajat] puuttuu tai on tyhjä")
    else:
        for login, name in kayttajat.items():
            if not _LOGIN.fullmatch(login):
                problems.append(f"[hub.kayttajat]: kelvoton tunnus {login!r}")
            elif not isinstance(name, str) or not _NAME.fullmatch(name):
                problems.append(f"[hub.kayttajat] {login!r}: kelvoton nimi {name!r}")
            else:
                users[login] = name

    if problems:
        raise ConfigError("; ".join(problems))
    return HubConfig(rp_id=rp_id, users=MappingProxyType(users), runs_dir=Path(julkaisut), rules_dir=Path(peruskirja))


def load_config(path: Path = DEFAULT_CONFIG) -> HubConfig:
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise ConfigError(f"konfiguraatiota {path} ei voi lukea: {e.strerror}") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path} ei ole kelvollista TOMLia: {e}") from None
    return parse_config(data)
