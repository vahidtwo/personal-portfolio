"""Batch 1: the offline dashboard copy is never shown without a valid session."""
import json
import shutil
import subprocess

import pytest

from tests.test_holdings import _register, no_network  # noqa: F401
from tests.test_phase1_blockers import STATIC, SW_HARNESS


def _sw(steps, **extra):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    scenario = json.dumps({"maxAgeMs": 10_000, "steps": steps, **extra})
    out = subprocess.run(["node", str(SW_HARNESS), str(STATIC / "sw.js"), scenario],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_offline_copy_not_served_and_deleted_when_session_marker_gone():
    """Matin's case: cookie deleted, then offline -> private dashboard must not show."""
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": False, "go": "/dashboard"},                   # marker still there: offline copy ok
        {"online": False, "marker": False, "go": "/dashboard"},  # session cookie gone
        {"online": False, "marker": True, "go": "/dashboard"},   # copy was deleted, never comes back
    ])
    assert r[0]["pages"] == ["https://app.test/dashboard"]
    assert "dashboard private" in r[1]["body"]
    assert "dashboard private" not in r[2]["body"] and "offline page" in r[2]["body"]
    assert r[2]["pages"] == []
    assert "dashboard private" not in r[3]["body"]


def test_no_cookie_store_means_no_offline_private_copy():
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": False, "go": "/dashboard"},
    ], cookieStore=False)
    assert r[0]["pages"] == []  # never even stored
    assert "dashboard private" not in r[1]["body"]


def test_not_cached_without_marker():
    r = _sw([{"online": "ok", "offline_html": True, "go": "/dashboard"}], marker=False)
    assert r[0]["pages"] == []


def test_page_cache_name_bumped():
    # v11: per-user page caches (pages-v3-<marker id>); v2 copies are dropped by the version bump.
    assert 'VERSION + "-pages-v3-"' in (STATIC / "sw.js").read_text(encoding="utf-8")


def _marker(resp):
    return [v for k, v in resp.headers.multi_items() if k == "set-cookie" and v.startswith("inventory_signed_in=")]


def test_server_sets_and_clears_signed_in_marker(client, no_network):
    from app.config import SESSION_MAX_AGE_SECONDS

    _register(client)
    r = client.get("/dashboard")
    m = _marker(r)
    assert m and m[0].startswith("inventory_signed_in=1;") and f"Max-Age={SESSION_MAX_AGE_SECONDS}" in m[0]
    assert "HttpOnly" not in m[0] and "SameSite=Lax" in m[0]
    assert client.cookies.get("inventory_signed_in") == "1"
    assert __import__("re").fullmatch(r"u[A-Za-z0-9_-]{22}", client.cookies.get("inventory_page_key"))
    assert not _marker(client.get("/static/style.css"))  # static files untouched
    csrf = client.cookies.get("inventory_signed_in") and __import__("re").search(
        r'name="csrf" value="([^"]+)"', client.get("/profile").text).group(1)
    out = client.post("/logout", data={"csrf": csrf}, follow_redirects=False)
    assert out.status_code in (302, 303)
    m = _marker(out)
    assert m and "Max-Age=0" in m[0]
    assert client.cookies.get("inventory_signed_in") is None
    assert client.cookies.get("inventory_page_key") is None
