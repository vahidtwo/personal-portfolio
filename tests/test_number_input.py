"""The ONE shared input parser (app.number_input) through every form endpoint that takes numbers."""
import importlib
import re
from decimal import Decimal

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

GOOD = [("۱٫۵", Decimal("1.5")), ("1.5", Decimal("1.5")), ("۱۵۰٬۰۰۰", Decimal("150000")),
        ("150,000", Decimal("150000")), ("۱5٠,۰۰0", Decimal("150000")), ("۱۵۰،۰۰۰", Decimal("150000")),
        (" ١٢٫٥ ", Decimal("12.5")), ("1,234.5", Decimal("1234.5"))]
BAD = ["1.234,5", "۱٫۲٫۳", "abc", "1e5", "NaN", "Infinity", "1.5.", "--1", "۱۲x"]


def test_parser_unit():
    from app.number_input import normalize_number_text, parse_decimal_text, parse_int_required, parse_int_text
    for raw, want in GOOD:
        assert parse_decimal_text(raw) == want, raw
    for raw in BAD:
        with pytest.raises(ValueError):
            normalize_number_text(raw)
    assert parse_decimal_text("") is None and parse_decimal_text("  ") is None and parse_decimal_text(None) is None
    assert parse_int_text("۱٬۰۰۰") == 1000 and parse_int_text("") is None
    with pytest.raises(ValueError):
        parse_int_text("۱٫۵")
    with pytest.raises(ValueError):
        parse_int_required("")
    assert parse_int_required("-3") == -3  # sign kept; callers check ranges, like int() did


def test_parse_decimal_keeps_its_semantics():
    from fastapi import HTTPException
    from app.security import parse_decimal
    assert parse_decimal("", field="x") == 0 and parse_decimal(None, field="x") == 0
    assert parse_decimal("۱٫۵", field="x") == Decimal("1.5")
    for raw in ["-1", "−۱", *BAD]:
        with pytest.raises(HTTPException) as e:
            parse_decimal(raw, field="x")
        assert e.value.status_code == 400


def _alice():
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    return db, db.query(User).filter_by(username="alice").one()


EMPTY_ASSETS = {k: "" for k in ("gold_grams", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram",
                                "silver_grams", "btc", "ada", "eth", "sol", "doge", "matic", "usd", "cash_toman")}


@pytest.mark.parametrize("raw,want", GOOD)
def test_every_form_endpoint_parses_the_same(client, no_network, raw, want):
    from app.models import DailySpend, Debt, MonthlyExpense, SpendCategory
    _register(client)
    client.post("/profile", data={**EMPTY_ASSETS, "btc": raw, "cash_toman": raw, "csrf": _csrf(client)})
    client.post("/profile/account", data={"full_name": "", "username": "alice", "mobile": "", "salary_toman": raw,
                                          "current_password": "", "new_password": "", "csrf": _csrf(client)})
    client.post("/profile/debts", data={"title": "وام", "monthly_toman": raw, "months_left": "۱۲", "due_year": "۱۴۰۵",
                                        "due_month": "۷", "due_day": "۱۵", "csrf": _csrf(client)})
    client.post("/profile/expenses", data={"title": "اجاره", "amount_toman": raw, "due_day": "۵", "csrf": _csrf(client)})
    client.get("/dashboard?tab=daily")
    db, alice = _alice()
    child = db.query(SpendCategory).filter(SpendCategory.user_id == alice.id, SpendCategory.parent_id.is_not(None)).first()
    parent_id, child_id = child.parent_id, child.id
    db.close()
    # Spends are whole toman (spending v2 spec): a decimal amount is rejected at the field, not rounded.
    spend_raw = raw if want == want.to_integral_value() else "۱۲"
    spend_want = want if want == want.to_integral_value() else Decimal("12")
    client.post("/profile/spends", data={"amount_toman": spend_raw, "year": "۱۴۰۵", "month": "۱", "day": "۱", "parent_id": str(parent_id),
                                         "category_id": str(child_id), "note": "form", "csrf": _csrf(client)})
    assert client.post("/api/sms-spend", json={"amount_toman": raw, "note": "sms"}).status_code == 200
    db, alice = _alice()
    try:
        assert alice.btc == want and alice.cash_toman == want and alice.salary_toman == want
        assert db.query(Debt).filter_by(user_id=alice.id).one().monthly_toman == want
        assert db.query(MonthlyExpense).filter_by(user_id=alice.id).one().amount_toman == want
        amounts = sorted(Decimal(s.amount_toman) for s in db.query(DailySpend).filter_by(user_id=alice.id))
        assert amounts == sorted([want, spend_want])
    finally:
        db.close()


@pytest.mark.parametrize("raw", BAD)
def test_every_form_endpoint_rejects_garbage(client, no_network, raw):
    from app.models import DailySpend, Debt, MonthlyExpense
    _register(client)
    client.post("/profile", data={**EMPTY_ASSETS, "btc": "۲", "csrf": _csrf(client)})
    client.post("/profile", data={**EMPTY_ASSETS, "btc": raw, "csrf": _csrf(client)})
    client.post("/profile/debts", data={"title": "وام", "monthly_toman": raw, "months_left": "۱۲", "due_year": "۱۴۰۵",
                                        "due_month": "۷", "due_day": "۱۵", "csrf": _csrf(client)})
    client.post("/profile/expenses", data={"title": "اجاره", "amount_toman": raw, "due_day": "۵", "csrf": _csrf(client)})
    assert client.post("/api/sms-spend", json={"amount_toman": raw}).status_code == 400
    db, alice = _alice()
    try:
        assert alice.btc == Decimal("2")
        assert db.query(Debt).count() == 0 and db.query(MonthlyExpense).count() == 0 and db.query(DailySpend).count() == 0
    finally:
        db.close()


def test_int_fields_accept_both_digit_styles_and_reject_fractions(client, no_network):
    from app.models import Debt, MonthlyExpense
    _register(client)
    client.post("/profile/debts", data={"title": "a", "monthly_toman": "۱۰۰", "months_left": "۱٫۵", "due_year": "1405",
                                        "due_month": "7", "due_day": "15", "csrf": _csrf(client)})
    client.post("/profile/debts", data={"title": "b", "monthly_toman": "100", "months_left": "1۲", "due_year": "۱۴۰۵",
                                        "due_month": "٧", "due_day": "15", "csrf": _csrf(client)})
    client.post("/profile/expenses", data={"title": "c", "amount_toman": "100", "due_day": "٥", "csrf": _csrf(client)})
    db, alice = _alice()
    try:
        debts = db.query(Debt).filter_by(user_id=alice.id).all()
        assert [(d.title, d.months_left, d.due_month) for d in debts] == [("b", 12, 7)]
        assert db.query(MonthlyExpense).one().due_day == 5
    finally:
        db.close()


def test_admin_price_uses_shared_parser(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import MarketPrice, User
    from app.security import hash_password
    import sys

    async def _noop(*a, **k):
        return None
    for name, mod in list(sys.modules.items()):  # no live price fetch may overwrite the row under test
        if name.startswith("app."):
            for attr in ("fetch_chande_prices", "refresh_market_prices_for_user", "refresh_prices_and_snapshot_user"):
                if hasattr(mod, attr):
                    monkeypatch.setattr(mod, attr, _noop)
    db = SessionLocal(); db.add(User(username="boss", password_hash=hash_password("password123"))); db.commit(); db.close()
    for mod in ("app.security", "app.admin_users", "app.db_admin", "app.config"):
        m = importlib.import_module(mod)
        if hasattr(m, "ADMIN_USERNAMES"):
            monkeypatch.setattr(m, "ADMIN_USERNAMES", frozenset({"boss"}))
    client.post("/login", data={"username": "boss", "password": "password123", "csrf": _csrf(client, "/login")})
    from datetime import datetime, timezone
    db = SessionLocal()
    db.merge(MarketPrice(symbol="btc", price_toman=Decimal("1"), fetched_at=datetime.now(timezone.utc)))
    db.commit(); db.close()
    client.post("/admin/db/market-prices/btc", data={"price_toman": "۷٬۲۰۰٬۰۰۰٬۰۰۰٫۵", "fetched_at": "",
                                                     "csrf": _csrf(client, "/admin")})
    db = SessionLocal()
    try:
        assert db.get(MarketPrice, "btc").price_toman == Decimal("7200000000.5")
    finally:
        db.close()


def _form_fields(html: str, action: str) -> dict:
    form = re.search(rf'<form method="post" action="{re.escape(action)}"[^>]*>(.*?)</form>', html, re.S).group(1)
    return {m.group(1): m.group(2) for m in re.finditer(r'<input[^>]*\bname="([^"]+)"[^>]*\bvalue="([^"]*)"', form)}


def test_unchanged_profile_resubmit_keeps_every_value(client, no_network):
    """Seed holdings, GET the profile, re-submit both forms exactly as rendered: nothing may change."""
    from app.db import SessionLocal
    from app.models import User
    _register(client)
    seeded = {"ada": "0.12345678", "gold_grams": "12.5", "cash_toman": "18500000000", "btc": "0.00000001",
              "eth": "1.23456789", "usd": "3249.45", "coin_emami": "3", "silver_grams": "1000.0001",
              "salary_toman": "45000000.5"}
    db, alice = _alice()
    for k, v in seeded.items():
        setattr(alice, k, Decimal(v))
    db.commit(); db.close()

    def snapshot():
        db = SessionLocal()
        u = db.query(User).filter_by(username="alice").one()
        out = {k: Decimal(getattr(u, k)) for k in (*EMPTY_ASSETS, "salary_toman")}
        db.close()
        return out

    before = snapshot()
    html = client.get("/assets").text  # Phase 1: the assets form lives on /assets, still posting to /profile
    assets = _form_fields(html, "/profile")
    assert assets["ada"] == "۰٫۱۲۳۴۵۶۷۸" and assets["gold_grams"] == "۱۲٫۵"
    assert assets["btc"] == "۰٫۰۰۰۰۰۰۰۱" and assets["cash_toman"] == "۱۸٬۵۰۰٬۰۰۰٬۰۰۰"
    assert client.post("/profile", data=assets).status_code == 200
    account = _form_fields(client.get("/profile").text, "/profile/account")
    assert account["salary_toman"] == ""  # privacy mode: stored salary never in the form; empty keeps it
    client.post("/profile/account", data={**account, "current_password": "", "new_password": ""})
    assert snapshot() == before
    assert snapshot()["ada"] == Decimal("0.12345678")
