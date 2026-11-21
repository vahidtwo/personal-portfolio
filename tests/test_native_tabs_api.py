"""POST /profile keeps fields that are not sent, and the read-only JSON mirrors for the native tabs."""
import json
from decimal import Decimal

from tests.test_debts_v2 import _seed, clock  # noqa: F401
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.test_quick_ux_5c import _seed_spends

SALARY = 93_410_000
ENDPOINTS = ("/api/assets", "/api/categories", "/api/spends", "/api/debts", "/api/expenses", "/api/settings")


def _user():
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    return db, db.query(User).filter_by(username="alice").one()


def _hold(**values):
    db, user = _user()
    for key, value in values.items():
        setattr(user, key, Decimal(value))
    db.commit()
    db.close()


def _quantities():
    from app.profile import HOLDING_FORM_FIELDS

    db, user = _user()
    out = {k: Decimal(getattr(user, k) or 0) for k in HOLDING_FORM_FIELDS}
    db.close()
    return out


def test_post_with_one_field_keeps_every_other_holding(client, no_network):
    _register(client)
    _hold(gold_grams="12.5", btc="0.25", cash_toman="41270000")
    r = client.post("/profile", data={"eth": "3", "next": "/assets", "csrf": _csrf(client, "/assets")},
                    follow_redirects=False)
    assert r.status_code == 303
    q = _quantities()
    assert q["eth"] == Decimal("3")
    assert q["gold_grams"] == Decimal("12.5") and q["btc"] == Decimal("0.25") and q["cash_toman"] == Decimal("41270000")


def test_sent_empty_field_still_means_zero(client, no_network):
    _register(client)
    _hold(gold_grams="12.5", btc="0.25")
    client.post("/profile", data={"btc": "", "csrf": _csrf(client, "/assets")})
    q = _quantities()
    assert q["btc"] == 0 and q["gold_grams"] == Decimal("12.5")


def test_invalid_sent_field_saves_nothing_and_unsent_stay(client, no_network):
    _register(client)
    _hold(gold_grams="12.5", btc="2")
    r = client.post("/profile", headers={"Accept": "application/json"},
                    data={"btc": "1.2.3", "eth": "5", "next": "/assets", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 422 and set(r.json()["fields"]) == {"btc"}
    q = _quantities()
    assert q["btc"] == Decimal("2") and q["eth"] == 0 and q["gold_grams"] == Decimal("12.5")


def test_full_web_form_still_saves_every_field(client, no_network):
    from app.profile import HOLDING_FORM_FIELDS

    _register(client)
    _hold(gold_grams="12.5", btc="2")
    data = {k: "" for k in HOLDING_FORM_FIELDS}
    data.update(ada="7", csrf=_csrf(client, "/assets"))
    client.post("/profile", data=data)
    q = _quantities()
    assert q["ada"] == Decimal("7") and q["gold_grams"] == 0 and q["btc"] == 0


def test_cash_keep_marker_keeps_cash(client, no_network):
    _register(client)
    _hold(cash_toman="41270000", btc="1")
    client.post("/profile", data={"cash_toman": "", "cash_toman_keep": "1", "btc": "2",
                                  "csrf": _csrf(client, "/assets")})
    q = _quantities()
    assert q["cash_toman"] == Decimal("41270000") and q["btc"] == Decimal("2")


def test_tab_endpoints_need_login(client):
    for path in ENDPOINTS:
        r = client.get(path)
        assert r.status_code == 401, path
        assert "no-store" in r.headers["cache-control"]


def _seed_all(client):
    _register(client)
    _seed([("وام نمونه", 2_357_000, 12, 1405, 8, 5)], expenses=[("اجاره نمونه", 7_130_000, 1)], salary=SALARY)
    _seed_spends()
    _hold(btc="0.25", gold_grams="12.5", cash_toman="41270000")


def test_no_tab_response_carries_the_salary(client, no_network, clock):
    from app.formatting import format_toman

    _seed_all(client)
    salary_label = format_toman(Decimal(SALARY))
    for path in ENDPOINTS:
        r = client.get(path)
        assert r.status_code == 200, path
        text = json.dumps(r.json(), ensure_ascii=False)
        assert str(SALARY) not in text and salary_label not in text, path
        assert "salary_toman" not in text and '"left"' not in text, path


def test_assets_json(client, no_network):
    _seed_all(client)
    data = client.get("/api/assets").json()
    assert [g["key"] for g in data["groups"]] == ["gold", "fx", "crypto"]
    rows = {r["field"]: r for g in data["groups"] for r in g["rows"]}
    assert rows["btc"]["held"] and rows["btc"]["quantity"] == "0.25"
    assert rows["gold_grams"]["quantity"] == "12.5"
    assert rows["cash_toman"]["quantity"] == "41270000" and rows["cash_toman"]["manual"]
    assert not rows["eth"]["held"] and rows["eth"]["quantity"] == "0"
    assert data["car"]["state"] == "none" and data["car"]["value"] is None
    assert data["empty"] is False
    assert {g["key"]: g["count"] for g in data["groups"]} == {"gold": 1, "fx": 1, "crypto": 1}


def test_assets_json_empty_user(client, no_network):
    _register(client)
    data = client.get("/api/assets").json()
    assert data["empty"] is True and all(g["count"] == 0 for g in data["groups"])


def test_categories_json(client):
    _register(client)
    cats = client.get("/api/categories").json()["categories"]
    assert cats and all(c["children"] for c in cats)
    assert all(c["icon"] and c["color"] for c in cats)


def test_spends_json_month_param(client, no_network, clock):
    from app.formatting import format_toman

    _seed_all(client)
    data = client.get("/api/spends?month=1405-07").json()
    assert (data["year"], data["month"]) == (1405, 7)
    rows = [r for g in data["groups"] for r in g["rows"]]
    assert sorted(r["amount"] for r in rows) == ["1250000", "450000", "99000"]
    assert data["month_label"] == format_toman(Decimal(1_799_000))
    assert data["total_count"] == 3 and data["has_any"] is True
    assert data["top"] and data["top"][0]["share"] == 100
    assert client.get("/api/spends?jy=1405&jm=7").json()["groups"] == data["groups"]
    other = client.get("/api/spends?month=1405-05").json()
    assert other["groups"] == [] and other["has_any"] is True


def test_spends_json_bad_month_falls_back_to_this_month(client, clock):
    _register(client)
    data = client.get("/api/spends?month=abc").json()
    assert data["is_current_month"] is True


def test_debts_and_expenses_json(client, clock):
    from app.formatting import format_toman

    _seed_all(client)
    data = client.get("/api/debts").json()
    assert len(data["debts"]) == 1 and data["active_count"] == 1
    debt = data["debts"][0]
    assert debt["title"] == "وام نمونه" and debt["months_left"] == 12 and debt["monthly"] == "2357000"
    assert debt["reminder_days_before"] == 1
    assert data["summary"]["total_label"] == format_toman(Decimal(2_357_000 * 12))
    assert data["summary"]["expenses_label"] == format_toman(Decimal(7_130_000))
    assert data["next"] and data["next"]["title"] == "وام نمونه"
    exp = client.get("/api/expenses").json()
    assert exp["expenses"][0]["amount"] == "7130000" and exp["expenses"][0]["due_day"] == 1


def test_settings_json(client):
    _register(client)
    data = client.get("/api/settings").json()
    assert data["account"]["username"] == "alice"
    assert data["has_salary"] is False and data["car_connected"] is False
    assert set(data["push"]) == {"server", "devices"}


def test_tab_endpoints_do_not_write(client, no_network, clock):
    from app.db import SessionLocal
    from app.models import DailySpend, Debt, MonthlyExpense

    _seed_all(client)
    client.get("/api/categories")
    before = _quantities()
    db = SessionLocal()
    counts = (db.query(Debt).count(), db.query(MonthlyExpense).count(), db.query(DailySpend).count())
    db.close()
    for path in ENDPOINTS:
        client.get(path)
    db = SessionLocal()
    assert (db.query(Debt).count(), db.query(MonthlyExpense).count(), db.query(DailySpend).count()) == counts
    db.close()
    assert _quantities() == before
