"""The chart has a start point right after the first save, from stored prices."""
from datetime import datetime, timedelta, timezone

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.amounts_helper import amounts_for
from tests.test_phase0_ui import _set_price


def _snapshots(username="alice"):
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User

    db = SessionLocal()
    user = db.query(User).filter(User.username == username).one()
    rows = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user.id).all()
    db.close()
    return rows


def _chart(client):
    html = client.get("/dashboard").text
    chart = amounts_for(client, "/dashboard")["chart"]
    return chart, html


def _save(client, **fields):
    data = {"csrf": _csrf(client, "/assets"), "next": "/assets", **fields}
    return client.post("/profile", data=data, headers={"Accept": "application/json"})


def test_first_save_with_stored_prices_gives_start_and_live_point(client, no_network):
    _set_price("gold", "7400000")
    _register(client)
    assert _snapshots() == []
    r = _save(client, gold_grams="2", cash_toman="1000000")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["snapshot_at"]
    snaps = _snapshots()
    assert len(snaps) == 1 and snaps[0].total_toman == 2 * 7_400_000 + 1_000_000
    chart, _html = _chart(client)
    assert len(chart["times"]) == 2
    total = chart["series"][0]
    assert total["key"] == "total" and total["data"] == [15_800_000, 15_800_000]


def test_first_save_keeps_changes_as_dash(client, no_network):
    _set_price("gold", "7400000")
    _register(client)
    _save(client, gold_grams="1")
    from app.dashboard import net_worth_changes
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot
    from app.portfolio import build_portfolio, load_prices

    db = SessionLocal()
    from app.models import User
    user = db.query(User).filter(User.username == "alice").one()
    view = build_portfolio(user, load_prices(db))
    snaps = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user.id).all()
    changes = net_worth_changes(snaps, view, 0, datetime.now(timezone.utc))
    db.close()
    assert changes["24h"]["delta"] is None and changes["7d"]["delta"] is None
    assert changes["has_history"] is False
    chart, _html = _chart(client)
    assert chart["has_prior_point"] is False
    assert chart["weekly"]["has_prior_point"] is False


def test_zero_history_keeps_earliest_of_today():
    from app.dashboard import chart_snapshots

    class S:
        def __init__(self, at):
            self.taken_at = at

    now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    a, b = S(now - timedelta(minutes=30)), S(now - timedelta(minutes=5))
    assert chart_snapshots([a, b], now, "day", keep_first_now=True) == [a]
    assert chart_snapshots([a, b], now, "week", keep_first_now=True) == [a]
    assert chart_snapshots([], now, "day", keep_first_now=True) == []
    assert chart_snapshots([a, b], now, "day") == []


def test_existing_history_still_drops_today():
    from app.dashboard import chart_snapshots

    class S:
        def __init__(self, at):
            self.taken_at = at

    now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    yesterday, today = S(now - timedelta(days=1)), S(now - timedelta(minutes=5))
    assert chart_snapshots([yesterday, today], now, "day", keep_first_now=True) == [yesterday]


def test_no_prices_no_500_and_specific_empty_line(client, no_network):
    from app.dashboard import CHART_NO_PRICES_FA

    _register(client)
    r = _save(client, gold_grams="1")
    assert r.status_code == 200 and r.json()["snapshot_at"] is None
    assert _snapshots() == []
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert CHART_NO_PRICES_FA == "قیمت بازار هنوز دریافت نشده. نمودار با رسیدن اولین قیمت‌ها پر می‌شود."
    assert 'data-empty="no-prices"' in page.text and CHART_NO_PRICES_FA in page.text


def test_no_row_for_user_without_assets(client, no_network):
    _set_price("gold", "7400000")
    _register(client)
    r = _save(client, gold_grams="0")
    assert r.status_code == 200 and r.json()["snapshot_at"] is None
    assert _snapshots() == []
    chart, html = _chart(client)
    assert 'data-empty="no-prices"' not in html


def test_form_post_redirect_also_stores_snapshot(client, no_network):
    _set_price("gold", "7400000")
    _register(client)
    r = client.post("/profile", data={"csrf": _csrf(client, "/assets"), "gold_grams": "1"}, follow_redirects=False)
    assert r.status_code == 303
    assert len(_snapshots()) == 1


def test_first_save_chart_foot_uses_dash_like_chips():
    """With only today's start point, the «این ماه» stat is «—», not «۰٪» or a bare «٪»."""
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent / "app/static/dashboard.js").read_text(encoding="utf-8")
    assert "if (!src().has_prior_point || first === 0)" in js
    block = js.split("function updateFoot(view) {", 1)[1].split("function renderChart()", 1)[0]
    assert 'changeEl.textContent = "—"' in block
    # The zero-change «۰٪» label is only reached when a prior day exists.
    assert block.index("!src().has_prior_point") < block.index('changeEl.textContent = "۰٪"')


def test_prior_day_snapshot_sets_has_prior_point(client, no_network):
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User

    _set_price("gold", "7400000")
    _register(client)
    _save(client, gold_grams="1")
    db = SessionLocal()
    snap = db.query(PortfolioSnapshot).join(User).filter(User.username == "alice").one()
    snap.taken_at = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    db.commit()
    db.close()
    chart, _html = _chart(client)
    assert chart["has_prior_point"] is True
    assert chart["weekly"]["has_prior_point"] is True
