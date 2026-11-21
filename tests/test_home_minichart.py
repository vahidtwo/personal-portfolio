import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.dashboard import build_week_asset_trends, sparkline, sparkline_path
from app.models import utcnow
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401


def _view(**prices):
    rows = [SimpleNamespace(key=k, unit_price=(Decimal(v) if v is not None else None)) for k, v in prices.items()]
    return SimpleNamespace(rows=rows)


def _snap(at, **unit):
    return SimpleNamespace(taken_at=at, breakdown_json=json.dumps({"unit_price": {k: str(v) for k, v in unit.items()}}))


# Midday in Tehran: the 2-hour-older snapshot of each day stays on the same Tehran day.
FIXED_NOW = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)


def test_series_last_snapshot_per_day_plus_live_old_to_new():
    now = FIXED_NOW
    snaps = [_snap(now - timedelta(days=d, hours=h), gold=100 + 10 * (8 - d) + h) for d in range(1, 10) for h in (0, 2)]
    trends = build_week_asset_trends(snaps, _view(gold="500", cash="1"), now)
    assert len(trends["gold"]) <= 8 and trends["gold"][-1] == 500.0
    assert trends["gold"][:-1] == sorted(trends["gold"][:-1])  # oldest first
    assert trends["cash"] == []


def test_series_empty_and_sparse():
    now = utcnow()
    assert build_week_asset_trends([], _view(gold="5"), now) == {"gold": [5.0]}
    assert build_week_asset_trends([_snap(now - timedelta(days=2), btc=1)], _view(gold="5"), now) == {"gold": [5.0]}
    assert build_week_asset_trends([], _view(gold=None), now) == {"gold": []}
    assert sparkline_path([]) == "" and sparkline_path([5.0]) == ""
    assert sparkline("gold", "طلا", [5.0], {"kind": "none", "label": "—"}, 72) is None


def test_flat_line_straight_and_direction_follows_chip():
    assert sparkline_path([3.0, 3.0, 3.0]) == "M 2,12.0 L 70,12.0"
    up = sparkline("gold", "طلا", [1.0, 2.0], {"kind": "up", "label": "▲ ۱۰۰٪"}, 72)
    assert up["kind"] == "up" and up["label"] == "قیمت واحد طلا در ۷ روز گذشته: بالا رفت، ۱۰۰٪"
    down = sparkline("btc", "بیت‌کوین", [2.0, 1.0], {"kind": "down", "label": "▼ ۵۰٪"}, 64)
    assert down["kind"] == "down" and down["label"].endswith("پایین آمد، ۵۰٪") and down["width"] == 64
    flat = sparkline("usd", "دلار", [1.0, 1.0], {"kind": "flat", "label": "بدون تغییر"}, 72)
    assert flat["label"].endswith(": بدون تغییر")


def test_home_renders_charts_only_for_priced_rows(client, no_network):
    from app.db import SessionLocal
    from app.models import MarketPrice, PortfolioSnapshot, User
    _register(client)
    db = SessionLocal()
    now = utcnow()
    for sym, v in (("gold", "7000000"), ("btc", "9000000000")):
        db.merge(MarketPrice(symbol=sym, price_toman=Decimal(v), fetched_at=now))
    u = db.query(User).one()
    u.gold_grams, u.btc, u.cash_toman = Decimal("2"), Decimal("0.01"), Decimal("1000")
    for d in range(7, 0, -1):
        db.add(PortfolioSnapshot(user_id=u.id, taken_at=now - timedelta(days=d), total_toman=Decimal("1"),
                                 breakdown_json=json.dumps({"unit_price": {"gold": str(6000000 + d), "btc": "9000000000"}})))
    db.commit(); db.close()
    html = client.get("/dashboard").text
    assert html.count('<svg class="mc up"') == 2  # gold: card + desktop table
    assert 'قیمت واحد طلا ۱۸ عیار در ۷ روز گذشته: بالا رفت، ' in html or 'در ۷ روز گذشته: بالا رفت، ' in html
    assert 'class="mc flat"' in html  # btc unchanged
    assert html.count('class="mc ') == 4  # no chart for cash
    assert 'focusable="false"' in html and "tabindex" not in html.split('class="mc ')[1][:400]


def test_minichart_css_contract():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app/static/style.css").read_text(encoding="utf-8")
    assert ".acard .r2 .mc{width:72px;height:24px}" in css and "@media (max-width:339px){.acard .r2 .mc{width:56px}}" in css
    assert "--mc-up:#08735a;--mc-down:#b42318;--mc-flat:#5b6475" in css


def _tsnap(at, total, usd):
    bd = {"unit_price": {"usd": str(usd)}} if usd is not None else {}
    return SimpleNamespace(taken_at=at, total_toman=Decimal(total), breakdown_json=json.dumps(bd))


def test_usd_series_daily_skips_missing_and_ends_live():
    from app.dashboard import week_usd_series
    now = utcnow()
    snaps = [_tsnap(now - timedelta(days=3), 2000, 100), _tsnap(now - timedelta(days=2), 9999, None),
             _tsnap(now - timedelta(days=1), 3000, 100)]
    assert week_usd_series(snaps, Decimal("100"), Decimal("4000"), now) == [20.0, 30.0, 40.0]
    assert week_usd_series([], Decimal("100"), Decimal("4000"), now) == [40.0]
    assert week_usd_series(snaps, None, Decimal("4000"), now) == [20.0, 30.0]


def test_usd_sparkline_label_and_direction():
    from app.dashboard import usd_sparkline
    assert usd_sparkline([40.0]) is None
    down = usd_sparkline([15954.0, 13806.0])
    assert down["kind"] == "down" and down["label"] == "معادل دلاری دارایی در ۷ روز گذشته: از ۱۵٬۹۵۴ به ۱۳٬۸۰۶ دلار، پایین ۱۳٫۵٪"
    assert usd_sparkline([100.0, 100.04])["label"].endswith("، بدون تغییر")
    assert usd_sparkline([100.0, 110.0])["kind"] == "up"


def test_usd_tile_chart_hidden_while_masked():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app/static/style.css").read_text(encoding="utf-8")
    assert ".stat.stat-usd .mc{width:64px;height:20px;display:none}" in css
    assert 'html[data-show-portfolio="1"] .stat.stat-usd .mc{display:block}' in css
