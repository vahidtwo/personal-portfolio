"""Pytest fixtures with isolated SQLite per test."""

from __future__ import annotations

import ipaddress
import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _purge_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "inventory.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-fixed-for-sessions")
    monkeypatch.setenv("ENABLE_INTERNAL_SCHEDULER", "0")
    _purge_app_modules()
    from app.db import SessionLocal, init_db
    from app.main import app

    init_db()
    with TestClient(app) as test_client:
        yield test_client
    import app.db as db_module

    db_module.engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    yield
    import app.rate_limit as rate_limit

    rate_limit.reset_all()


# ---- parallel safety (pytest-xdist) -------------------------------------------------------------
# Every test that uses ``client`` already gets its own SQLite file under tmp_path (unique per test and
# per xdist worker). These guards make sure nothing else is shared between workers.

@pytest.fixture(scope="session", autouse=True)
def _per_worker_data_dir(tmp_path_factory: pytest.TempPathFactory, worker_id: str):
    """Default DATA_DIR/DATABASE_URL for code imported outside ``client``: one dir per worker, never ./data."""
    mp = pytest.MonkeyPatch()
    d = tmp_path_factory.mktemp(f"data-{worker_id}")
    mp.setenv("DATA_DIR", str(d))
    mp.setenv("DATABASE_URL", f"sqlite:///{d / 'inventory.db'}")
    mp.setenv("ENABLE_INTERNAL_SCHEDULER", "0")
    yield d
    mp.undo()


def _is_local(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return True
    if host in ("localhost", "testserver", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a hostname: real DNS/network


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch):
    """Tests never reach the internet (price APIs, Firebase...). Loopback and Unix sockets stay allowed."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address):
            raise RuntimeError(f"real network access blocked in tests: {address!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo(socket.getaddrinfo))


def _guarded_getaddrinfo(real):
    def wrapper(host, *args, **kwargs):
        if host is not None and not _is_local((host,)) and host != "testserver":
            raise RuntimeError(f"real DNS lookup blocked in tests: {host!r}")
        return real(host, *args, **kwargs)

    return wrapper
