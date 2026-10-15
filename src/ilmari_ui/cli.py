"""Hubin käynnistin: vain omistajan Unix-soketti, ei TCP-vaihtoehtoa.

Kehitystila: ilman --config-valitsinta (Host ilmari.local, valinnainen --demo ja --runs-dir).
Tuotantotila: --config /etc/ilmari-hub/hub.toml (aiops ADR-0013). Julkaisujuuri ja sallitut Tailscale-tunnukset tulevat
konfiguraatiosta, eikä esimerkkitilaa tai --runs-dir-valitsinta hyväksytä.
"""

import argparse
from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import stat

import uvicorn

from .app import Settings, create_app
from .config import ConfigError, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Ilmari Hubin paikallinen lukukäyttöliittymä (Unix-soketti).")
    parser.add_argument("--socket", type=Path, default=Path(".runtime/hub.sock"))
    parser.add_argument("--demo", action="store_true", help="Salli eristetty esimerkkidata kyselyllä demo=1.")
    parser.add_argument("--runs-dir", type=Path, help="Erikseen hyväksytty julkaisuhakemisto; ei raakatuloksia.")
    parser.add_argument("--config", type=Path, help="Tuotantokonfiguraatio (esim. /etc/ilmari-hub/hub.toml, ADR-0013).")
    args = parser.parse_args()
    hub_config = None
    if args.config is not None:
        if args.demo or args.runs_dir is not None:
            parser.error("Tuotantotilassa (--config) ei käytetä valitsimia --demo eikä --runs-dir.")
        try:
            hub_config = load_config(args.config)
        except ConfigError as error:
            parser.error(str(error))
        args.runs_dir = hub_config.runs_dir
    if args.runs_dir is not None and (not args.runs_dir.is_absolute() or args.runs_dir == Path("/") or ".." in args.runs_dir.parts):
        parser.error("Julkaisujuuren pitää olla yksilöity absoluuttinen hakemistopolku ilman '..'-osia.")
    address = args.socket.absolute()
    if len(str(address).encode()) > 100:
        parser.error("Soketin polku on liian pitkä.")
    for ancestor in (address.parent, *address.parent.parents):
        if ancestor.is_symlink():
            parser.error("Sokettihakemiston polku ei saa sisältää symbolisia linkkejä.")
    address.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = address.parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        parser.error("Sokettihakemiston pitää kuulua käyttäjälle ja sen oikeuksien pitää olla 0700.")
    if address.exists() or address.is_symlink():
        parser.error("Soketin polku on jo käytössä. Tarkista ja pysäytä aiempi oma kehityspalvelin.")
    os.umask(0o077)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(address))
        os.chmod(address, 0o600)
        identity = address.stat()

        def cleanup_socket() -> None:
            try:
                current = address.lstat()
                if current.st_ino == identity.st_ino and current.st_dev == identity.st_dev and stat.S_ISSOCK(current.st_mode):
                    address.unlink()
            except FileNotFoundError:
                pass

        @asynccontextmanager
        async def lifespan(_app):
            try:
                yield
            finally:
                # Uvicorn re-raises SIGTERM after shutdown. Clean the path before
                # that signal can terminate Python without unwinding this frame.
                cleanup_socket()

        try:
            application = create_app(Settings(runs_dir=args.runs_dir, demo_enabled=args.demo, identity=hub_config))
            application.router.lifespan_context = lifespan
            config = uvicorn.Config(application, log_level="info", proxy_headers=False, server_header=False, access_log=False)
            uvicorn.Server(config).run(sockets=[server])
        finally:
            cleanup_socket()


if __name__ == "__main__":
    main()
