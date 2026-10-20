"""Home v2 (mockups/app-v2/home): welcome card, price freshness line, stale/error banners, chart fallback."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def _price_at(when, symbol="btc", price="1000000"):
    from app.db import SessionLocal
    from app.models import MarketPrice

    db = SessionLocal()
    row = db.get(MarketPrice, symbol) or MarketPrice(symbol=symbol)
    row.price_toman = Decimal(price)
    row.fetched_at = when.replace(tzinfo=None)
    db.merge(row)
    db.commit()
    db.close()


def _with_asset(client):
    _register(client)
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})
    _forget_fetch_state()


def _forget_fetch_state():
    """Background refreshes in tests hit the network guard and record a failure; start each check clean."""
    from app import config, price_fetch_state

    (config.DATA_DIR / price_fetch_state.STATE_FILE).unlink(missing_ok=True)
    price_fetch_state._memory = None


def _now():
    return datetime.now(timezone.utc)


def test_welcome_only_for_users_without_assets_and_debts(client, no_network):
    _register(client)
    html = client.get("/dashboard").text
    assert 'id="home-welcome"' in html and "خوش آمدید! بیایید شروع کنیم" in html
    assert 'href="/assets">افزودن دارایی</a>' in html
    assert 'href="/profile?tab=debts">افزودن</a>' in html and 'href="/profile">تنظیم</a>' in html
    assert 'class="dash"' not in html


def test_debts_only_user_gets_the_dashboard(client, no_network):
    _register(client)
    from app.db import SessionLocal
    from app.models import Debt, User

    db = SessionLocal()
    user = db.query(User).filter_by(username="alice").one()
    debt = Debt(user_id=user.id, title="وام", monthly_toman=Decimal("4500000"), months_left=3,
                due_year=1405, due_month=9, due_day=5)
    db.add(debt)
    db.commit()
    db.close()
    html = client.get("/dashboard").text
    assert 'id="home-welcome"' not in html and 'class="dash"' in html


def test_fresh_line_shows_relative_age_and_exact_time(client, no_network):
    _with_asset(client)
    _price_at(_now() - timedelta(minutes=4))
    html = client.get("/dashboard").text
    assert "قیمت‌ها <b>۴ دقیقه پیش</b> به‌روز شد" in html
    assert "وقت تهران" in html and "v2-banner" not in html


def test_stale_after_two_hours_shows_status_banner(client, no_network):
    _with_asset(client)
    _price_at(_now() - timedelta(hours=3, minutes=5))
    html = client.get("/dashboard").text
    assert "قیمت‌ها <b>۳ ساعت</b> است به‌روز نشده‌اند" in html
    assert 'role="status"' in html and "قیمت‌ها قدیمی‌اند" in html
    assert "ارزش‌ها با قیمت ۳ ساعت پیش حساب شده‌اند." in html


def test_just_under_two_hours_is_still_fresh(client, no_network):
    _with_asset(client)
    _price_at(_now() - timedelta(hours=1, minutes=59))
    assert "قیمت‌ها قدیمی‌اند" not in client.get("/dashboard").text


def test_failed_fetch_after_last_success_shows_alert(client, no_network):
    from app import price_fetch_state

    _with_asset(client)
    _price_at(_now() - timedelta(hours=3))
    price_fetch_state.record(False)
    html = client.get("/dashboard").text
    assert 'role="alert"' in html and "قیمت تازه از چنده نرسید" in html
    assert "ارزش‌ها با آخرین قیمت (۳ ساعت پیش) حساب شده‌اند." in html
    assert "تلاش دوباره" in html


def test_older_failure_is_ignored_once_prices_are_newer(client, no_network):
    from app import price_fetch_state

    _with_asset(client)
    price_fetch_state.record(False, _now() - timedelta(minutes=30))
    _price_at(_now() - timedelta(minutes=5))
    html = client.get("/dashboard").text
    assert "قیمت تازه از چنده نرسید" not in html and "به‌روز شد" in html


def test_fetch_state_file_roundtrip_and_survives_reimport(client):
    import importlib

    from app import config, price_fetch_state

    when = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    price_fetch_state.record(False, when)
    assert (config.DATA_DIR / "price_fetch_state.json").exists()
    mod = importlib.reload(price_fetch_state)  # fresh process state: memory gone, file stays
    assert mod.last() == (False, when)


def test_manual_refresh_failure_is_recorded(client, monkeypatch):
    import app.jobs as jobs
    from app import price_fetch_state

    _with_asset(client)

    async def boom():
        raise RuntimeError("chande down")

    monkeypatch.setattr(jobs, "fetch_chande_prices", boom)
    client.post("/dashboard/refresh-prices", data={"csrf": _csrf(client, "/dashboard")})
    ok, _at = price_fetch_state.last()
    assert ok is False


def test_hourly_job_success_is_recorded(client, monkeypatch):
    import asyncio

    import app.jobs as jobs
    from app import price_fetch_state

    async def fine():
        return {}

    monkeypatch.setattr(jobs, "fetch_chande_prices", fine)
    monkeypatch.setattr(jobs, "upsert_prices", lambda _f: None)
    asyncio.run(jobs.fetch_and_store_prices())
    assert price_fetch_state.last()[0] is True


def test_primary_button_is_solid_teal_with_dark_text():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    block = css[css.index(".btn-primary {"):css.index("}", css.index(".btn-primary {"))]
    assert "gradient" not in block and "color: #04120e" in block
    light = css[css.index('[data-theme="light"] .btn-primary,'):]
    light = light[:light.index("}")]
    assert "#fff" not in light and "#04120e" in light and "#0d9f7a" in light


def test_chart_skeleton_and_failure_message_in_js():
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert "showChartSkeleton, 1000" in js
    assert "نمودار باز نشد. اینترنت را بررسی کنید و دوباره امتحان کنید." in js and "تلاش دوباره" in js


def test_dashboard_copy_uses_persian_comma(client, no_network):
    _with_asset(client)
    html = client.get("/dashboard").text
    hero = html[html.index('class="summary dash-hero"'):html.index('id="chart-panel"')]
    assert "·" not in hero
    assert 'aria-label="نمایش یا پنهان کردن خالص دارایی"' in html
