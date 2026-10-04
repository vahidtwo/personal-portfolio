"""Firebase Admin env parsing (no network)."""

from __future__ import annotations

import pytest

from app.firebase_push import normalize_firebase_private_key


def test_normalize_private_key_unescapes_and_strips_quotes():
    raw = '"-----BEGIN PRIVATE KEY-----\\nline\\n-----END PRIVATE KEY-----\\n"'
    out = normalize_firebase_private_key(raw)
    assert out.startswith("-----BEGIN PRIVATE KEY-----")
    assert "\nline\n" in out
    assert "\\n" not in out


def test_get_firebase_admin_reports_missing_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setenv("FIREBASE_CLIENT_EMAIL", "")
    monkeypatch.setenv("FIREBASE_PRIVATE_KEY", "")

    import importlib
    import sys

    for name in list(sys.modules):
        if name in ("app.firebase_push", "app.config"):
            del sys.modules[name]

    import app.config as config
    import app.firebase_push as fp

    importlib.reload(config)
    importlib.reload(fp)

    with pytest.raises(fp.FirebaseAdminConfigError) as exc:
        fp._service_account_dict()
    msg = str(exc.value)
    assert "FIREBASE_CLIENT_EMAIL" in msg
    assert "FIREBASE_PRIVATE_KEY" in msg
    assert "BEGIN PRIVATE KEY" not in msg
