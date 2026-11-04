"""The price refresh button (a form POST that redirects to /dashboard) and a reload must show the fresh page,
not the service worker's cached copy of the dashboard."""
from pathlib import Path

from tests.test_offline_privacy import _sw

ROOT = Path(__file__).resolve().parents[1]


def _old_then_new():
    return [
        {"online": "ok", "body": "<p>old prices</p>", "go": "/dashboard"},
        {"advance": 120_000, "online": "ok", "body": "<p>new prices</p>"},
    ]


def test_dashboard_after_refresh_post_comes_from_network():
    r = _sw(_old_then_new() + [
        {"go": "/dashboard/refresh-prices", "opts": {"method": "POST"}},
        {"go": "/dashboard"},
    ], maxAgeMs=10_000_000)
    assert r[1]["handled"] is False  # the POST itself goes to the server untouched
    assert "new prices" in r[2]["body"]
    assert r[2]["messages"] == []  # no background copy that would eat the flash message


def test_reload_of_dashboard_comes_from_network():
    for mode in ("reload", "no-cache"):
        r = _sw(_old_then_new() + [{"go": "/dashboard", "opts": {"cache": mode}}], maxAgeMs=10_000_000)
        assert "new prices" in r[1]["body"], mode


def test_plain_open_still_shows_cached_copy_first():
    r = _sw(_old_then_new() + [{"go": "/dashboard"}], maxAgeMs=10_000_000)
    assert "old prices" in r[1]["body"]
    assert r[1]["messages"][0]["type"] == "inventory-dashboard-refreshed"


def test_form_post_flag_is_used_once():
    r = _sw(_old_then_new() + [
        {"go": "/dashboard/refresh-prices", "opts": {"method": "POST"}},
        {"go": "/dashboard"},
        {"go": "/dashboard"},
    ], maxAgeMs=10_000_000)
    assert "new prices" in r[2]["body"]
    assert r[3]["messages"] and r[3]["messages"][0]["type"] == "inventory-dashboard-refreshed"


def test_offline_after_post_still_falls_back_to_cached_copy():
    r = _sw(_old_then_new() + [
        {"online": False, "go": "/dashboard/refresh-prices", "opts": {"method": "POST"}},
        {"go": "/dashboard"},
    ], maxAgeMs=10_000_000)
    assert "old prices" in r[2]["body"]


def test_static_version_bumped_for_new_worker():
    from app.config import STATIC_ASSET_VERSION
    assert STATIC_ASSET_VERSION >= "20261104d"
