"""Turvallinen luku kiinteän hakemiston alta: yhteinen pohja kaikille Hubin lukijoille.

Hakemisto avataan kuvaajalla juuresta alkaen (O_NOFOLLOW, O_DIRECTORY): symbolinen linkki tai muu tiedostotyyppi
polussa on virhe, ja jokainen osa tarkistetaan uudelleen luvun jälkeen, joten vaihto kesken luvun huomataan. Tiedosto
luetaan vain, jos se on tavallinen tiedosto yhdellä linkillä, kokoraja ei ylity, omistaja kelpaa (tuotannossa) eikä
tiedosto muutu luvun aikana. Virheilmoitukset eivät koskaan sisällä absoluuttisia polkuja.
"""

from __future__ import annotations

import errno
import math
import os
import re
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


class ReadFailure(ValueError):
    """Turvallinen virhe näytettäväksi; viestissä ei ole tiedostopolkuja."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _snapshot(info: os.stat_result) -> tuple[int, ...]:
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _fail_os(error: OSError) -> ReadFailure:
    if error.errno == errno.ENOENT:
        return ReadFailure("not_found", "Tiedostoa tai hakemistoa ei ole.")
    if error.errno in {errno.EACCES, errno.EPERM}:
        return ReadFailure("forbidden", "Lukemiseen ei ole käyttöoikeutta.")
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        return ReadFailure("unsafe_path", "Polku ei ole turvallinen hakemisto.")
    return ReadFailure("read_error", "Lukeminen epäonnistui.")


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ReadFailure("timeout", "Lukuaikaraja ylittyi.")


class Hakemisto:
    """Kiinteä, absoluuttinen hakemisto, joka avataan kuvaajalla polun jokainen osa tarkistaen."""

    def __init__(self, root: str | Path, *, timeout_seconds: float = 1.0):
        raw = os.fspath(root)
        if not isinstance(raw, str) or not raw.startswith("/") or "\\" in raw or "\0" in raw:
            raise ValueError("Hakemiston on oltava turvallinen absoluuttinen polku.")
        components = raw.split("/")[1:]
        if not components or any(part in {"", ".", ".."} for part in components):
            raise ValueError("Hakemiston polku sisältää kielletyn osan.")
        if type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 10:
            raise ValueError("Lukuaikaraja ei ole sallittu.")
        self.root = raw
        self._components = tuple(components)
        self.timeout_seconds = timeout_seconds

    @contextmanager
    def juuri(self, deadline: float) -> Iterator[int]:
        fds: list[int] = []
        links: list[tuple[int, str, int]] = []
        try:
            fds.append(os.open("/", _DIRECTORY_FLAGS))
            for part in self._components:
                _check_deadline(deadline)
                parent = fds[-1]
                before = os.stat(part, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(before.st_mode):
                    raise ReadFailure("unsafe_path", "Polussa on kielletty tiedostotyyppi.")
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent)
                fds.append(child)
                if _identity(before) != _identity(os.fstat(child)):
                    raise ReadFailure("changed", "Hakemisto muuttui lukemisen aikana.")
                links.append((parent, part, child))
            yield fds[-1]
            _check_deadline(deadline)
            for parent, part, child in links:
                after = os.stat(part, dir_fd=parent, follow_symlinks=False)
                if _identity(after) != _identity(os.fstat(child)):
                    raise ReadFailure("changed", "Hakemisto muuttui lukemisen aikana.")
        except OSError as error:
            raise _fail_os(error) from None
        finally:
            for fd in reversed(fds):
                os.close(fd)

    @contextmanager
    def ali(self, root_fd: int, name: str) -> Iterator[int]:
        """Juuren välitön alihakemisto (esim. kehitystyön numero); linkki tai muu tyyppi on virhe."""
        fd: int | None = None
        try:
            before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise ReadFailure("unsafe_path", "Alihakemisto ei ole turvallinen hakemisto.")
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            if _identity(before) != _identity(os.fstat(fd)):
                raise ReadFailure("changed", "Alihakemisto muuttui lukemisen aikana.")
            yield fd
            after = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if _identity(after) != _identity(os.fstat(fd)):
                raise ReadFailure("changed", "Alihakemisto muuttui lukemisen aikana.")
        except OSError as error:
            raise _fail_os(error) from None
        finally:
            if fd is not None:
                os.close(fd)


def _lue(hd: int, nimi: str, omistaja: int | None, deadline: float, raja: int) -> bytes:
    """Tiedosto hakemistokuvaajan alta: tavallinen tiedosto, yksi linkki, kokoraja, omistaja (None = ei tarkistusta)
    ja muuttumattomuus luvun aikana."""
    fd: int | None = None
    try:
        ennen = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
        if not stat.S_ISREG(ennen.st_mode) or ennen.st_nlink != 1:
            raise ReadFailure("unsafe_file", "Tiedostotyyppi tai linkitys ei ole sallittu.")
        if omistaja is not None and ennen.st_uid != omistaja:
            raise ReadFailure("wrong_owner", "Tiedoston omistaja on väärä.")
        if ennen.st_size > raja:
            raise ReadFailure("too_large", "Tiedosto ylittää lukurajan.")
        fd = os.open(nimi, _FILE_FLAGS, dir_fd=hd)
        avattu = os.fstat(fd)
        if _snapshot(ennen) != _snapshot(avattu):
            raise ReadFailure("changed", "Tiedosto muuttui lukemisen aikana.")
        sisalto = bytearray()
        while True:
            _check_deadline(deadline)
            pala = os.read(fd, min(64 * 1024, raja + 1 - len(sisalto)))
            if not pala:
                break
            sisalto.extend(pala)
            if len(sisalto) > raja:
                raise ReadFailure("too_large", "Tiedosto ylittää lukurajan.")
        jalkeen = os.stat(nimi, dir_fd=hd, follow_symlinks=False)
        if _snapshot(avattu) != _snapshot(os.fstat(fd)) or _snapshot(avattu) != _snapshot(jalkeen):
            raise ReadFailure("changed", "Tiedosto muuttui lukemisen aikana.")
        return bytes(sisalto)
    except OSError as error:
        raise _fail_os(error) from None
    finally:
        if fd is not None:
            os.close(fd)
