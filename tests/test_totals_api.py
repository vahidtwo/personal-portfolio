"""Amounts are not in the page source; GET /api/amounts returns them to the signed-in user, same-origin only."""
import re
from decimal import Decimal

from app.formatting import format_toman
from tests.amounts_helper import amounts_for, with_amounts
from tests.test_debts_v2 import _seed, clock  # noqa: F401
from tests.test_holdings import _register, no_network  # noqa: F401
from tests.test_quick_ux_5c import _seed_spends

PAGES = ("/dashboard", "/dashboard?tab=daily", "/profile?tab=debts", "/assets")
# Fake amounts that appear nowhere else on the pages.
DEBT, EXPENSE, CASH, SALARY, CAR = 2_357_000, 7_130_000, 41_270_000, 93_410_000, 683_150_000
SPENDS = (450000, 1250000, 99000)


def _seed_all(client):
    from app.db import SessionLocal
    from app.models import User

    _register(client)
    _seed([("وام نمونه", DEBT, 12, 1405, 8, 5)], expenses=[("اجاره نمونه", EXPENSE, 1)], salary=SALARY)
    _seed_spends()
    db = SessionLocal()
    user = db.query(User).filter_by(username="alice").one()
    user.cash_toman = Decimal(CASH)
    user.sanjeh_token = "fake-token"
    user.car_toman = Decimal(CAR)
    user.car_count = 3
    db.commit()
    db.close()


def _labels():
    return [format_toman(Decimal(v)) for v in (DEBT, EXPENSE, CASH, SALARY, CAR, CASH + CAR, DEBT * 12, CASH + CAR - DEBT * 12) + SPENDS]


def test_page_source_has_no_amounts(client, no_network, clock):
    _seed_all(client)
    for url in PAGES:
        html = client.get(url).text
        for label in _labels():
            assert label not in html, (url, label)
        for raw in (str(DEBT), str(EXPENSE), str(CASH), str(SALARY), str(CAR), str(CASH + CAR), "2,357,000", "41270000.0"):
            assert raw not in html, (url, raw)
        assert not re.search(r"\sdata-form=['\"]", html)
        assert 'data-sort-value="' not in html and 'data-sort-qty="' not in html


def test_amounts_fill_every_placeholder(client, no_network, clock):
    _seed_all(client)
    home = with_amounts(client, "/dashboard")
    assert format_toman(Decimal(CASH)) in home and format_toman(Decimal(DEBT)) in home
    assert format_toman(Decimal(CASH + CAR - DEBT * 12)) in home  # net worth
    debts = with_amounts(client, "/profile?tab=debts")
    assert format_toman(Decimal(DEBT)) in debts and format_toman(Decimal(EXPENSE)) in debts
    assert re.search(r"\sdata-form=['\"]", debts)
    assets = with_amounts(client, "/assets")
    for v in (CASH, CAR, CASH + CAR):
        assert format_toman(Decimal(v)) in assets, v
    assert re.search(r'data-assets-total data-base="%d' % (CASH + CAR), assets)
    assert "car-count" in amounts_for(client, "/assets") and "car-value-confirm" in amounts_for(client, "/assets")
    assert 'name="cash_toman_keep"' in client.get("/assets").text
    daily = with_amounts(client, "/dashboard?tab=daily")
    assert format_toman(Decimal(1250000)) in daily
    for url in PAGES:
        html = client.get(url).text
        keys = set(re.findall(r'data-amt="([^"]*)"', html))
        assert keys and keys <= set(amounts_for(client, url)), url


def test_salary_stays_out_of_the_amounts(client, no_network, clock):
    _seed_all(client)
    for url in PAGES:
        values = amounts_for(client, url)
        assert format_toman(Decimal(SALARY)) not in str(values)


def test_api_is_no_store_and_needs_a_session(client, no_network, clock):
    _seed_all(client)
    r = client.get("/api/amounts?path=/dashboard")
    assert r.status_code == 200
    assert "no-store" in r.headers["cache-control"] and "access-control-allow-origin" not in r.headers
    client.cookies.clear()
    r = client.get("/api/amounts?path=/dashboard")
    assert r.status_code == 401 and "no-store" in r.headers["cache-control"]
    assert CASH and format_toman(Decimal(CASH)) not in r.text


def test_api_refuses_cross_site(client, no_network, clock):
    _seed_all(client)
    url = "/api/amounts?path=/dashboard"
    assert client.get(url, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(url, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert client.get(url, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get(url, headers={"Origin": "null"}).status_code == 403
    assert client.get(url, headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}).status_code == 200


def test_api_only_known_pages(client, no_network, clock):
    _seed_all(client)
    for bad in ("", "/admin", "/assets/car", "https://evil.example/dashboard", "//evil.example/dashboard", "/api/amounts"):
        assert client.get("/api/amounts", params={"path": bad}).status_code == 400, bad
    assert client.post("/api/amounts?path=/dashboard").status_code == 405


def test_static_js_wiring():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "app" / "static"
    js = (static / "amounts.js").read_text(encoding="utf-8")
    assert 'cache: "no-store"' in js and 'credentials: "same-origin"' in js and "localStorage" not in js
    assert "Amounts.refresh" in (static / "debts-page.js").read_text(encoding="utf-8")
    assert "Amounts.refresh" in (static / "spending-page.js").read_text(encoding="utf-8")
    assert "amounts:filled" in (static / "dashboard.js").read_text(encoding="utf-8")


def test_cash_left_empty_by_the_page_is_kept_on_save(client, no_network, clock):
    from tests.test_holdings import _csrf
    _seed_all(client)
    tok = _csrf(client, "/assets")
    client.post("/profile", data={"cash_toman": "", "cash_toman_keep": "1", "btc": "0", "next": "/assets", "csrf": tok})
    assert format_toman(Decimal(CASH)) in with_amounts(client, "/assets")
    client.post("/profile", data={"cash_toman": "5000", "cash_toman_keep": "1", "next": "/assets", "csrf": tok})
    assert amounts_for(client, "/assets")["input-cash_toman"] == format_toman(Decimal(5000))
    client.post("/profile", data={"cash_toman": "", "next": "/assets", "csrf": tok})  # filled page, cleared by the user
    assert amounts_for(client, "/assets")["input-cash_toman"] in ("", "۰")
