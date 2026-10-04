"""Pytest fixtures with isolated SQLite per test."""

from __future__ import annotations

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
