"""web-v11-prep must work with the installed v10 app (no dependency on v11 native code).

What v10 native reads from the web (android/ on main, unchanged by this PR):
- SMS sender: ServerAddress.hasSignedInSession needs inventory_signed_in == "1" plus inventory_session.
- Offline fallback (R2/R2c): <meta name="x-offline" content="1"> in /offline.html.
- It loads /dashboard over https; the SW and its caches are pure web and need nothing native.
"""
import re
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
KT = (ROOT / "android/app/src/main/java/app/myinventory/ServerAddress.kt").read_text(encoding="utf-8")


def _native_has_signed_in_session(cookies):
    """Python copy of ServerAddress.hasSignedInSession (v10/v11 native)."""
    return cookies.get("inventory_signed_in") == "1" and bool(cookies.get("inventory_session"))


def test_native_contract_unchanged_in_source():
    assert 'SIGNED_IN_COOKIE = "inventory_signed_in"' in KT and 'SESSION_COOKIE = "inventory_session"' in KT
    assert 'pairs[SIGNED_IN_COOKIE] == "1"' in KT


def test_v10_sms_sender_still_sees_signed_in_session(client, no_network):
    _register(client)
    client.get("/dashboard")
    assert _native_has_signed_in_session(client.cookies)
    assert client.cookies.get("inventory_page_key", "").startswith("u")  # the new key is a separate cookie


def test_offline_marker_page_unchanged():
    html = (ROOT / "app/static/offline.html").read_text(encoding="utf-8")
    assert re.search(r'<meta name="x-offline" content="1"', html)
