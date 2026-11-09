"""Native home «به‌روزرسانی»: it must ask the server to fetch market prices, not only re-read /api/home."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_home_v2 import _forget_fetch_state, _price_at
from tests.test_native_api import _csrf, _post, _signup

ROOT = Path(__file__).resolve().parents[1]
KT = ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "myinventory"


@pytest.fixture()
def fake_chande(monkeypatch):
    import app.jobs as jobs

    calls = []

    async def fetched():
        calls.append(1)
        return []

    def upsert(_items):
        _price_at(datetime.now(timezone.utc), price="2000000")

    monkeypatch.setattr(jobs, "fetch_chande_prices", fetched)
    monkeypatch.setattr(jobs, "upsert_prices", upsert)
    _forget_fetch_state()
    return calls


def _refresh(client, csrf=None):
    return client.post("/api/home/refresh-prices", json={},
                       headers={"X-CSRF-Token": _csrf(client) if csrf is None else csrf})


def test_refresh_fetches_prices_and_home_shows_them(client, fake_chande):
    _signup(client)
    _price_at(datetime.now(timezone.utc) - timedelta(hours=3))
    before = client.get("/api/home").json()["price"]
    assert before["state"] == "stale" and before["wait_sec"] == 0 and before["wait_label"] == ""
    r = _refresh(client)
    assert r.status_code == 200 and r.json()["result"] == "ok" and fake_chande == [1]
    assert r.headers["Cache-Control"] == "no-store"
    after = client.get("/api/home").json()["price"]
    assert after["state"] == "fresh" and after["wait_sec"] > 0 and after["wait_label"].startswith("دوباره تا ")


def test_refresh_respects_the_cooldown(client, fake_chande):
    _signup(client)
    _price_at(datetime.now(timezone.utc) - timedelta(minutes=1))
    r = _refresh(client)
    assert r.status_code == 429 and r.json()["result"] == "wait" and int(r.headers["Retry-After"]) > 0
    assert "دقیقه" in r.json()["message"] and fake_chande == []


def test_refresh_failure_is_reported_and_recorded(client, monkeypatch):
    import app.jobs as jobs
    from app import price_fetch_state

    async def boom():
        raise RuntimeError("chande down")

    monkeypatch.setattr(jobs, "fetch_chande_prices", boom)
    _forget_fetch_state()
    _signup(client)
    r = _refresh(client)
    assert r.status_code == 200 and r.json()["result"] == "error"
    assert price_fetch_state.last()[0] is False
    assert client.get("/api/home").json()["price"]["state"] == "error"


def test_refresh_needs_csrf_and_a_session(client, fake_chande):
    assert _refresh(client).status_code == 401
    _signup(client)
    assert _refresh(client, csrf="forged").status_code == 400
    assert client.post("/api/home/refresh-prices", json={}).status_code == 400
    assert fake_chande == []


def test_native_button_posts_the_refresh_not_only_a_reread():
    home = (KT / "HomeActivity.kt").read_text(encoding="utf-8")
    block = home[home.index("// price line"):home.index("// tiles")]
    assert "setOnClickListener { refreshPrices(this) }" in block
    assert "fetchHome()" not in block
    fn = home[home.index("private fun refreshPrices"):home.index("private fun signOutLocal")]
    assert "NativeSession.post(PriceRefresh.PATH" in fn and "PriceRefresh.TIMEOUT_MS" in fn and "fetchHome()" in fn
    pr = (KT / "PriceRefresh.kt").read_text(encoding="utf-8")
    assert 'PATH = "/api/home/refresh-prices"' in pr
    assert int(re.search(r"TIMEOUT_MS = ([\d_]+)", pr).group(1).replace("_", "")) >= 60_000
