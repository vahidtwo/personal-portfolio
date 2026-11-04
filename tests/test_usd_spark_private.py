"""The dashboard HTML carries no user amount, the 7-day USD line included: it comes from /api/amounts."""
import json
import re
from datetime import timedelta
from decimal import Decimal

from app.formatting import format_number, format_toman
from app.models import utcnow
from tests.amounts_helper import amounts_for, with_amounts
from tests.test_holdings import _register, no_network  # noqa: F401

USD_PRICE = 100_000
CASH = 731_900_000  # live total; 7,319 USD at the fake dollar price
HISTORY = (612_300_000, 655_700_000, 690_100_000)  # 6,123 / 6,557 / 6,901 USD


def _seed():
    from app.db import SessionLocal
    from app.models import MarketPrice, PortfolioSnapshot, User
    db = SessionLocal()
    now = utcnow()
    db.merge(MarketPrice(symbol="usd", price_toman=Decimal(USD_PRICE), fetched_at=now))
    u = db.query(User).one()
    u.cash_toman = Decimal(CASH)
    for i, total in enumerate(HISTORY):
        db.add(PortfolioSnapshot(user_id=u.id, taken_at=now - timedelta(days=len(HISTORY) - i), total_toman=Decimal(total),
                                 breakdown_json=json.dumps({"unit_price": {"usd": str(USD_PRICE)}})))
    db.commit()
    db.close()


def _usd(total):
    return format_number(Decimal(round(total / USD_PRICE)), 0)


def test_dashboard_html_has_no_user_amount_and_no_usd_line(client, no_network):
    _register(client)
    _seed()
    html = client.get("/dashboard").text
    for v in (CASH, *HISTORY):
        assert format_toman(Decimal(v)) not in html and str(v) not in html, v
        assert _usd(v) not in html, _usd(v)
    assert "معادل دلاری دارایی در ۷ روز گذشته" not in html
    svg = re.search(r"<svg [^>]*data-usd-spark[^>]*>.*?</svg>", html, re.S).group(0)
    assert 'd=""' in svg and "cx=" not in svg and "aria-label" not in svg and " hidden" in svg
    assert not re.search(r'class="mc (?:up|down|flat)"[^>]*viewBox="0 0 64 20"', html)


def test_usd_line_comes_from_the_amounts_api(client, no_network):
    _register(client)
    _seed()
    sp = amounts_for(client, "/dashboard")["usd-spark"]
    assert sp["kind"] == "up" and sp["path"].startswith("M ")
    assert sp["label"].startswith("معادل دلاری دارایی در ۷ روز گذشته: از " + _usd(HISTORY[0]))
    assert _usd(CASH) in sp["label"]
    assert _usd(CASH) in with_amounts(client, "/dashboard")


def test_dashboard_js_draws_the_usd_line_after_fill():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "app/static/dashboard.js").read_text(encoding="utf-8")
    block = js[js.index("function drawUsdSpark"):]
    assert 'addEventListener("amounts:filled", drawUsdSpark)' in js
    for part in ('"aria-label"', '"d"', '"cx"', "svg.hidden = false"):
        assert part in block
