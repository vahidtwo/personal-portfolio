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
    html = client.get("/register").text  # redirects to /auth (unified sign-in)
    assert f"دست‌کم {persian_digits(str(PASSWORD_MIN_LENGTH))} حرف" in html
    assert f"{persian_digits(str(USERNAME_MIN_LENGTH))} تا {persian_digits(str(USERNAME_MAX_LENGTH))} حرف" in html
    assert 'role="alert"' not in html
    # regex is still exactly what it was (3..32, starts with a letter)
    assert USERNAME_RE.pattern == r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$"


def test_signup_lands_on_assets_page(client, no_network):
    t = _csrf(client, "/register")
    r = client.post("/register", data={"username": "newbie", "password": "password123",
                                        "password_confirm": "password123", "csrf": t}, follow_redirects=False)
    assert r.headers["location"] == "/assets"  # Phase 1: assets moved off the profile page
    html = client.get("/assets").text
    assert 'name="gold_grams"' in html and 'name="new_password"' not in html


def test_dashboard_empty_state_for_new_user(client, no_network):
    _register(client, "emptyuser")
    html = client.get("/dashboard").text
    # home v2: no assets and no debts -> welcome card instead of an all-zero dashboard
    assert 'id="home-welcome"' in html and "خوش آمدید! بیایید شروع کنیم" in html
    assert 'id="portfolio-table"' not in html and 'id="chart-panel"' not in html


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
    assert "هنوز هزینهٔ ماهانه‌ای ثبت نکرده‌اید" in html and 'href="#expense-form"' in html
    daily = client.get("/dashboard?tab=daily").text
    assert "در این ماه خرجی ثبت نشده است" in daily


def test_daily_form_on_top_with_today_in_persian_digits(client, no_network):
    import jdatetime
    from app.formatting import persian_digits
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    assert html.index('id="daily-spend-form"') < html.index('id="daily-report-heading"')
    from app.formatting import tehran_today
    today = tehran_today()
    assert f'name="year" value="{persian_digits(str(today.year))}"' in html
    assert f'name="day" value="{persian_digits(str(today.day))}"' in html


def test_spend_form_accepts_persian_and_latin_digits(client, no_network):
    import re
    import jdatetime
    _register(client)
    page = client.get("/dashboard?tab=daily").text
    cat = re.search(r'name="category_id" id="spend-child" required>\s*<option value="(\d+)"', page).group(1)
    from app.formatting import tehran_today
    today = tehran_today()
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
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})  # home v2: an all-empty user gets the welcome card
    html = client.get("/dashboard").text
    assert 'localStorage.getItem("privacy-portfolio") !== "1"' in html
    assert "privacy-label-hide" in html and "پنهان کردن" in html


def test_html_lang_and_dir(client):
    for path in ("/", "/login", "/register"):
        assert '<html lang="fa" dir="rtl"' in client.get(path).text


def test_chart_picker_hides_zero_assets_like_the_table(client, no_network):
    import re
    _register(client)
    _set_price("btc", "1000000")
    _set_price("eth", "500000")
    client.post("/profile", data={"btc": "2", "gold_grams": "1", "csrf": _csrf(client)})  # gold has no price

    def picker():
        html = client.get("/dashboard").text
        sel = html[html.index('id="chart-asset-select"'):html.index("</select>", html.index('id="chart-asset-select"'))]
        return re.findall(r'<option value="([^"]*)"', sel)

    opts = picker()
    assert opts[0] == "total"
    assert "btc" in opts and "eth" not in opts
    assert "gold" in opts  # quantity > 0 but no price (value 0): still shown, same as the table
    client.post("/profile", data={"btc": "2", "gold_grams": "1", "eth": "1", "csrf": _csrf(client)})
    assert "eth" in picker()


def test_chart_default_falls_back_to_total_when_default_asset_hidden(client, no_network, monkeypatch):
    import re
    import app.dashboard as dash
    real_render = dash.render

    def render(request, name, db, **ctx):
        if name == "dashboard.html" and "default_chart_asset_key" in ctx:
            ctx["default_chart_asset_key"] = monkeypatch_key["key"]
        return real_render(request, name, db, **ctx)
    monkeypatch_key = {"key": "eth"}
    monkeypatch.setattr(dash, "render", render)
    _register(client)
    _set_price("btc", "1000000")
    _set_price("eth", "500000")
    client.post("/profile", data={"btc": "2", "csrf": _csrf(client)})

    def selected():
        html = client.get("/dashboard").text
        sel = html[html.index('id="chart-asset-select"'):html.index("</select>", html.index('id="chart-asset-select"'))]
        return re.findall(r'<option value="([^"]*)"\s+selected', sel)

    assert selected() == ["total"]  # eth is zero -> hidden -> total is selected (dashboard.js reads select.value)
    monkeypatch_key["key"] = "btc"
    assert selected() == ["btc"]  # a visible default is kept


def test_landing_android_url_in_own_ltr_block(client):
    html = client.get("/").text
    assert '<span class="url-block" dir="ltr">https://portfolio.vahidtwo.ir</span>' in html


def test_profile_mcp_url_uses_request_or_public_base_url(client, no_network, monkeypatch):
    _register(client)
    html = client.get("/profile").text
    assert '<code dir="ltr" class="url-block">http://testserver/mcp</code>' in html
    import app.profile as profile
    monkeypatch.setattr(profile, "PUBLIC_BASE_URL", "https://portfolio.vahidtwo.ir")
    html = client.get("/profile").text
    assert ">https://portfolio.vahidtwo.ir/mcp</code>" in html and "127.0.0.1" not in html


def test_android_setup_prefills_public_server_url():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "android/app/src/main/assets/www/setup.html").read_text(encoding="utf-8")
    assert 'id="site-url"' in html and 'value="https://portfolio.vahidtwo.ir"' in html
    # a saved address still wins over the default
    assert ('urlInput.value = (saved || "").trim() || DEFAULT_URL;' in html
            or "if (saved) urlInput.value = saved;" in html)


def test_monthly_report_toman_after_number_not_ltr_dd(client, no_network):
    import re
    _register(client)
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})  # home v2: an all-empty user gets the welcome card
    for path in ("/dashboard", "/profile?tab=debts"):
        html = client.get(path).text
        assert not re.search(r'<dd class="num"[^>]*dir="ltr"', html), path
        assert re.search(r'<dd class="num"[^>]*><bdi dir="ltr">[^<]+</bdi> تومان</dd>', html), path


def test_glossary_terms(client, no_network):
    _register(client)
    dash = client.get("/dashboard").text
    debts = client.get("/profile?tab=debts").text
    assets = client.get("/assets").text
    for html in (dash, debts):
        assert "هزینهٔ ماهانه" in html and "خرج ماهانه" not in html
    assert "دلار آمریکا" in assets and "دلار نقد" not in assets


def test_privacy_btn_is_pill_not_fixed_circle():
    import re
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app/static/style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.privacy-btn \{([^}]*)\}", css).group(1)
    assert "border-radius: 999px" in rule and "50%" not in rule
    assert not re.search(r"(^|\s)width:\s*44px", rule) and not re.search(r"(^|\s)height:\s*44px", rule)


def test_privacy_note_mentions_backups_and_hashed_passwords(client):
    from app.security import hash_password
    assert hash_password("x" * 8).startswith("$2")  # bcrypt, as the note says
    html = client.get("/").text
    assert "نسخه‌های پشتیبان" in html and "هش‌شده" in html


def test_new_user_profile_fields_empty_and_saving_empty_means_zero(client, no_network):
    import re
    _register(client)
    html = client.get("/assets").text
    for k in ("gold_grams", "btc", "usd", "cash_toman"):
        assert re.search(rf'<input name="{k}" value="" placeholder="۰"', html), k
    assert re.search(r'<input name="salary_toman" value="" placeholder="مبلغ جدید"', client.get("/profile").text)
    data = {k: "" for k in ("gold_grams", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram",
                            "silver_grams", "btc", "ada", "eth", "sol", "doge", "matic", "usd", "cash_toman")}
    data["csrf"] = _csrf(client)
    r = client.post("/profile", data=data, follow_redirects=False)
    assert r.status_code == 303
    client.post("/profile", data={**data, "btc": "۰.۵", "cash_toman": "۱۸٬۵۰۰٬۰۰۰", "csrf": _csrf(client)})
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal(); u = db.query(User).filter_by(username="alice").one()
    assert u.btc == Decimal("0.5") and u.cash_toman == Decimal("18500000") and u.gold_grams == 0
    db.close()
    html = client.get("/assets").text
    assert 'name="btc" value="۰٫۵"' in html


def test_debt_year_placeholder_is_current_jalali_year(client, no_network):
    import jdatetime
    from app.formatting import persian_digits
    _register(client)
    html = client.get("/profile?tab=debts").text
    assert f'name="due_year" value="" inputmode="numeric" placeholder="{persian_digits(str(__import__('app.formatting', fromlist=['x']).tehran_today().year))}"' in html


def test_mcp_box_in_collapsed_advanced_section_and_actions_work(client, no_network):
    import re
    _register(client)
    html = client.get("/profile").text
    m = re.search(r'<details class="card auth-card wide advanced-card" id="advanced">(.*?)</details>', html, re.S)
    assert m, "advanced section must be a collapsed <details> for every user"
    box = m.group(1)
    assert "<summary class=\"advanced-summary\">پیشرفته</summary>" in box
    assert "دستیارهای هوش مصنوعی" in box and "http://testserver/mcp" in box
    assert 'action="/profile/mcp-token"' in box and "ساخت توکن" in box
    # advanced is the last settings section; only the Phase 1 admin/logout rows (per mockup) follow it
    after = html[html.rfind("</details>"):]
    assert after.count("<section") == 1 and 'id="settings-account-actions"' in after, "advanced section is last before the logout rows"
    # issue: details opens so the one-time config is visible, and the token works
    html = client.post("/profile/mcp-token", data={"csrf": _csrf(client)}).text  # follows redirect to /profile
    assert 'id="advanced" open>' in html
    cfg = re.search(r'<textarea id="mcp-cursor-config"[^>]*>(.*?)</textarea>', html, re.S).group(1)
    token = re.search(r"Bearer ([A-Za-z0-9_\-]+)", cfg).group(1)
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    assert client.post("/mcp", json=rpc, headers=hdr).status_code == 200
    # later views: collapsed again, regenerate + revoke offered
    html = client.get("/profile").text
    assert 'id="advanced">' in html and "توکن جدید" in html and 'action="/profile/mcp-token/revoke"' in html
    client.post("/profile/mcp-token/revoke", data={"csrf": _csrf(client)})
    assert client.post("/mcp", json=rpc, headers=hdr).status_code == 401
    assert client.post("/mcp", json=rpc, headers={"Accept": "application/json"}).status_code == 401
