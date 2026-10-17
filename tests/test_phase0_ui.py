"""Redesign Phase 0: template-only behaviour (copy, empty states, hidden zero rows, hints)."""
from datetime import datetime, timezone
from decimal import Decimal

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401


def _set_price(symbol, price):
    from app.db import SessionLocal
    from app.models import MarketPrice
    db = SessionLocal()
    db.merge(MarketPrice(symbol=symbol, price_toman=Decimal(price), fetched_at=datetime.now(timezone.utc)))
    db.commit(); db.close()


def test_landing_has_no_false_privacy_claim(client):
    html = client.get("/").text
    assert "داده روی سرور خودتان می‌ماند" not in html
    assert "مدیر سایت به آن دسترسی دارد" in html
    assert "رمزگذاری نمی‌شوند" in html


def test_register_shows_rules_from_validator_before_any_error(client):
    from app.security import PASSWORD_MIN_LENGTH, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, USERNAME_RE
    from app.formatting import persian_digits
    html = client.get("/register").text
    assert f"حداقل {persian_digits(str(PASSWORD_MIN_LENGTH))} کاراکتر" in html
    assert f"{persian_digits(str(USERNAME_MIN_LENGTH))} تا {persian_digits(str(USERNAME_MAX_LENGTH))} کاراکتر" in html
    assert f'minlength="{PASSWORD_MIN_LENGTH}"' in html
    assert 'role="alert"' not in html
    # regex is still exactly what it was (3..32, starts with a letter)
    assert USERNAME_RE.pattern == r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$"


def test_signup_lands_on_profile_with_assets_before_account(client, no_network):
    t = _csrf(client, "/register")
    r = client.post("/register", data={"username": "newbie", "password": "password123",
                                        "password_confirm": "password123", "csrf": t}, follow_redirects=False)
    assert r.headers["location"] == "/profile"
    html = client.get("/profile").text
    assert html.index('name="gold_grams"') < html.index('name="new_password"')


def test_dashboard_empty_state_for_new_user(client, no_network):
    _register(client, "emptyuser")
    html = client.get("/dashboard").text
    assert "هنوز دارایی‌ای ثبت نکرده‌اید" in html
    assert 'id="portfolio-table"' not in html


def test_dashboard_hides_zero_rows_and_shows_them_after_value(client, no_network):
    _register(client)
    _set_price("btc", "1000000")
    _set_price("eth", "500000")
    client.post("/profile", data={"btc": "2", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    table = html[html.index('id="portfolio-table"'):html.index("</table>", html.index('id="portfolio-table"'))]
    assert "/static/logos/btc.svg" in table
    assert "/static/logos/eth.svg" not in table
    assert "دارایی با مقدار صفر پنهان است" in html
    client.post("/profile", data={"btc": "2", "eth": "1", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    table = html[html.index('id="portfolio-table"'):html.index("</table>", html.index('id="portfolio-table"'))]
    assert "/static/logos/eth.svg" in table


def test_debts_expenses_spends_empty_states(client, no_network):
    _register(client)
    html = client.get("/profile?tab=debts").text
    assert "هنوز بدهی یا قسطی ثبت نکرده‌اید" in html and 'href="#debt-form"' in html
    assert "هنوز خرج ماهانه‌ای ثبت نکرده‌اید" in html and 'href="#expense-form"' in html
    daily = client.get("/dashboard?tab=daily").text
    assert "در این ماه خرجی ثبت نشده است" in daily


def test_daily_form_on_top_with_today_in_persian_digits(client, no_network):
    import jdatetime
    from app.formatting import persian_digits
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    assert html.index('id="daily-spend-form"') < html.index('id="daily-report-heading"')
    today = jdatetime.date.today()
    assert f'name="year" value="{persian_digits(str(today.year))}"' in html
    assert f'name="day" value="{persian_digits(str(today.day))}"' in html


def test_spend_form_accepts_persian_and_latin_digits(client, no_network):
    import re
    import jdatetime
    _register(client)
    page = client.get("/dashboard?tab=daily").text
    cat = re.search(r'name="category_id" id="spend-child" required>\s*<option value="(\d+)"', page).group(1)
    today = jdatetime.date.today()
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    for amount, y in (("۱۵۰۰۰۰", str(today.year).translate(fa)), ("150000", str(today.year))):
        client.post("/profile/spends", data={"csrf": _csrf(client, "/dashboard?tab=daily"), "amount_toman": amount,
                    "category_id": cat, "year": y, "month": str(today.month).translate(fa), "day": str(today.day),
                    "note": "", "jy": str(today.year), "jm": str(today.month)})
    from app.db import SessionLocal
    from app.models import DailySpend
    db = SessionLocal()
    assert [int(s.amount_toman) for s in db.query(DailySpend).all()] == [150000, 150000]
    db.close()


def test_privacy_values_shown_by_default_with_labeled_toggle(client, no_network):
    _register(client)
    html = client.get("/dashboard").text
    assert 'localStorage.getItem("privacy-portfolio") !== "1"' in html
    assert "privacy-label-hide" in html and "پنهان کردن" in html


def test_html_lang_and_dir(client):
    for path in ("/", "/login", "/register"):
        assert '<html lang="fa" dir="rtl"' in client.get(path).text
