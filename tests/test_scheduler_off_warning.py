"""Turning the internal scheduler off must be loud: nightly backups stop with it."""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from tests.test_holdings import no_network  # noqa: F401


def test_warning_names_backups(caplog):
    from app import main

    caplog.set_level(logging.WARNING, logger="app.main")
    main.warn_scheduler_off()
    text = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "ENABLE_INTERNAL_SCHEDULER is off" in text and "backups will NOT run" in text


def test_startup_warns_when_scheduler_off(monkeypatch, caplog, no_network):
    from app import main

    monkeypatch.setattr(main, "ENABLE_INTERNAL_SCHEDULER", False)
    started = []
    monkeypatch.setattr(main, "start_nightly_backup", lambda: started.append("backup"))
    caplog.set_level(logging.WARNING, logger="app.main")
    with TestClient(main.app):
        pass
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == "app.main"]
    assert any(main.SCHEDULER_OFF_WARNING == r.getMessage() for r in warnings)
    assert not started


def test_startup_is_quiet_when_scheduler_on(monkeypatch, caplog, no_network):
    from app import main

    monkeypatch.setattr(main, "ENABLE_INTERNAL_SCHEDULER", True)
    monkeypatch.setattr(main, "start_hourly_scheduler", lambda: None)
    monkeypatch.setattr(main, "start_nightly_backup", lambda: None)
    caplog.set_level(logging.WARNING, logger="app.main")
    with TestClient(main.app):
        pass
    assert not any(main.SCHEDULER_OFF_WARNING == r.getMessage() for r in caplog.records)
