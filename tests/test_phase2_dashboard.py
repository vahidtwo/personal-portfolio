"""Phase 2 dashboard: net-worth change from price moves only, formatting, layout contracts."""
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import jdatetime

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.test_phase0_ui import _set_price

TEHRAN = ZoneInfo("Asia/Tehran")
ROOT = Path(__file__).resolve().parent.parent
# 12:00 Tehran = 08:30 UTC
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=TEHRAN).astimezone(timezone.utc)


class _Snap:
    def __init__(self, taken_at, prices=None, breakdown=None):
        self.taken_at = taken_at
        bd = dict(breakdown or {})
        if prices is not None:
            bd["unit_price"] = {k: str(v) for k, v in prices.items()}
        self.breakdown_json = json.dumps(bd)


def _view(**holdings):
    """PortfolioView from {key: (quantity, unit_price)}; cash is (amount, None)."""
    from app.portfolio import ASSET_META, AssetRow, PortfolioView

    rows, total = [], Decimal("0")
    for key, (qty, price) in holdings.items():
        qty = Decimal(str(qty))
        value = qty if price is None else (qty * Decimal(str(price))).quantize(Decimal("1"))
        meta = ASSET_META[key]
        rows.append(AssetRow(key, meta["name_fa"], meta["name_en"], qty, meta["unit_fa"], meta["unit_en"],
                             None if price is None else Decimal(str(price)), value, price is None))
        total += value
    return PortfolioView(rows=rows, total_toman=total, prices_fetched_at=None, missing_prices=[])


def _naive_utc(local_tehran: datetime) -> datetime:
    """What SQLite gives back: naive UTC."""
    return local_tehran.astimezone(timezone.utc).replace(tzinfo=None)


# --- change calculation -------------------------------------------------------------------

def test_reference_window_is_tehran_wall_clock_and_bounded(client):
    from app.dashboard import change_reference_time, reference_snapshot

    assert change_reference_time(NOW, timedelta(hours=24)) == datetime(2026, 10, 16, 12, 0, tzinfo=TEHRAN)
    assert change_reference_time(NOW, timedelta(days=7)) == datetime(2026, 10, 10, 12, 0, tzinfo=TEHRAN)
    exact = _Snap(_naive_utc(datetime(2026, 10, 16, 12, 0, tzinfo=TEHRAN)), {"btc": 1})
    too_new = _Snap(_naive_utc(datetime(2026, 10, 16, 12, 1, tzinfo=TEHRAN)), {"btc": 2})
    older = _Snap(_naive_utc(datetime(2026, 10, 16, 11, 0, tzinfo=TEHRAN)), {"btc": 3})
    picked = reference_snapshot([older, too_new, exact], NOW, timedelta(hours=24), timedelta(hours=3))
    assert picked is exact  # newest snapshot at or before 24h ago (Tehran), never a newer one
    stale = _Snap(_naive_utc(datetime(2026, 10, 16, 8, 59, tzinfo=TEHRAN)), {"btc": 4})
    assert reference_snapshot([stale, too_new], NOW, timedelta(hours=24), timedelta(hours=3)) is None


def test_change_counts_price_moves_only(client):
    from app.dashboard import net_worth_changes

    view = _view(btc=(2, 110), cash=(50, None))  # assets 270
    day = _Snap(NOW - timedelta(hours=24), {"btc": 100})
    week = _Snap(NOW - timedelta(days=7), {"btc": 120})
    ch = net_worth_changes([day, week], view, Decimal("20"), NOW)
    # 24h: 2 × (110 − 100) = +20 on a past net worth of (200 + 50) − 20 = 230
    assert ch["24h"]["delta"] == Decimal("20")
    assert ch["24h"]["label"] == "▲ ۸٫۷٪" and ch["24h"]["kind"] == "up"
    # 7d: 2 × (110 − 120) = −20 on (240 + 50) − 20 = 270
    assert ch["7d"]["delta"] == Decimal("-20")
    assert ch["7d"]["label"] == "▼ ۷٫۴۱٪" and ch["7d"]["kind"] == "down"
    assert ch["note"] == ("۲۰", "تومان بیشتر از دیروز")


def test_adding_or_removing_assets_does_not_move_the_chips(client):
    from app.dashboard import net_worth_changes

    # Yesterday: 1 BTC (snapshot total 100). Today: 3 BTC + a new gold holding, same prices.
    snap = _Snap(NOW - timedelta(hours=24), {"btc": 100, "gold": 50}, {"total": "100", "btc": "100"})
    view = _view(btc=(3, 100), gold=(4, 50), cash=(1000, None))
    ch = net_worth_changes([snap], view, Decimal("0"), NOW)
    assert ch["24h"]["delta"] == 0 and ch["24h"]["label"] == "۰٪" and ch["24h"]["kind"] == "flat"
    # An asset the old snapshot has no price for counts as "no move", never as a gain.
    view2 = _view(btc=(3, 100), eth=(1, 999999))
    assert net_worth_changes([snap], view2, Decimal("0"), NOW)["24h"]["delta"] == 0
    # Removing everything but cash: still no change.
    assert net_worth_changes([snap], _view(cash=(5, None)), Decimal("0"), NOW)["24h"]["delta"] == 0


def test_no_price_history_shows_dash(client):
    from app.dashboard import net_worth_changes

    view = _view(btc=(1, 100))
    ch = net_worth_changes([], view, Decimal("0"), NOW)
    assert [w["label"] for w in ch["windows"]] == ["—", "—"]
    assert ch["note"] is None and ch["has_history"] is False
    # A snapshot only 2 hours old is not "24h ago" either.
    assert net_worth_changes([_Snap(NOW - timedelta(hours=2), {"btc": 1})], view, Decimal("0"), NOW)["24h"]["label"] == "—"
    # Old-format snapshot without stored unit prices: no history.
    old = _Snap(NOW - timedelta(hours=24), None, {"total": "90", "btc": "90"})
    assert net_worth_changes([old], view, Decimal("0"), NOW)["24h"]["label"] == "—"


def test_asset_week_chip(client):
    from app.dashboard import asset_week_change

    view = _view(btc=(1, 110), cash=(5, None), gold=(1, 50))
    rows = {r.key: r for r in view.rows}
    assert asset_week_change(rows["btc"], {"btc": Decimal("100")})[0] == {"kind": "up", "label": "▲ ۱۰٪"}
    assert asset_week_change(rows["gold"], {"gold": Decimal("50")})[0]["label"] == "بدون تغییر"
    assert asset_week_change(rows["btc"], None)[0]["label"] == "—"
    assert asset_week_change(rows["cash"], None)[0]["label"] == "بدون تغییر"


def test_chart_history_tiers_keep_real_snapshots(client):
    from app.dashboard import chart_snapshots

    snaps = [_Snap(NOW - timedelta(hours=h)) for h in range(24 * 365 * 3, -1, -1)]  # hourly, 3 years
    kept = chart_snapshots(snaps, NOW)
    assert all(k in snaps for k in kept)  # real snapshots, stored values untouched
    assert [k.taken_at for k in kept] == sorted(k.taken_at for k in kept)
    age = lambda s: NOW - s.taken_at  # noqa: E731
    last48 = [s for s in snaps if age(s) <= timedelta(hours=48)]
    assert [k for k in kept if age(k) <= timedelta(hours=48)] == last48  # every hourly point
    six = [k for k in kept if timedelta(hours=48) < age(k) < timedelta(days=7)]
    buckets = {(k.taken_at.astimezone(TEHRAN).date(), k.taken_at.astimezone(TEHRAN).hour // 6) for k in six}
    assert len(six) == len(buckets) and 18 <= len(six) <= 21  # one per 6 hours
    days = [k for k in kept if timedelta(days=7) <= age(k) < timedelta(days=366)]
    assert len(days) == len({k.taken_at.astimezone(TEHRAN).date() for k in days})  # one per Tehran day
    weeks = [k for k in kept if age(k) >= timedelta(days=366)]
    assert len(weeks) == len({k.taken_at.astimezone(TEHRAN).date().isocalendar()[:2] for k in weeks})
    assert len(kept) < 600


def test_chart_payload_small_for_three_years_hourly(client):
    """~3 years of hourly snapshots, every asset held: the embedded chart JSON stays < 200 KB."""
    from app.dashboard import build_chart_data
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User
    from app.portfolio import ASSET_ORDER

    _register(client)
    db = SessionLocal()
    user = db.query(User).filter(User.username == "alice").one()
    now = datetime.now(timezone.utc)
    keys = list(ASSET_ORDER) + [f"extra_{i}" for i in range(40 - len(ASSET_ORDER))]  # 40 keys per breakdown
    rows = []
    for h in range(24 * 365 * 3, 0, -1):
        bd = {k: str(123_456_789 + h * (i + 1)) for i, k in enumerate(keys)}
        bd["total"] = str(9_876_543_210 + h)
        rows.append({"user_id": user.id, "taken_at": (now - timedelta(hours=h)).replace(tzinfo=None),
                     "total_toman": Decimal(bd["total"]), "breakdown_json": json.dumps(bd)})
    db.execute(PortfolioSnapshot.__table__.insert(), rows)
    db.commit()
    view = _view(**{k: (1, 1000) if k not in ("cash", "car") else (1000, None) for k in ASSET_ORDER if k != "car"})
    data = build_chart_data(db, user.id, view, now)
    db.close()
    size = len(json.dumps(data, ensure_ascii=False).encode())
    assert size < 200 * 1024, size
    assert len(data["series"]) == len(view.rows) + 1
    # Values are the stored ones: the newest snapshot's total is passed through as is.
    assert data["series"][0]["data"][-2] == 9_876_543_211


def test_next_instalment_due_chip(client):
    from app.dashboard import next_instalment
    from app.models import Debt

    today = jdatetime.date(1405, 7, 25)
    d1 = Debt(title="وام خودرو", monthly_toman=Decimal("4500000"), months_left=3, due_year=1405, due_month=1, due_day=5)
    d2 = Debt(title="کارت", monthly_toman=Decimal("100"), months_left=3, due_year=1405, due_month=1, due_day=26)
    n = next_instalment([d1, d2], today)
    assert n["chip"] == "فردا" and n["title"] == "کارت" and n["amount_label"] == "۱۰۰"
    n = next_instalment([d1], today)
    assert n["chip"] == "۱۰ روز دیگر" and n["date_label"] == "۵ آبان"
    assert next_instalment([], today) is None


# --- formatting ---------------------------------------------------------------------------

def test_usd_two_decimals_and_millions(client):
    from app.dashboard import big_toman
    from app.formatting import format_millions, format_usd

    assert format_usd(Decimal("9102.3"), fixed=True) == "۹٬۱۰۲٫۳۰"
    assert format_usd(Decimal("200"), fixed=True) == "۲۰۰٫۰۰"
    assert format_usd(Decimal("0.005"), fixed=True) == "۰٫۰۱"
    assert format_usd(Decimal("3249.40")) == "۳٬۲۴۹٫۴"  # default unchanged
    assert format_millions(Decimal("89800000")) == ("۸۹٫۸", False)
    assert format_millions(Decimal("1113000001"), 0) == ("۱٬۱۱۳", True)
    assert big_toman(Decimal("1113000001")) == {"label": "۱٬۱۱۳", "unit": "میلیون تومان", "approx": True}
    assert big_toman(Decimal("450000")) == {"label": "۴۵۰٬۰۰۰", "unit": "تومان", "approx": False}


def test_chart_axis_uses_milyoun_not_m_and_spaced_labels():
    js = (ROOT / "app/static/dashboard.js").read_text(encoding="utf-8")
    assert "میلیون تومان" in js
    assert not re.search(r'"[MKB]"', js)  # no Latin unit suffixes on the axis
    assert "autoSkip: true" in js and "autoSkipPadding" in js  # y labels skip instead of overlapping
    assert "timeTicks" in js and "maxRotation: 0" in js and 'timeZone: "Asia/Tehran"' in js
    # Wheel/pinch zoom only when the chart is in full screen.
    assert "zoomOn: zoomAvailable && fullscreen" in js
    assert "wheel: { enabled: false }" in js


def test_chart_axis_and_tooltips_use_shared_formatter_and_page_font(client):
    from app.formatting import format_number

    js = (ROOT / "app/static/dashboard.js").read_text(encoding="utf-8")
    nf = (ROOT / "app/static/number-format.js").read_text(encoding="utf-8")
    assert format_number(1120, 0) == "۱٬۱۲۰"  # «٬» (U+066C), never an apostrophe
    assert "\\u066C" in nf or "٬" in nf
    assert "toLocaleString" not in js and "NumberFormat(" not in js  # ticks/tooltips only via NumberFa
    # Canvas text drawn in Vazirmatn (the default canvas font shows «٬» like «'»), re-drawn once it loads.
    assert "Chart.defaults.font.family = APP_FONT" in js and "Vazirmatn" in js
    assert "document.fonts.load" in js


def test_layout_css_contract():
    css = (ROOT / "app/static/style.css").read_text(encoding="utf-8")
    block = css[css.index("Dashboard (Phase 2"):]
    assert "@media (min-width: 900px)" in block and "@media (max-width: 899px)" in block
    assert '"hero" "assets" "chart" "tiles" "report"' in block  # phones: tiles below the chart
    assert '"hero tiles"' in block  # desktop: tiles beside the hero
    assert "#chart-asset-select:focus-visible" in block and ".range button:focus-visible" in block
    assert "#chart-fullscreen { display: none; }" not in css  # full screen reachable on phones


# --- rendered dashboard -------------------------------------------------------------------

def _seed(client):
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User

    _register(client)
    _set_price("btc", "1000000")
    _set_price("usd", "100000")
    client.post("/profile", data={"btc": "2", "usd": "200", "cash_toman": "1500000", "csrf": _csrf(client)})
    client.post("/profile/debts", data={"title": "وام", "monthly_toman": "100000", "months_left": "3",
                                        "due_year": "1405", "due_month": "1", "due_day": "1",
                                        "csrf": _csrf(client, "/profile?tab=debts")})
    db = SessionLocal()
    user = db.query(User).filter(User.username == "alice").one()
    now = datetime.now(timezone.utc)
    for hours, btc in ((24, "900000"), (24 * 7, "800000")):
        db.add(PortfolioSnapshot(user_id=user.id, taken_at=now - timedelta(hours=hours), total_toman=Decimal("1"),
                                 breakdown_json=json.dumps({"total": "1", "unit_price": {"btc": btc, "usd": "100000"}})))
    db.commit()
    db.close()


def test_dashboard_numbers_match_previous_formulas(client, no_network):
    """Totals are computed exactly as before Phase 2 (only the layout changed)."""
    from app.db import SessionLocal
    from app.formatting import format_number, format_toman
    from app.models import Debt, User
    from app.portfolio import build_portfolio, load_prices

    _seed(client)
    html = client.get("/dashboard").text
    db = SessionLocal()
    user = db.query(User).filter(User.username == "alice").one()
    view = build_portfolio(user, load_prices(db))
    debt = sum(Decimal(d.monthly_toman) * d.months_left for d in db.query(Debt).filter(Debt.user_id == user.id))
    db.close()
    old_net = format_toman(view.total_toman - debt)               # pre-Phase-2 net_label
    old_total = format_toman(view.total_toman)                    # pre-Phase-2 total_label
    old_usd = format_number(view.total_toman / Decimal("100000"), 2)  # pre-Phase-2 usd label (trimmed)
    assert old_net == "۲۳٬۲۰۰٬۰۰۰" and old_total == "۲۳٬۵۰۰٬۰۰۰"
    assert f'data-mask="portfolio">{old_net}</span>' in html
    tfoot = html[html.index("<tfoot>"):html.index("</tfoot>")]
    assert old_total in tfoot
    assert f"title=\"{format_toman(debt)} تومان\"" in html
    assert old_usd == "۲۳۵" and "<bdi dir=\"ltr\">۲۳۵٫۰۰</bdi> <small>دلار آمریکا</small>" in html
    table = html[html.index('id="portfolio-table"'):html.index("</table>")]
    for row in view.rows:
        if row.value_toman:
            assert f"<b>{format_toman(row.value_toman)}</b>" in table, row.key


def test_dashboard_change_chips_and_tiles(client, no_network):
    _seed(client)
    html = client.get("/dashboard").text
    # 24h: 2 BTC × (1,000,000 − 900,000) = +200,000 on a past net worth of 23,300,000 − 300,000
    assert 'data-change="24h"><bdi>▲ ۰٫۸۷٪</bdi>' in html
    # 7d: +400,000 on 23,100,000 − 300,000
    assert 'data-change="7d"><bdi>▲ ۱٫۷۵٪</bdi>' in html
    assert "۲۰۰٬۰۰۰</bdi> تومان بیشتر از دیروز" in html
    tile = html[html.index('id="tile-next-debt"'):html.index('id="tile-month-spend"')]
    assert "۱۰۰٬۰۰۰" in tile and "وام" in tile and re.search(r'badge-due[^"]*">(امروز|فردا|[۰-۹]+ روز دیگر)<', tile)
    assert 'id="tile-month-spend"' in html and "خرج این ماه" in html
    assert "۲۰۰٫۰۰" in html  # USD holding with 2 decimals
    assert 'class="acards only-mob"' in html and 'id="portfolio-table"' in html
    for rng in ("7", "30", "90", "365", "all"):
        assert f'data-range="{rng}"' in html
    chart = json.loads(re.search(r'<script id="chart-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert len(chart["times"]) == len(chart["labels"]) == len(chart["series"][0]["data"])
    assert chart["times"] == sorted(chart["times"]) and chart["now"] == chart["times"][-1]


def test_dashboard_without_history_shows_dash(client, no_network):
    _register(client)
    _set_price("btc", "1000000")
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    assert 'data-change="24h"><bdi>—</bdi>' in html and 'data-change="7d"><bdi>—</bdi>' in html
    assert "سابقهٔ قیمت کافی نیست" in html
    assert "قسطی ثبت نشده" in html


def test_four_assets_with_different_moves_show_four_different_7d_chips(client, no_network):
    """Each asset's «۷ روز» chip uses its own unit price vs its own price 7 days ago."""
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User

    _register(client)
    now_prices = {"btc": "1100000", "eth": "950000", "gold": "1000000", "usd": "102500"}
    then_prices = {"btc": "1000000", "eth": "1000000", "gold": "1000000", "usd": "100000"}
    for key, price in now_prices.items():
        _set_price(key, price)
    client.post("/profile", data={"btc": "1", "eth": "1", "gold_grams": "1", "usd": "10", "csrf": _csrf(client)})
    db = SessionLocal()
    user = db.query(User).filter(User.username == "alice").one()
    db.add(PortfolioSnapshot(user_id=user.id, taken_at=datetime.now(timezone.utc) - timedelta(days=7),
                             total_toman=Decimal("1"),
                             breakdown_json=json.dumps({"total": "1", "unit_price": then_prices})))
    db.commit()
    db.close()
    html = client.get("/dashboard").text
    table = html[html.index('id="portfolio-table"'):html.index("<tfoot>")]
    chips = dict(re.findall(r'<span>([^<]+?)(?: <span class="badge[^"]*">[^<]*</span>)?</span>\s*</div>.*?'
                            r'<span class="chg [a-z]+">([^<]+)</span>', table, re.S))
    assert chips == {"بیت‌کوین": "▲ ۱۰٪", "اتریوم": "▼ ۵٪", "طلا ۱۸ عیار": "بدون تغییر", "دلار آمریکا": "▲ ۲٫۵٪"}
    assert len(set(chips.values())) == 4
