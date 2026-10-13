"""Bounded, descriptor-relative reader for published Ilmari run files.

This reads a *publication*, never an agent workspace. The upstream semantic
schema is not available in this repository: JSON is safely inspected, not
interpreted as a verified run status, model name, or reviewer verdict.
"""

from __future__ import annotations

import errno
import json
import math
import os
import re
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

RUN_ID_RE = re.compile(r"[0-9]{8}-[0-9]{6}-yo-[a-z0-9]{1,32}\Z", re.ASCII)
FILE_LIMITS = {
    "meta.json": 64 * 1024,
    "raportti.md": 512 * 1024,
    "ehdotukset.jsonl": 512 * 1024,
    "sol-tulos.json": 256 * 1024,
    "luonnos.patch": 1024 * 1024,
}
JSONL_LINE_LIMIT = 16 * 1024
JSONL_RECORD_LIMIT = 512
SCAN_LIMIT = 2000
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY


@dataclass(frozen=True)
class ReadError:
    code: str
    file: str
    message: str


class ReadFailure(ValueError):
    """A safe public error; messages never include absolute filesystem paths."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    meta: dict[str, Any] | None
    errors: tuple[ReadError, ...] = ()

    @property
    def title(self) -> str:
        return self.run_id


@dataclass(frozen=True)
class RunDetail:
    run_id: str
    meta: dict[str, Any] | None
    report: str | None
    proposals: tuple[dict[str, Any], ...]
    sol_result: dict[str, Any] | list[Any] | None
    patch: str | None
    errors: tuple[ReadError, ...]


@dataclass(frozen=True)
class RunList:
    runs: tuple[RunSummary, ...]
    errors: tuple[ReadError, ...]
    state: str
    truncated: bool = False


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _snapshot(info: os.stat_result) -> tuple[int, ...]:
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _fail_os(error: OSError) -> ReadFailure:
    if error.errno == errno.ENOENT:
        return ReadFailure("not_found", "Julkaistua tiedostoa tai hakemistoa ei ole.")
    if error.errno in {errno.EACCES, errno.EPERM}:
        return ReadFailure("forbidden", "Julkaisun lukemiseen ei ole käyttöoikeutta.")
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        return ReadFailure("unsafe_path", "Julkaisun polku ei ole turvallinen hakemisto.")
    return ReadFailure("read_error", "Julkaisun lukeminen epäonnistui.")


def _valid_string(value: str, maximum: int) -> None:
    if len(value) > maximum:
        raise ReadFailure("invalid_json", "JSON-tekstin pituus ylittää lukurajan.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ReadFailure("invalid_json", "JSON sisältää kielletyn ohjausmerkin.")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ReadFailure("invalid_json", "JSON sisältää virheellisen Unicode-merkin.")
    if any(0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069 for c in value):
        raise ReadFailure("invalid_json", "JSON sisältää kielletyn suunnanohjausmerkin.")


def _validate_json(value: Any) -> None:
    remaining = 4096

    def visit(item: Any, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise ReadFailure("invalid_json", "JSON-rakenteen lukuraja ylittyi.")
        if type(item) is dict:
            if len(item) > 64:
                raise ReadFailure("invalid_json", "JSON-oliolla on liikaa kenttiä.")
            for key, child in item.items():
                if type(key) is not str or not key:
                    raise ReadFailure("invalid_json", "JSON-kentän nimi on virheellinen.")
                _valid_string(key, 100)
                if any(ord(c) < 32 for c in key):
                    raise ReadFailure("invalid_json", "JSON-kentän nimi sisältää ohjausmerkin.")
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > 1024:
                raise ReadFailure("invalid_json", "JSON-listalla on liikaa alkioita.")
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            _valid_string(item, 16 * 1024)
        elif type(item) is float:
            if not math.isfinite(item) or abs(item) > 1e100:
                raise ReadFailure("invalid_json", "JSON-numero ei ole sallittu äärellinen luku.")
        elif type(item) is int:
            if abs(item) >= 10**30:
                raise ReadFailure("invalid_json", "JSON-kokonaisluku ylittää lukurajan.")
        elif item is not None and type(item) is not bool:
            raise ReadFailure("invalid_json", "JSON-arvon tyyppi ei ole sallittu.")

    visit(value, 0)


def _parse_json(data: str, *, object_only: bool) -> dict[str, Any] | list[Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReadFailure("invalid_json", "JSON sisältää saman kentän kahdesti.")
            result[key] = value
        return result

    def integer(text: str) -> int:
        if len(text.lstrip("-")) > 30:
            raise ReadFailure("invalid_json", "JSON-kokonaisluku ylittää lukurajan.")
        return int(text)

    def constant(_: str) -> None:
        raise ReadFailure("invalid_json", "JSON sisältää kielletyn numeroarvon.")

    try:
        result = json.loads(data, object_pairs_hook=pairs_hook, parse_int=integer, parse_constant=constant)
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ReadFailure):
            raise
        raise ReadFailure("invalid_json", "Julkaisun JSON ei ole kelvollista.") from None
    if type(result) is not dict and (object_only or type(result) is not list):
        raise ReadFailure("invalid_json", "Julkaisun JSON-rakenne on virheellinen.")
    _validate_json(result)
    return result


class RunReader:
    """Read only the five allowed filenames below a fixed publication root.

    Each public operation has a bounded cooperative deadline. Use a trusted
    local filesystem; this does not interrupt an OS call stuck in a remote
    filesystem. Parent directories and files are checked again before returning.
    """

    def __init__(self, root: str | Path, *, max_runs: int = 100, timeout_seconds: float = 1.0):
        raw = os.fspath(root)
        if not isinstance(raw, str) or not raw.startswith("/") or "\\" in raw or "\0" in raw:
            raise ValueError("Julkaisuhakemiston on oltava turvallinen absoluuttinen polku.")
        components = raw.split("/")[1:]
        if not components or any(part in {"", ".", ".."} for part in components):
            raise ValueError("Julkaisuhakemiston polku sisältää kielletyn osan.")
        if type(max_runs) is not int or not 1 <= max_runs <= 1000:
            raise ValueError("Ajolistauksen raja ei ole sallittu.")
        if type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 10:
            raise ValueError("Lukuaikaraja ei ole sallittu.")
        self.root = raw
        self._components = tuple(components)
        self.max_runs = max_runs
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def validate_run_id(run_id: str) -> str:
        if type(run_id) is not str or RUN_ID_RE.fullmatch(run_id) is None:
            raise ReadFailure("invalid_run_id", "Ajotunnuksen muoto ei ole sallittu.")
        return run_id

    @staticmethod
    def _check_deadline(deadline: float) -> None:
        if time.monotonic() > deadline:
            raise ReadFailure("timeout", "Julkaisun lukuaikaraja ylittyi.")

    @contextmanager
    def _root_fd(self, deadline: float) -> Iterator[int]:
        fds: list[int] = []
        links: list[tuple[int, str, int]] = []
        try:
            fds.append(os.open("/", _DIRECTORY_FLAGS))
            for part in self._components:
                self._check_deadline(deadline)
                parent = fds[-1]
                before = os.stat(part, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(before.st_mode):
                    raise ReadFailure("unsafe_path", "Julkaisun polussa on kielletty tiedostotyyppi.")
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent)
                fds.append(child)
                if _identity(before) != _identity(os.fstat(child)):
                    raise ReadFailure("changed", "Julkaisuhakemisto muuttui lukemisen aikana.")
                links.append((parent, part, child))
            yield fds[-1]
            self._check_deadline(deadline)
            for parent, part, child in links:
                after = os.stat(part, dir_fd=parent, follow_symlinks=False)
                if _identity(after) != _identity(os.fstat(child)):
                    raise ReadFailure("changed", "Julkaisuhakemisto muuttui lukemisen aikana.")
        except OSError as error:
            raise _fail_os(error) from None
        finally:
            for fd in reversed(fds):
                os.close(fd)

    @contextmanager
    def _run_fd(self, root_fd: int, run_id: str) -> Iterator[int]:
        fd: int | None = None
        try:
            before = os.stat(run_id, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise ReadFailure("unsafe_path", "Ajojulkaisu ei ole turvallinen hakemisto.")
            fd = os.open(run_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            if _identity(before) != _identity(os.fstat(fd)):
                raise ReadFailure("changed", "Ajojulkaisu muuttui lukemisen aikana.")
            yield fd
            after = os.stat(run_id, dir_fd=root_fd, follow_symlinks=False)
            if _identity(after) != _identity(os.fstat(fd)):
                raise ReadFailure("changed", "Ajojulkaisu muuttui lukemisen aikana.")
        except OSError as error:
            raise _fail_os(error) from None
        finally:
            if fd is not None:
                os.close(fd)

    def _read_file(self, run_fd: int, name: str, deadline: float) -> str:
        maximum = FILE_LIMITS[name]
        fd: int | None = None
        try:
            self._check_deadline(deadline)
            before = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ReadFailure("unsafe_file", "Julkaisun tiedostotyyppi tai linkitys ei ole sallittu.")
            if before.st_size > maximum:
                raise ReadFailure("too_large", "Julkaistu tiedosto ylittää lukurajan.")
            fd = os.open(name, _FILE_FLAGS, dir_fd=run_fd)
            opened = os.fstat(fd)
            if _snapshot(before) != _snapshot(opened) or not stat.S_ISREG(opened.st_mode):
                raise ReadFailure("changed", "Julkaistu tiedosto muuttui lukemisen aikana.")
            content = bytearray()
            while True:
                self._check_deadline(deadline)
                chunk = os.read(fd, min(64 * 1024, maximum + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > maximum:
                    raise ReadFailure("too_large", "Julkaistu tiedosto ylittää lukurajan.")
            after = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
            if _snapshot(opened) != _snapshot(os.fstat(fd)) or _snapshot(opened) != _snapshot(after):
                raise ReadFailure("changed", "Julkaistu tiedosto muuttui lukemisen aikana.")
            self._check_deadline(deadline)
            try:
                text = content.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                raise ReadFailure("invalid_text", "Julkaisun teksti ei ole UTF-8-muodossa.") from None
            if any(ord(c) < 32 and c not in "\n\r\t" for c in text) or any(0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069 for c in text):
                raise ReadFailure("invalid_text", "Julkaisun teksti sisältää kielletyn merkin.")
            return text
        except OSError as error:
            raise _fail_os(error) from None
        finally:
            if fd is not None:
                os.close(fd)

    def _meta(self, fd: int, deadline: float) -> dict[str, Any]:
        result = _parse_json(self._read_file(fd, "meta.json", deadline), object_only=True)
        assert isinstance(result, dict)
        return result

    def list_runs(self) -> RunList:
        deadline = time.monotonic() + self.timeout_seconds
        errors: list[ReadError] = []
        runs: list[RunSummary] = []
        truncated = False
        try:
            with self._root_fd(deadline) as root_fd:
                # Bound directory scanning before sorting; never retain an
                # unbounded list of directory entries supplied by a publisher.
                names: list[str] = []
                with os.scandir(root_fd) as entries:
                    for index, entry in enumerate(entries):
                        self._check_deadline(deadline)
                        if index >= SCAN_LIMIT:
                            truncated = True
                            break
                        if RUN_ID_RE.fullmatch(entry.name) is not None:
                            names.append(entry.name)
                if len(names) > self.max_runs:
                    truncated = True
                for name in sorted(names, reverse=True)[: self.max_runs]:
                    self._check_deadline(deadline)
                    run_errors: list[ReadError] = []
                    meta = None
                    try:
                        with self._run_fd(root_fd, name) as fd:
                            try:
                                meta = self._meta(fd, deadline)
                            except ReadFailure as error:
                                run_errors.append(ReadError(error.code, "meta.json", error.message))
                    except ReadFailure as error:
                        errors.append(ReadError(error.code, name, error.message))
                        continue
                    runs.append(RunSummary(name, meta, tuple(run_errors)))
        except ReadFailure as error:
            # Results from a changed root cannot be trusted as a snapshot.
            return RunList((), (ReadError(error.code, "julkaisuhakemisto", error.message),), "not_available" if error.code == "not_found" else "error")
        return RunList(tuple(runs), tuple(errors), "ready" if runs else "error" if errors else "empty", truncated)

    def read_run(self, run_id: str) -> RunDetail:
        self.validate_run_id(run_id)
        deadline = time.monotonic() + self.timeout_seconds
        errors: list[ReadError] = []
        values: dict[str, Any] = {
            "meta.json": None,
            "raportti.md": None,
            "ehdotukset.jsonl": (),
            "sol-tulos.json": None,
            "luonnos.patch": None,
        }
        with self._root_fd(deadline) as root_fd:
            with self._run_fd(root_fd, run_id) as fd:
                for name in FILE_LIMITS:
                    try:
                        text = self._read_file(fd, name, deadline)
                        if name == "meta.json":
                            values[name] = _parse_json(text, object_only=True)
                        elif name == "sol-tulos.json":
                            values[name] = _parse_json(text, object_only=False)
                        elif name == "ehdotukset.jsonl":
                            proposals = []
                            lines = text.split("\n") if text else []
                            if lines and lines[-1] == "":
                                lines.pop()
                            for line in lines:
                                self._check_deadline(deadline)
                                if not line.strip():
                                    raise ReadFailure("invalid_jsonl", "JSONL-julkaisu sisältää tyhjän rivin.")
                                if len(line.encode("utf-8")) > JSONL_LINE_LIMIT or len(proposals) >= JSONL_RECORD_LIMIT:
                                    raise ReadFailure("too_large", "JSONL-rivien lukuraja ylittyi.")
                                proposals.append(_parse_json(line, object_only=True))
                            values[name] = tuple(proposals)
                        else:
                            values[name] = text
                    except ReadFailure as error:
                        errors.append(ReadError(error.code, name, error.message))
        return RunDetail(run_id, values["meta.json"], values["raportti.md"], values["ehdotukset.jsonl"], values["sol-tulos.json"], values["luonnos.patch"], tuple(errors))
