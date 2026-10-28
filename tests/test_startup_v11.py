"""v11 startup: per-user cache-first dashboard, no navigation preload, masks before first paint."""
import json
import re
import shutil
import subprocess

import pytest

from tests.test_holdings import _register, no_network  # noqa: F401
from tests.test_phase1_blockers import STATIC, SW_HARNESS
from tests.test_salary_privacy import SALARY_RAW, _csrf, _setup

A = "uAAAAAAAAAAAAAAAAAAAAAA"
B = "uBBBBBBBBBBBBBBBBBBBBBB"
SW = (STATIC / "sw.js").read_text(encoding="utf-8")


def _sw(steps, **extra):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    scenario = json.dumps({"maxAgeMs": 10 ** 9, "steps": steps, **extra})
    out = subprocess.run(["node", str(SW_HARNESS), str(STATIC / "sw.js"), scenario],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_dashboard_cache_first_then_background_refresh():
    r = _sw([
        {"marker": A, "online": "ok", "body": "<p>v1 A</p>", "go": "/dashboard"},
        {"online": "ok", "body": "<p>v2 A</p>", "advance": 120_000, "go": "/dashboard"},
        {"online": "ok", "body": "<p>v3 A</p>", "go": "/dashboard"},
    ])
    assert "v1 A" in r[0]["body"] and r[0]["stores"] == ["inventory-vtest-pages-v3-" + A]
    assert "v1 A" in r[1]["body"]  # shown first from cache
    assert r[1]["messages"] == [{"to": "client-/dashboard", "type": "inventory-dashboard-refreshed", "age": 120_000}]
    assert "v2 A" in r[2]["body"]  # the background copy is what the next open shows


def test_cache_is_per_user_and_account_switch_drops_the_other_user():
    r = _sw([
        {"marker": A, "online": "ok", "body": "<p>secret A</p>", "go": "/dashboard"},
        {"marker": B, "online": False, "offline_html": True, "go": "/dashboard"},
        {"marker": B, "online": "ok", "body": "<p>secret B</p>", "go": "/dashboard"},
        {"marker": A, "online": False, "go": "/dashboard"},
    ])
    assert "secret A" not in r[1]["body"] and "offline page" in r[1]["body"]
    assert r[1]["stores"] == ["inventory-vtest-pages-v3-" + B] or r[1]["pages"] == []
    assert not any(A in s for s in r[1]["stores"])  # A's copy deleted on switch
    assert "secret B" in r[2]["body"]
    assert "secret B" not in r[3]["body"] and "secret A" not in r[3]["body"]


def test_not_cached_when_signed_out_or_old_v10_marker():
    for marker in (False, "1"):
        r = _sw([{"marker": marker, "online": "ok", "go": "/dashboard"}])
        assert r[0]["pages"] == [] and r[0]["stores"] == []


def test_logout_and_session_end_clear_the_cache():
    r = _sw([
        {"marker": A, "online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "status", "status": 303, "go": "/logout", "opts": {"method": "POST", "mode": "same-origin"}},
    ])
    assert r[0]["pages"] and r[1]["pages"] == []
    r = _sw([
        {"marker": A, "online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "status", "status": 401, "go": "/api/holdings", "opts": {"mode": "cors"}},
    ])
    assert r[1]["pages"] == []
    # server ended the session while the cached copy was on screen: copy deleted, page sent to /login
    r = _sw([
        {"marker": A, "online": "ok", "go": "/dashboard"},
        {"online": "redirect-login", "go": "/dashboard"},
    ])
    assert r[1]["pages"] == [] and r[1]["messages"][0]["type"] == "inventory-session-ended"


def test_no_navigation_preload():
    """#44 NO-GO: preload made v10's WebView fire a main-frame error on an offline cold start."""
    r = _sw([
        {"activate": True},
        {"marker": A, "online": "ok", "body": "<p>from fetch</p>", "go": "/dashboard"},
        {"marker": False, "online": "ok", "go": "/"},
    ])
    assert r[-1] == {"preloadCalls": 0}
    for word in ("navigationPreload", "preloadResponse", "Service-Worker-Navigation-Preload"):
        assert word not in SW


def test_pwa_soft_refresh_is_guarded():
    js = (STATIC / "pwa.js").read_text(encoding="utf-8")
    block = js[js.index('"inventory-dashboard-refreshed"'):]
    assert "touched" in block and "data.age > 60000" in block and "inventory-soft-refresh" in block
    assert 'window.location.replace("/login")' in js


def test_server_marker_is_per_user_and_not_the_user_id(client, no_network):
    _register(client, "alice")
    a = client.cookies.get("inventory_page_key")
    client.cookies.clear()
    _register(client, "bob")
    b = client.cookies.get("inventory_page_key")
    assert re.fullmatch(r"u[A-Za-z0-9_-]{22}", a) and re.fullmatch(r"u[A-Za-z0-9_-]{22}", b) and a != b
    from app.session_marker import marker_value
    assert marker_value("k", 1) == marker_value("k", 1) != marker_value("k", 2) and "1" != marker_value("k", 1)[1:]


def test_hide_and_salary_masks_are_in_the_html_before_first_paint(client, no_network):
    _setup(client)
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})  # not the empty-user welcome card
    html = client.get("/dashboard").text
    head = html[: html.index("</head>")]
    # hide-amounts is decided by an inline head script (no defer/async) before <body> exists
    assert 'localStorage.getItem("privacy-portfolio") !== "1"' in head and "dataset.showPortfolio" in head
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert 'html[data-show-portfolio="1"] [data-mask="portfolio"]' in css  # amounts masked unless shown
    # the salary is never in the page (so never in a cached copy either): mask only
    fields = re.findall(r'data-salary-field="(\w+)"[^>]*>([^<]*)<', html)
    assert fields and all(v.strip() in ("••••••", "") for _, v in fields), fields
    assert SALARY_RAW not in html
