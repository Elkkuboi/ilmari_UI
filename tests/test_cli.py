"""The public launcher can bind only its owner-only Unix socket."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from ilmari_ui import cli


@pytest.fixture
def private_directory():
    # A short path avoids Linux's independent sockaddr_un length constraint.
    folder = Path(tempfile.mkdtemp(prefix="ilmari-test-", dir="/tmp"))
    try:
        yield folder
    finally:
        shutil.rmtree(folder)


@pytest.fixture(autouse=True)
def restore_umask():
    previous = os.umask(0o077)
    os.umask(previous)
    try:
        yield
    finally:
        os.umask(previous)


def run_main(monkeypatch, *arguments: str):
    monkeypatch.setattr(sys, "argv", ["ilmari-ui", *arguments])
    cli.main()


def test_launcher_default_is_private_unix_and_demo_disabled(monkeypatch, private_directory):
    monkeypatch.chdir(private_directory)
    observed = {}

    class ProbeServer:
        def __init__(self, config):
            observed["config"] = config

        def run(self, *, sockets):
            assert len(sockets) == 1
            server = sockets[0]
            assert server.family == socket.AF_UNIX
            address = private_directory / ".runtime" / "hub.sock"
            assert server.getsockname() == str(address)
            assert stat.S_ISSOCK(address.stat().st_mode)
            assert stat.S_IMODE(address.stat().st_mode) == 0o600
            assert stat.S_IMODE(address.parent.stat().st_mode) == 0o700
            observed["served"] = True

    monkeypatch.setattr(cli.uvicorn, "Server", ProbeServer)
    run_main(monkeypatch)
    assert observed["served"]
    assert observed["config"].proxy_headers is False
    assert observed["config"].server_header is False
    assert observed["config"].access_log is False
    assert not (private_directory / ".runtime" / "hub.sock").exists()
    client = TestClient(observed["config"].app, base_url="http://ilmari.local", client=None)
    assert "DEMO – ESIMERKKIDATA" not in client.get("/hub?demo=1").text


def test_explicit_socket_demo_and_run_directory_are_passed_without_tcp(monkeypatch, private_directory):
    address = private_directory / "hub.sock"
    publication = private_directory / "published-runs"
    captured = {}

    class ProbeServer:
        def __init__(self, config):
            captured["config"] = config

        def run(self, *, sockets):
            assert sockets[0].family == socket.AF_UNIX
            assert sockets[0].getsockname() == str(address)

    monkeypatch.setattr(cli.uvicorn, "Server", ProbeServer)
    run_main(monkeypatch, "--socket", str(address), "--demo", "--runs-dir", str(publication))
    client = TestClient(captured["config"].app, base_url="http://ilmari.local", client=None)
    assert "DEMO – ESIMERKKIDATA" in client.get("/hub?demo=1").text
    assert not address.exists()


@pytest.mark.parametrize("arguments", [("--host", "0.0.0.0"), ("--port", "8000"), ("--uds", "/tmp/arbitrary")])
def test_no_tcp_or_alternative_uvicorn_option_is_exposed(monkeypatch, arguments):
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, *arguments)
    assert failure.value.code == 2


def test_shared_socket_directory_is_refused(monkeypatch, private_directory):
    folder = private_directory / "shared"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(folder / "hub.sock"))
    assert failure.value.code == 2
    assert not (folder / "hub.sock").exists()


def test_socket_directory_must_belong_to_current_user(monkeypatch, private_directory):
    current_uid = os.getuid()
    monkeypatch.setattr(cli.os, "getuid", lambda: current_uid + 1)
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(private_directory / "hub.sock"))
    assert failure.value.code == 2
    assert not (private_directory / "hub.sock").exists()


@pytest.mark.parametrize("ancestor", [False, True])
def test_symbolic_link_socket_directory_or_ancestor_is_refused(monkeypatch, private_directory, ancestor):
    real = private_directory / "real"
    real.mkdir(mode=0o700)
    linked = private_directory / "link"
    linked.symlink_to(real, target_is_directory=True)
    address = linked / "child" / "hub.sock" if ancestor else linked / "hub.sock"
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(address))
    assert failure.value.code == 2
    assert not (real / "hub.sock").exists()
    assert not (real / "child").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "socket"])
def test_existing_path_is_never_removed_or_replaced(monkeypatch, private_directory, kind):
    address = private_directory / "hub.sock"
    held_socket = None
    if kind == "file":
        address.write_bytes(b"preserve me")
    elif kind == "directory":
        address.mkdir(mode=0o700)
    elif kind == "symlink":
        address.symlink_to(private_directory / "nonexistent")
    else:
        held_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        held_socket.bind(str(address))
    before = address.lstat()
    try:
        with pytest.raises(SystemExit) as failure:
            run_main(monkeypatch, "--socket", str(address))
        assert failure.value.code == 2
        after = address.lstat()
        assert (before.st_ino, before.st_mode) == (after.st_ino, after.st_mode)
        if kind == "file":
            assert address.read_bytes() == b"preserve me"
    finally:
        if held_socket:
            held_socket.close()


def test_overlong_socket_path_is_rejected_before_creating_directories(monkeypatch, private_directory):
    folder = private_directory / ("x" * 100)
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(folder / "hub.sock"))
    assert failure.value.code == 2
    assert not folder.exists()


@pytest.mark.parametrize("publication", ["relative-publication", "/", "/tmp/../publication"])
def test_invalid_publication_root_is_refused_before_creating_a_socket(monkeypatch, private_directory, publication):
    socket_dir = private_directory / "runtime"
    address = socket_dir / "hub.sock"
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(address), "--runs-dir", publication)
    assert failure.value.code == 2
    assert not address.exists()
    assert not socket_dir.exists()


def test_socket_is_cleaned_when_server_fails(monkeypatch, private_directory):
    address = private_directory / "hub.sock"

    class FailingServer:
        def __init__(self, config):
            pass

        def run(self, *, sockets):
            assert address.exists()
            raise RuntimeError("simulated startup failure")

    monkeypatch.setattr(cli.uvicorn, "Server", FailingServer)
    with pytest.raises(RuntimeError, match="simulated"):
        run_main(monkeypatch, "--socket", str(address))
    assert not address.exists()


def test_shutdown_does_not_unlink_a_replacement_file(monkeypatch, private_directory):
    address = private_directory / "hub.sock"

    class ReplacementServer:
        def __init__(self, config):
            pass

        def run(self, *, sockets):
            address.unlink()
            address.write_bytes(b"belongs to a later process")

    monkeypatch.setattr(cli.uvicorn, "Server", ReplacementServer)
    run_main(monkeypatch, "--socket", str(address))
    assert address.read_bytes() == b"belongs to a later process"


def test_real_server_sigterm_cleans_socket_and_allows_restart(private_directory):
    """Exercise the shipped launcher and signal handling over real Unix HTTP."""
    address = private_directory / "hub.sock"
    children = []

    def wait_until_serving(child):
        deadline = time.monotonic() + 5
        last_error = "not ready"
        with httpx.Client(
            transport=httpx.HTTPTransport(uds=str(address)),
            base_url="http://ilmari.local",
            timeout=0.25,
        ) as client:
            while time.monotonic() < deadline:
                assert child.poll() is None, f"Launcher exited before serving: {child.returncode}"
                try:
                    response = client.get("/hub?demo=1")
                except httpx.TransportError as error:
                    last_error = type(error).__name__
                else:
                    assert response.status_code == 200
                    assert "DEMO – ESIMERKKIDATA" in response.text
                    assert stat.S_ISSOCK(address.stat().st_mode)
                    assert stat.S_IMODE(address.stat().st_mode) == 0o600
                    return
                time.sleep(0.025)
        pytest.fail(f"Launcher did not serve Unix HTTP within 5 seconds ({last_error})")

    try:
        for _ in range(2):
            child = subprocess.Popen(
                [sys.executable, "-m", "ilmari_ui.cli", "--socket", str(address), "--demo"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            children.append(child)
            wait_until_serving(child)
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=5)
            assert not address.exists(), "SIGTERM left the socket path occupied"
    finally:
        # Never signal a process other than one created by this test.
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


# --------------------------------------------------------------------------------------------------
# Tuotantotila (--config, aiops ADR-0013)
# --------------------------------------------------------------------------------------------------

def _hub_toml(folder: Path, julkaisut: Path) -> Path:
    config = folder / "hub.toml"
    config.write_text(
        '[hub]\nrp_id = "tyoasema.taild1a5b7.ts.net"\n'
        f'julkaisut = "{julkaisut}"\n\n'
        '[hub.kayttajat]\n"Elkkuboi@github" = "elias"\n', encoding="utf-8")
    return config


def test_production_config_enables_identity_and_prefix(monkeypatch, private_directory):
    address = private_directory / "hub.sock"
    julkaisut = private_directory / "ajot"
    julkaisut.mkdir()
    captured = {}

    class ProbeServer:
        def __init__(self, config):
            captured["config"] = config

        def run(self, *, sockets):
            assert sockets[0].family == socket.AF_UNIX and sockets[0].getsockname() == str(address)

    monkeypatch.setattr(cli.uvicorn, "Server", ProbeServer)
    run_main(monkeypatch, "--socket", str(address), "--config", str(_hub_toml(private_directory, julkaisut)))
    app = captured["config"].app
    serve = {"x-forwarded-host": "tyoasema.taild1a5b7.ts.net", "tailscale-user-login": "Elkkuboi@github"}
    with TestClient(app, base_url="http://localhost", client=None) as client:
        assert client.get("/ajot", headers=serve).status_code == 200            # Serven polku ilman /hub-etuliitettä
        assert client.get("/ajot", headers={**serve, "tailscale-user-login": "muu@github"}).status_code == 403
        assert client.get("/hub", headers={"host": "ilmari.local"}).status_code == 421   # kehitystila ei ole päällä
    assert not address.exists()


@pytest.mark.parametrize("extra", [("--demo",), ("--runs-dir", "/srv/aiops/ilmari/ajot")])
def test_production_config_refuses_demo_and_runs_dir(monkeypatch, private_directory, extra):
    socket_dir = private_directory / "runtime"
    config = _hub_toml(private_directory, private_directory / "ajot")
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(socket_dir / "hub.sock"), "--config", str(config), *extra)
    assert failure.value.code == 2
    assert not socket_dir.exists()


@pytest.mark.parametrize("content", [None, "[hub]\nrp_id = 1\n", "ei toml"])
def test_invalid_or_missing_config_is_refused_before_creating_a_socket(monkeypatch, private_directory, content):
    socket_dir = private_directory / "runtime"
    config = private_directory / "hub.toml"
    if content is not None:
        config.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        run_main(monkeypatch, "--socket", str(socket_dir / "hub.sock"), "--config", str(config))
    assert failure.value.code == 2
    assert not socket_dir.exists()
