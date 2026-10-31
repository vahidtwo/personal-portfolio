"""The server must not start without a real SECRET_KEY."""
from __future__ import annotations

import importlib
import sys

import pytest


def _load_main(monkeypatch, tmp_path, value):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'inventory.db'}")
    if value is None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("SECRET_KEY", value)
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    return importlib.import_module("app.main")


@pytest.mark.parametrize("value", [None, "", "   ", "\t", " \n ", "change-me-in-dokploy", "change-me-to-a-long-random-string"])
def test_refuses_missing_or_placeholder_key(monkeypatch, tmp_path, value):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _load_main(monkeypatch, tmp_path, value)
    assert not (tmp_path / "secret_key").exists()


def test_starts_with_explicit_key(monkeypatch, tmp_path):
    main = _load_main(monkeypatch, tmp_path, "explicit-test-key")
    assert main._secret_key() == "explicit-test-key"


def test_compose_has_no_placeholder_default():
    from pathlib import Path

    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
    web = compose.split("  # Optional backup")[0]
    assert "change-me-in-dokploy" not in web


@pytest.mark.parametrize("value", ["  spaced-key  ", "key\twith-tab\n", "\tk"])
def test_key_is_used_exactly_as_set(monkeypatch, tmp_path, value):
    main = _load_main(monkeypatch, tmp_path, value)
    assert main._secret_key() == value


def test_placeholder_with_spaces_is_a_different_key(monkeypatch, tmp_path):
    main = _load_main(monkeypatch, tmp_path, " change-me-in-dokploy ")
    assert main._secret_key() == " change-me-in-dokploy "
