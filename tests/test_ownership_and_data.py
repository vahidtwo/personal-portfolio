"""Guard rails for the refactor: per-user ownership, SMS dedupe, portfolio math."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


def _csrf(client: TestClient, path: str = "/profile") -> str:
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def _register(client: TestClient, username: str) -> None:
    token = _csrf(client, "/register")
    resp = client.post(
        "/register",
        data={"username": username, "password": "password123", "password_confirm": "password123", "csrf": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _logout(client: TestClient) -> None:
    client.post("/logout", data={"csrf": _csrf(client)})


@pytest.fixture()
def victim_rows(client: TestClient):
    """Alice owns one debt, expense, and spend; then Mallory logs in."""
    from app.db import SessionLocal
    from app.models import DailySpend, Debt, MonthlyExpense, SpendCategory, User
    from app.spends import ensure_spend_categories

    _register(client, "alice")
    _logout(client)
    with SessionLocal() as db:
        alice = db.query(User).filter_by(username="alice").one()
        ensure_spend_categories(db, alice)
        cat = db.query(SpendCategory).filter(SpendCategory.user_id == alice.id, SpendCategory.parent_id.isnot(None)).first()
        debt = Debt(user_id=alice.id, title="loan", monthly_toman=Decimal("100"), months_left=3, due_year=1405, due_month=1, due_day=1)
        exp = MonthlyExpense(user_id=alice.id, title="rent", amount_toman=Decimal("200"), due_day=5)
        spend = DailySpend(user_id=alice.id, category_id=cat.id, amount_toman=Decimal("300"), spent_on=date.today(), note="x")
        db.add_all([debt, exp, spend])
        db.commit()
        ids = {"debt": debt.id, "expense": exp.id, "spend": spend.id}
    _register(client, "mallory")
    return ids


def _counts():
    from app.db import SessionLocal
    from app.models import DailySpend, Debt, MonthlyExpense

    with SessionLocal() as db:
        return (
            db.query(Debt).count(),
            db.query(MonthlyExpense).count(),
            db.query(DailySpend).count(),
            [d.title for d in db.query(Debt)],
            [e.title for e in db.query(MonthlyExpense)],
            [str(s.amount_toman) for s in db.query(DailySpend)],
        )


def test_other_user_cannot_edit_or_delete(client: TestClient, victim_rows):
    before = _counts()
    token = _csrf(client)
    attempts = [
        (f"/profile/debts/{victim_rows['debt']}", {"title": "pwned", "monthly_toman": "1", "months_left": "1", "due_year": "1405", "due_month": "1", "due_day": "1"}),
        (f"/profile/debts/{victim_rows['debt']}/delete", {}),
        (f"/profile/expenses/{victim_rows['expense']}", {"title": "pwned", "amount_toman": "1", "due_day": "1"}),
        (f"/profile/expenses/{victim_rows['expense']}/delete", {}),
        (f"/profile/spends/{victim_rows['spend']}", {"amount_toman": "1", "year": "1405", "month": "1", "day": "1", "note": "pwned"}),
        (f"/profile/spends/{victim_rows['spend']}/delete", {}),
    ]
    for path, data in attempts:
        client.post(path, data={**data, "csrf": token}, follow_redirects=False)
    assert _counts() == before


def test_sms_spend_dedupes_by_idempotency_key(client: TestClient):
    _register(client, "smsuser")
    body = {"amount_toman": "125000", "note": "bank", "idempotency_key": "msg-1"}
    first = client.post("/api/sms-spend", json=body).json()
    second = client.post("/api/sms-spend", json=body).json()
    assert first["ok"] and second["ok"]
    assert second.get("duplicate") is True
    assert second["id"] == first["id"]


def test_sms_spend_rejects_bad_amount(client: TestClient):
    _register(client, "smsbad")
    assert client.post("/api/sms-spend", json={"amount_toman": "0"}).status_code == 400
    assert client.post("/api/sms-spend", json={"amount_toman": "abc"}).status_code == 400


def test_portfolio_total_is_sum_of_rows(client: TestClient):
    from app.db import SessionLocal
    from app.models import User
    from app.portfolio import build_portfolio, load_prices

    _register(client, "math")
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="math").one()
        user.cash_toman = Decimal("5000000")
        user.car_toman = Decimal("1000000000")
        db.commit()
        view = build_portfolio(user, load_prices(db))
    assert view.total_toman == sum(r.value_toman for r in view.rows)
    by_key = {r.key: r for r in view.rows}
    assert by_key["cash"].value_toman == Decimal("5000000")
    assert by_key["car"].value_toman == Decimal("1000000000")


def test_owner_can_delete_own_rows(client: TestClient, victim_rows):
    """Positive control: the same requests work for the owner, so the test above is not vacuous."""
    _logout(client)
    token = _csrf(client, "/login")
    client.post("/login", data={"username": "alice", "password": "password123", "csrf": token})
    token = _csrf(client)
    client.post(f"/profile/debts/{victim_rows['debt']}/delete", data={"csrf": token})
    client.post(f"/profile/expenses/{victim_rows['expense']}/delete", data={"csrf": token})
    client.post(f"/profile/spends/{victim_rows['spend']}/delete", data={"csrf": token})
    debts, expenses, spends, *_ = _counts()
    assert (debts, expenses, spends) == (0, 0, 0)


def _login(client: TestClient, username: str) -> None:
    _logout(client)
    client.post("/login", data={"username": username, "password": "password123", "csrf": _csrf(client, "/login")})


def test_owner_can_edit_own_rows(client: TestClient, victim_rows):
    from app.db import SessionLocal
    from app.models import DailySpend, Debt, MonthlyExpense, SpendCategory

    _login(client, "alice")
    token = _csrf(client)
    with SessionLocal() as db:
        spend = db.get(DailySpend, victim_rows["spend"])
        child = db.get(SpendCategory, spend.category_id)
        parent_id, child_id = child.parent_id, child.id
    client.post(f"/profile/debts/{victim_rows['debt']}", data={"title": "loan2", "monthly_toman": "150", "months_left": "2", "due_year": "1405", "due_month": "2", "due_day": "3", "csrf": token})
    client.post(f"/profile/expenses/{victim_rows['expense']}", data={"title": "rent2", "amount_toman": "250", "due_day": "6", "csrf": token})
    client.post(f"/profile/spends/{victim_rows['spend']}", data={"amount_toman": "350", "year": "1405", "month": "1", "day": "1", "parent_id": str(parent_id), "category_id": str(child_id), "note": "y", "csrf": token})
    with SessionLocal() as db:
        debt = db.get(Debt, victim_rows["debt"])
        exp = db.get(MonthlyExpense, victim_rows["expense"])
        spend = db.get(DailySpend, victim_rows["spend"])
        assert (debt.title, debt.monthly_toman, debt.months_left) == ("loan2", Decimal("150"), 2)
        assert (exp.title, exp.amount_toman, exp.due_day) == ("rent2", Decimal("250"), 6)
        assert (spend.amount_toman, spend.note) == (Decimal("350"), "y")


def test_cannot_file_spend_under_another_users_category(client: TestClient, victim_rows):
    from app.db import SessionLocal
    from app.models import DailySpend, SpendCategory, User

    with SessionLocal() as db:
        alice_id = db.query(User).filter_by(username="alice").one().id
        alice_child = db.query(SpendCategory).filter(SpendCategory.user_id == alice_id, SpendCategory.parent_id.isnot(None)).first()
        ids = (alice_child.parent_id, alice_child.id)
    client.post("/profile/spends", data={"amount_toman": "999", "year": "1405", "month": "1", "day": "1", "parent_id": str(ids[0]), "category_id": str(ids[1]), "note": "", "csrf": _csrf(client)})
    with SessionLocal() as db:
        assert db.query(DailySpend).filter(DailySpend.category_id == ids[1], DailySpend.user_id != alice_id).count() == 0


def test_same_idempotency_key_is_per_user(client: TestClient):
    body = {"amount_toman": "5000", "note": "bank", "idempotency_key": "shared-key"}
    _register(client, "smsa")
    a = client.post("/api/sms-spend", json=body).json()
    _logout(client)
    _register(client, "smsb")
    b = client.post("/api/sms-spend", json=body).json()
    assert a["ok"] and b["ok"]
    assert not b.get("duplicate")
    assert a["id"] != b["id"]


def _mcp(client: TestClient, token: str, name: str):
    return client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {}}},
    )


def test_mcp_token_only_sees_own_data_and_revoke_works(client: TestClient, victim_rows):
    from app.db import SessionLocal
    from app.mcp_http import hash_mcp_token
    from app.models import User

    with SessionLocal() as db:
        db.query(User).filter_by(username="alice").one().mcp_token_hash = hash_mcp_token("alice-tok")
        db.query(User).filter_by(username="mallory").one().mcp_token_hash = hash_mcp_token("mallory-tok")
        db.commit()
    assert "loan" in _mcp(client, "alice-tok", "list_debts").text
    assert "loan" not in _mcp(client, "mallory-tok", "list_debts").text
    assert _mcp(client, "wrong-tok", "list_debts").status_code == 401
    client.post("/profile/mcp-token/revoke", data={"csrf": _csrf(client)})
    assert _mcp(client, "mallory-tok", "list_debts").status_code == 401
    assert "loan" in _mcp(client, "alice-tok", "list_debts").text


def test_push_register_stores_token_for_current_user(client: TestClient):
    from app.db import SessionLocal
    from app.models import PushDeviceToken, User

    _register(client, "pushy")
    assert client.post("/api/push/register", json={"token": "tok-123", "platform": "web"}).json()["ok"]
    _logout(client)
    assert client.post("/api/push/register", json={"token": "tok-999"}).status_code == 401
    with SessionLocal() as db:
        uid = db.query(User).filter_by(username="pushy").one().id
        rows = db.query(PushDeviceToken).all()
        assert [(r.user_id, r.token) for r in rows] == [(uid, "tok-123")]
