"""Debts tab shown first from the per-user cache (amount-free copies only); precached assets serve ?v= URLs."""
import re

from app.config import STATIC_ASSET_VERSION
from tests.test_startup_v11 import A, SW, _sw

DEBTS = "/profile?tab=debts"
SLOTS = '<p>debts <span data-amt="debt-total-1"></span> {}</p>'


def test_debts_tab_cache_first_then_background_refresh():
    r = _sw([
        {"marker": A, "online": "ok", "body": SLOTS.format("v1"), "go": DEBTS},
        {"online": "ok", "body": SLOTS.format("v2"), "advance": 120_000, "go": DEBTS},
        {"online": "ok", "body": SLOTS.format("v3"), "go": DEBTS},
    ])
    assert "v1" in r[0]["body"] and r[0]["pages"] == ["https://app.test" + DEBTS]
    assert "v1" in r[1]["body"]
    assert r[1]["messages"][0]["type"] == "inventory-dashboard-refreshed"
    assert "v2" in r[2]["body"]


def test_debts_page_with_amounts_in_html_is_never_cached():
    r = _sw([{"marker": A, "online": "ok", "body": "<p>debt 12,000,000</p>", "go": DEBTS}])
    assert r[0]["pages"] == []


def test_edit_links_and_other_tabs_are_network_only():
    for path in ("/profile?tab=debts&edit=3", "/profile", "/profile?tab=settings"):
        r = _sw([{"marker": A, "online": "ok", "body": SLOTS.format("x"), "go": path}])
        assert r[0]["pages"] == [], path


def test_debts_offline_never_shows_the_dashboard_copy():
    r = _sw([
        {"marker": A, "online": "ok", "body": "<p>dash</p>", "offline_html": True, "go": "/dashboard"},
        {"online": False, "go": DEBTS},
    ])
    assert "dash" not in r[1]["body"] and "offline page" in r[1]["body"]


def test_debts_fresh_after_post_and_cleared_on_logout():
    r = _sw([
        {"marker": A, "online": "ok", "body": SLOTS.format("v1"), "go": DEBTS},
        {"online": "status", "status": 303, "go": "/logout", "opts": {"method": "POST", "mode": "same-origin"}},
    ])
    assert r[0]["pages"] and r[1]["pages"] == []
    r = _sw([
        {"marker": A, "online": "ok", "body": SLOTS.format("v1"), "go": DEBTS},
        {"online": "ok", "body": SLOTS.format("v2"), "go": DEBTS, "opts": {"cache": "reload"}},
    ])
    assert "v2" in r[1]["body"]


def test_this_builds_versioned_asset_comes_from_the_precache():
    r = _sw([
        {"static_put": "/static/app.js", "online": False, "go": "/static/app.js?v=test", "opts": {"mode": "no-cors"}},
        {"go": "/static/app.js?v=older", "opts": {"mode": "no-cors"}},
    ])
    assert r[0]["body"] == "precached /static/app.js"
    assert r[1].get("error") or r[1].get("body") != "precached /static/app.js"


def test_precache_bypasses_http_cache_and_covers_page_scripts():
    assert '{ cache: "reload" }' in SW
    precache = re.search(r"const PRECACHE = \[(.*?)\];", SW, re.S).group(1)
    for f in ("amounts.js", "debts-page.js", "spending-page.js", "confirm-dialog.js"):
        assert f'"/static/{f}"' in precache


def test_asset_version_bumped():
    assert STATIC_ASSET_VERSION >= "20261105b"
