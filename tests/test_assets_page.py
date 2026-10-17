"""Phase 1 piece 2: dedicated Assets page (/assets). Same save handler (POST /profile), no DB changes."""
import inspect
import re
from decimal import Decimal
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
QTY_FIELDS = ("gold_grams", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram", "silver_grams",
              "btc", "ada", "eth", "sol", "doge", "matic", "usd", "cash_toman")


def _assets_form(html):
    form = re.search(r'<form method="post" action="/profile" class="assets-page"[^>]*>(.*?)</form>', html, re.S)
    assert form, "assets form missing"
    return form.group(1)


def _fields(form_html):
    return {m.group(1): m.group(2) for m in re.finditer(r'<input[^>]*\bname="([^"]+)"[^>]*\bvalue="([^"]*)"', form_html)}


def _user(name="alice"):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    return db, db.query(User).filter_by(username=name).one()


def test_assets_requires_login(client):
    r = client.get("/assets", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_old_profile_assets_urls_redirect_to_assets_and_keep_login(client, no_network):
    r = client.get("/profile?tab=assets", follow_redirects=False)  # anonymous: /assets, which then asks for login
    assert r.status_code == 303 and r.headers["location"] == "/assets"
    _register(client)
    for path in ("/profile?tab=assets", "/profile?tab=assets&edit=3"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/assets", path
        page = client.get(path)
        assert page.status_code == 200 and str(page.url).endswith("/assets")
        assert 'name="gold_grams"' in page.text  # still logged in


def test_every_asset_field_of_the_save_handler_is_on_the_page(client, no_network):
    from app.profile import profile_save
    _register(client)
    form = _assets_form(client.get("/assets").text)
    handler_fields = set(inspect.signature(profile_save).parameters) - {"request", "db", "csrf", "clear_sanjeh"}
    assert handler_fields == set(QTY_FIELDS) | {"sanjeh_token"}
    for name in handler_fields:
        assert form.count(f'name="{name}"') == 1, name
    assert 'name="csrf"' in form
    # groups as cards, in mockup order
    heads = re.findall(r'<h2 id="group-\w+">([^<]+)</h2>', form)
    assert heads == ["طلا و سکه", "ارز و نقد", "رمزارز", "خودرو"]
    # quantity inputs keep the old attributes (Persian/Latin input, LTR, exact values)
    for name in QTY_FIELDS:
        assert re.search(rf'<input name="{name}" value="" placeholder="۰" inputmode="decimal" dir="ltr"', form), name
    assert re.search(r'<input name="cash_toman"[^>]*data-thousands', form)


def test_new_user_sees_add_chips_and_held_rows_hide_their_chip(client, no_network):
    _register(client)
    html = client.get("/assets").text
    assert html.count("افزودن دارایی در این گروه") == 3
    assert 'data-add-asset="btc"' in html and re.search(r'data-asset-row="btc"[^>]*hidden', html)
    client.post("/profile", data={"btc": "0.5", "csrf": _csrf(client, "/assets")})
    html = client.get("/assets").text
    assert 'data-add-asset="btc"' not in html
    assert not re.search(r'data-asset-row="btc"[^>]*hidden', html)
    assert 'data-add-asset="eth"' in html


def test_save_round_trip_keeps_exact_values(client, no_network):
    _register(client)
    data = {**{k: "" for k in QTY_FIELDS}, "gold_grams": "۱٫۵", "ada": "0.12345678", "csrf": _csrf(client, "/assets")}
    r = client.post("/profile", data=data, follow_redirects=False)
    assert r.status_code == 303
    db, u = _user()
    assert u.gold_grams == Decimal("1.5") and u.ada == Decimal("0.12345678")
    db.close()
    # reload: the page shows the exact values, and re-saving it unchanged changes nothing
    fields = _fields(_assets_form(client.get("/assets").text))
    assert fields["gold_grams"] == "۱٫۵" and fields["ada"] == "۰٫۱۲۳۴۵۶۷۸"
    assert client.post("/profile", data=fields, follow_redirects=False).status_code == 303
    fields2 = _fields(_assets_form(client.get("/assets").text))
    assert fields2 == {**fields, "csrf": fields2["csrf"]}
    client.post("/profile", data=fields2)
    db, u = _user()
    assert u.gold_grams == Decimal("1.5") and u.ada == Decimal("0.12345678")
    assert all(Decimal(getattr(u, k)) == 0 for k in QTY_FIELDS if k not in ("gold_grams", "ada"))
    db.close()


def test_invalid_value_shows_assets_page_again_and_saves_nothing(client, no_network):
    _register(client)
    client.post("/profile", data={"btc": "2", "csrf": _csrf(client, "/assets")})
    r = client.post("/profile", data={"btc": "1.2.3", "eth": "5", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 200
    assert "یکی از مقادیر وارد شده نامعتبر است" in r.text and 'class="assets-page"' in r.text
    assert 'name="btc" value="1.2.3"' in r.text  # what was typed is kept for fixing
    db, u = _user()
    assert u.btc == Decimal("2") and u.eth == 0
    db.close()


def test_header_total_and_row_values_match_the_dashboard_math(client, no_network):
    from app.db import SessionLocal
    from app.formatting import format_toman
    from app.models import MarketPrice, utcnow
    from app.portfolio import build_portfolio, load_prices
    _register(client)
    db = SessionLocal()
    row = db.query(MarketPrice).filter_by(symbol="btc").first() or MarketPrice(symbol="btc")
    row.price_toman, row.fetched_at = Decimal("10000000"), utcnow()
    db.add(row); db.commit(); db.close()
    client.post("/profile", data={"btc": "0.25", "cash_toman": "1000", "csrf": _csrf(client, "/assets")})
    html = client.get("/assets").text
    db, u = _user()
    view = build_portfolio(u, load_prices(db))
    db.close()
    assert view.total_toman == Decimal("2501000")
    assert re.search(rf'data-assets-total data-base="2501000">{format_toman(view.total_toman)}<', html)
    assert 'data-asset-row="btc" data-price="10000000" data-base="2500000"' in html
    assert "قیمت در دسترس نیست" not in html.split('data-asset-row="btc"')[1].split("</div>\n    </div>")[0]


def test_profile_no_longer_has_assets_section(client, no_network):
    _register(client)
    for path in ("/profile", "/profile?section=settings", "/profile?tab=debts", "/profile?tab=whatever"):
        html = client.get(path).text
        for name in (*QTY_FIELDS, "sanjeh_token", "clear_sanjeh"):
            assert f'name="{name}"' not in html, (path, name)
        assert 'action="/profile" class' not in html
    settings = client.get("/profile").text
    assert 'id="account-settings"' in settings and 'name="new_password"' in settings
    assert 'id="advanced"' in settings and 'id="settings-account-actions"' in settings
    debts = client.get("/profile?tab=debts").text
    assert 'id="debt-form"' in debts and 'href="/assets"' in debts and "/profile?tab=assets" not in debts


def test_nav_assets_link_points_to_assets_and_is_active_there(client, no_network):
    _register(client)
    html = client.get("/assets").text
    nav = re.search(r'<nav class="main-nav".*?</nav>', html, re.S).group(0)
    active = re.findall(r'<a class="main-nav-item is-active" href="([^"]+)" data-nav="(\w+)"', nav)
    assert active == [("/assets", "assets")]
    assert nav.count('aria-current="page"') == 1
    assert "/profile?tab=assets" not in client.get("/dashboard").text


def test_dashboard_edit_links_point_to_assets(client, no_network):
    _register(client)
    empty = client.get("/dashboard").text
    assert 'href="/assets">افزودن دارایی</a>' in empty
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client, "/assets")})
    html = client.get("/dashboard").text
    assert 'href="/assets">ویرایش موجودی</a>' in html
    assert 'href="/profile">ویرایش موجودی' not in html and 'href="/profile">افزودن دارایی' not in html


def test_car_keeps_existing_sanjeh_fields_without_new_status_ui(client, no_network, monkeypatch):
    async def fake_refresh(user):
        user.car_toman = Decimal("680000000")
        user.car_count = 1

    monkeypatch.setattr(no_network, "refresh_user_sanjeh_car", fake_refresh)
    _register(client)
    html = client.get("/assets").text
    assert 'name="sanjeh_token"' in html and 'name="clear_sanjeh"' not in html
    client.post("/profile", data={"sanjeh_token": "tok", "csrf": _csrf(client, "/assets")})
    html = client.get("/assets").text
    assert "توکن ذخیره شده است" in html and 'name="clear_sanjeh"' in html and "۶۸۰٬۰۰۰٬۰۰۰" in html
    assert "متصل به سنجه" not in html and "قطع اتصال" not in html and "خواندن دوباره" not in html
    # the token is kept on a plain re-save (empty token field), exactly as before
    client.post("/profile", data={"csrf": _csrf(client, "/assets")})
    db, u = _user()
    assert u.sanjeh_token == "tok"
    db.close()


def test_save_bar_and_leave_warning_contract(client, no_network):
    _register(client)
    html = client.get("/assets").text
    bar = re.search(r'<div class="assets-save-bar"[^>]*>(.*?)</div>', html, re.S)
    assert bar and "hidden" in bar.group(0)  # only shown once something changes
    assert "ذخیرهٔ تغییرات" in bar.group(1) and "انصراف" in bar.group(1) and "data-dirty-count" in bar.group(1)
    assert "<noscript>" in html  # without JS the form can still be saved
    assert re.search(r'src="/static/assets-page\.js\?v=\w+"', html)
    js = (STATIC / "assets-page.js").read_text(encoding="utf-8")
    assert "--page-extra-bottom" in js and "beforeunload" in js and "تغییر ذخیره نشده" in js
    assert "NF.normalize" in js
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    block = css[css.index("Assets page (Phase 1 piece 2"):]
    mobile = block[block.index("@media (max-width: 899px) {"):]
    assert "bottom: calc(var(--main-nav-h) + env(safe-area-inset-bottom));" in mobile
    assert ".arow[hidden] { display: none; }" in block


def test_static_asset_version_bumped():
    from app.config import STATIC_ASSET_VERSION
    assert STATIC_ASSET_VERSION != "20261017g"
