"""Phase 6 item 6: loan payment history (`debt_payments`), soft-delete (`debts.deleted_at`), guarded undo."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import jdatetime
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.test_debts_v2 import P, _csrf, _debt, _register, _seed, clock  # noqa: F401
from tests.test_holdings import no_network  # noqa: F401


def _set_tehran_date(monkeypatch, jy: int, jm: int, jd: int):
    import app.formatting as fmt

    g = jdatetime.date(jy, jm, jd).togregorian()
    state = {"dt": datetime(g.year, g.month, g.day, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(fmt, "_utcnow", lambda: state["dt"])
    return state


def _payments_db(debt_id: int) -> list[tuple]:
    from app.db import SessionLocal
    from app.models import DebtPayment

    with SessionLocal() as db:
        rows = (
            db.query(DebtPayment)
            .filter(DebtPayment.debt_id == debt_id)
            .order_by(DebtPayment.id.asc())
            .all()
        )
        return [
            (
                r.id,
                r.period_jy,
                r.period_jm,
                Decimal(r.amount_toman),
                r.paid_on,
                r.before_months_left,
                r.before_due_year,
                r.before_due_month,
                r.before_due_day,
                r.before_last_paid_on,
                r.kind,
            )
            for r in rows
        ]


def test_pay_creates_history_row_and_returns_newest_first(client, no_network, monkeypatch):
    from app.db import SessionLocal
    from app.models import Debt

    _set_tehran_date(monkeypatch, 1405, 7, 28)  # ۲۸ مهر ۱۴۰۵ -> 2026-10-20
    _register(client)
    (new_id, old_id) = _seed([
        ("روز ۳۱", 1_250_000, 4, 1405, 6, 31),
        ("قدیمی", 500_000, 3, 1405, 7, 10),
    ])
    with SessionLocal() as db:
        old_loan = db.get(Debt, old_id)
        old_loan.created_at = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        db.commit()

    csrf = _csrf(client, P)
    headers = {"Accept": "application/json"}

    # Pre-release loan with no rows yet -> note_before shown.
    r_old = client.get(f"/api/debts/{old_id}/payments")
    assert r_old.status_code == 200
    assert r_old.json() == {
        "ok": True,
        "debt_id": old_id,
        "count": 0,
        "note_before": "پرداخت‌های قبل از ۴ آذر ۱۴۰۵ ثبت نشده‌اند.",
        "payments": [],
    }

    # First payment: pays شهریور (6) on ۲۸ مهر ۱۴۰۵.
    r1 = client.post(f"/profile/debts/{new_id}/paid", data={"expect": "4", "csrf": csrf}, headers=headers)
    assert r1.status_code == 200 and r1.json()["ok"] is True
    p1_id = r1.json()["payment_id"]

    # Second payment same day: pays مهر (7) on ۲۸ مهر ۱۴۰۵.
    r2 = client.post(f"/profile/debts/{new_id}/paid", data={"expect": "3", "csrf": csrf}, headers=headers)
    assert r2.status_code == 200 and r2.json()["ok"] is True
    p2_id = r2.json()["payment_id"]

    hist = client.get(f"/api/debts/{new_id}/payments")
    assert hist.status_code == 200
    assert "no-store" in hist.headers.get("cache-control", "")
    body = hist.json()
    assert body["count"] == 2
    assert body["note_before"] is None
    assert [p["id"] for p in body["payments"]] == [p2_id, p1_id]
    assert body["payments"][0]["period_label"] == "قسط مهر"
    assert body["payments"][0]["amount_label"] == "۱٬۲۵۰٬۰۰۰"
    assert body["payments"][0]["paid_on"] == "2026-10-20"
    assert body["payments"][0]["paid_on_jalali"] == "۲۸ مهر ۱۴۰۵"
    assert body["payments"][0]["kind"] == "full"
    assert body["payments"][0]["can_undo"] is True
    assert body["payments"][1]["period_label"] == "قسط شهریور"
    assert body["payments"][1]["can_undo"] is False  # only newest row can be undone

    db_rows = _payments_db(new_id)
    assert len(db_rows) == 2
    assert db_rows[0][5:10] == (4, 1405, 6, 31, None)
    assert db_rows[1][5:10] == (3, 1405, 7, 31, date(2026, 10, 20))


def test_stale_expect_409_writes_no_payment_row(client, no_network, clock):
    _register(client)
    (debt_id,) = _seed([("وام", 900_000, 3, 1405, 7, 15)])
    csrf = _csrf(client, P)
    r = client.post(
        f"/profile/debts/{debt_id}/paid",
        data={"expect": "2", "csrf": csrf},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 409
    assert _payments_db(debt_id) == []
    assert _debt(debt_id) == (3, 1405, 7, 15)


def test_undo_across_devices_restores_state_and_last_paid_on(client, no_network, monkeypatch):
    from app.db import SessionLocal
    from app.models import Debt

    _set_tehran_date(monkeypatch, 1405, 7, 28)  # 2026-10-20
    _register(client, "device_user")
    (debt_id,) = _seed([("چنددستگاه", 750_000, 5, 1405, 7, 31)], username="device_user")
    with SessionLocal() as db:
        d = db.get(Debt, debt_id)
        d.last_paid_on = date(2026, 9, 21)  # pre-0013 previous payment date
        db.commit()

    csrf = _csrf(client, P)
    r1 = client.post(
        f"/profile/debts/{debt_id}/paid",
        data={"expect": "5", "csrf": csrf},
        headers={"Accept": "application/json"},
    )
    assert r1.status_code == 200
    pid = r1.json()["payment_id"]

    # Simulate a second device: fresh cookies/session (no `debt_undo` in session).
    client.cookies.clear()
    login_csrf = _csrf(client, "/login")
    client.post("/login", data={"username": "device_user", "password": "password123", "csrf": login_csrf})
    csrf2 = _csrf(client, P)
    r_undo = client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": str(pid), "csrf": csrf2},
        headers={"Accept": "application/json"},
    )
    assert r_undo.status_code == 200 and r_undo.json()["ok"] is True
    assert _payments_db(debt_id) == []
    with SessionLocal() as db:
        d = db.get(Debt, debt_id)
        assert (d.months_left, d.due_year, d.due_month, d.due_day) == (5, 1405, 7, 31)
        assert d.last_paid_on == date(2026, 9, 21)


def test_undo_enforces_newest_row_only_409(client, no_network, monkeypatch):
    _set_tehran_date(monkeypatch, 1405, 7, 28)
    _register(client)
    (debt_id,) = _seed([("دوبار", 600_000, 4, 1405, 7, 10)])
    csrf = _csrf(client, P)
    headers = {"Accept": "application/json"}

    p1 = client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "4", "csrf": csrf}, headers=headers).json()["payment_id"]
    p2 = client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "3", "csrf": csrf}, headers=headers).json()["payment_id"]

    # Older row p1 cannot be undone while p2 exists -> 409.
    r_old = client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": str(p1), "csrf": csrf},
        headers=headers,
    )
    assert r_old.status_code == 409
    assert _debt(debt_id) == (2, 1405, 9, 10)
    assert len(_payments_db(debt_id)) == 2

    # Non-numeric payment_id -> 409.
    r_bad = client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": "abc", "csrf": csrf},
        headers=headers,
    )
    assert r_bad.status_code == 409

    # Newest row p2 succeeds; p1 then becomes newest and can be undone too.
    r_new = client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": str(p2), "csrf": csrf},
        headers=headers,
    )
    assert r_new.status_code == 200
    assert _debt(debt_id) == (3, 1405, 8, 10)
    hist = client.get(f"/api/debts/{debt_id}/payments").json()
    assert [p["id"] for p in hist["payments"]] == [p1]
    assert hist["payments"][0]["can_undo"] is True

    # Undo p1, then third undo -> 409.
    assert client.post(f"/profile/debts/{debt_id}/unpaid", data={"payment_id": str(p1), "csrf": csrf}, headers=headers).status_code == 200
    assert client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": csrf}, headers=headers).status_code == 409


def test_undo_enforces_same_jalali_month_only_409(client, no_network, monkeypatch):
    state = _set_tehran_date(monkeypatch, 1405, 7, 28)  # ۲۸ مهر ۱۴۰۵
    _register(client)
    (debt_id,) = _seed([("ماه‌بعد", 800_000, 4, 1405, 7, 20)])
    csrf = _csrf(client, P)
    headers = {"Accept": "application/json"}

    pid = client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "4", "csrf": csrf}, headers=headers).json()["payment_id"]

    # Roll clock to 1 Aban 1405 (different Jalali month).
    aban_1 = jdatetime.date(1405, 8, 1).togregorian()
    state["dt"] = datetime(aban_1.year, aban_1.month, aban_1.day, 12, 0, tzinfo=timezone.utc)

    hist = client.get(f"/api/debts/{debt_id}/payments").json()
    assert hist["payments"][0]["can_undo"] is False

    r_no_pid = client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": csrf}, headers=headers)
    assert r_no_pid.status_code == 409
    r_with_pid = client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": str(pid), "csrf": csrf},
        headers=headers,
    )
    assert r_with_pid.status_code == 409
    assert _debt(debt_id) == (3, 1405, 8, 20)
    assert len(_payments_db(debt_id)) == 1


def test_undo_409_when_debt_manually_edited_after_payment(client, no_network, monkeypatch):
    _set_tehran_date(monkeypatch, 1405, 7, 28)
    _register(client)
    (debt_id,) = _seed([("ویرایش", 500_000, 4, 1405, 7, 15)])
    csrf = _csrf(client, P)
    headers = {"Accept": "application/json"}

    pid = client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "4", "csrf": csrf}, headers=headers).json()["payment_id"]

    # Manually edit the loan's months_left from 3 to 6.
    r_edit = client.post(
        f"/profile/debts/{debt_id}",
        data={
            "title": "ویرایش",
            "monthly_toman": "500000",
            "months_left": "6",
            "due_year": "1405",
            "due_month": "8",
            "due_day": "15",
            "csrf": csrf,
        },
        headers=headers,
    )
    assert r_edit.status_code == 200

    hist = client.get(f"/api/debts/{debt_id}/payments").json()
    assert hist["payments"][0]["can_undo"] is False
    assert client.post(
        f"/profile/debts/{debt_id}/unpaid",
        data={"payment_id": str(pid), "csrf": csrf},
        headers=headers,
    ).status_code == 409


def test_soft_delete_preserves_payments_and_excludes_loan_everywhere(client, no_network, monkeypatch):
    from app.db import SessionLocal
    from app.due_reminders import pending
    from app.expenses import monthly_view
    from app.mcp_http import _debts, _monthly_left
    from app.models import Debt, DebtPayment, DueReminder, User

    _set_tehran_date(monkeypatch, 1405, 7, 28)
    _register(client, "other")
    (other_id,) = _seed([("وام دیگری", 300_000, 2, 1405, 7, 29)], username="other")
    other_csrf = _csrf(client, P)
    client.post(f"/profile/debts/{other_id}/paid", data={"expect": "2", "csrf": other_csrf})
    client.post("/logout", data={"csrf": other_csrf})

    _register(client, "owner")
    (del_id, keep_id) = _seed(
        [
            ("حذفی", 2_000_000, 5, 1405, 7, 29),
            ("مانده", 1_000_000, 3, 1405, 7, 29),
        ],
        salary=10_000_000,
        username="owner",
    )
    csrf = _csrf(client, P)
    headers = {"Accept": "application/json"}
    client.post(f"/profile/debts/{del_id}/paid", data={"expect": "5", "csrf": csrf}, headers=headers)
    client.post(f"/profile/debts/{del_id}/paid", data={"expect": "4", "csrf": csrf}, headers=headers)
    assert len(_payments_db(del_id)) == 2

    with SessionLocal() as db:
        owner = db.query(User).filter(User.username == "owner").one()
        db.add(DueReminder(user_id=owner.id, debt_id=del_id, kind="upcoming", due_date="1405/09/29"))
        db.commit()

    # Soft-delete `del_id`
    r_del = client.post(f"/profile/debts/{del_id}/delete", data={"csrf": csrf}, headers=headers)
    assert r_del.status_code == 200 and r_del.json()["ok"] is True

    # Debt row and both DebtPayment rows stay in DB; reminder row is cleared.
    with SessionLocal() as db:
        deleted_row = db.get(Debt, del_id)
        assert deleted_row is not None and deleted_row.deleted_at is not None
        assert db.query(DebtPayment).filter(DebtPayment.debt_id == del_id).count() == 2
        assert db.query(DueReminder).filter(DueReminder.debt_id == del_id).count() == 0

        owner = db.query(User).filter(User.username == "owner").one()
        assert monthly_view(db, owner)["installment_month_label"] == "۱٬۰۰۰٬۰۰۰"
        assert [d["id"] for d in _debts(db, owner)["debts"]] == [keep_id]
        assert Decimal(str(_debts(db, owner)["total_toman"])) == Decimal("3000000")
        left = _monthly_left(db, owner)
        assert Decimal(str(left.get("installments_toman", left.get("installment_toman")))) == Decimal("1000000")
        # pending() defense-in-depth skips deleted loans too
        all_owner_debts = db.query(Debt).filter(Debt.user_id == owner.id).all()
        assert [d.id for d, _, _, _ in pending(all_owner_debts, jdatetime.date(1405, 7, 28), 2)] == [keep_id]

    # Excluded from web/API endpoints and returns 404 on direct debt actions.
    debts_html = client.get("/profile?tab=debts").text
    assert "حذفی" not in debts_html and "مانده" in debts_html
    dash_html = client.get("/dashboard").text
    assert "حذفی" not in dash_html
    assert [d["id"] for d in client.get("/api/debts").json()["debts"]] == [keep_id]
    assert client.get("/api/salary").json()["left"] == "۹٬۰۰۰٬۰۰۰"
    assert client.get(f"/api/debts/{del_id}/payments").status_code == 404
    assert client.post(f"/profile/debts/{del_id}/paid", data={"expect": "3", "csrf": csrf}, headers=headers).status_code == 404
    assert client.post(f"/profile/debts/{del_id}/unpaid", data={"csrf": csrf}, headers=headers).status_code == 404
    assert client.post(f"/profile/debts/{del_id}/delete", data={"csrf": csrf}, headers=headers).status_code == 404

    # Other user's debt and payments are untouched.
    assert len(_payments_db(other_id)) == 1


def test_payments_api_auth_and_ownership(client, no_network, clock):
    _register(client, "alice")
    (alice_debt,) = _seed([("آلیس", 400_000, 3, 1405, 8, 1)], username="alice")
    csrf_a = _csrf(client, P)
    client.post(f"/profile/debts/{alice_debt}/paid", data={"expect": "3", "csrf": csrf_a})
    client.post("/logout", data={"csrf": csrf_a})

    # Logged out -> 401 JSON.
    r_anon = client.get(f"/api/debts/{alice_debt}/payments")
    assert r_anon.status_code == 401 and "no-store" in r_anon.headers.get("cache-control", "")

    # Another user -> 404 JSON on payments GET and /unpaid, and cannot mutate.
    _register(client, "mallory")
    csrf_m = _csrf(client, P)
    assert client.get(f"/api/debts/{alice_debt}/payments").status_code == 404
    assert client.post(
        f"/profile/debts/{alice_debt}/unpaid",
        data={"csrf": csrf_m},
        headers={"Accept": "application/json"},
    ).status_code == 404
    assert client.post(f"/profile/debts/{alice_debt}/unpaid", data={}).status_code == 400  # no CSRF
    assert len(_payments_db(alice_debt)) == 1


def test_migration_0013_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "copy0013.sqlite"
    url = f"sqlite:///{db_path}"
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "app/migrations"))

    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["0013_debt_payments"]

    engine = create_engine(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0012_monthly_expense_paid")
        conn.execute(text(
            "INSERT INTO debts (user_id, title, monthly_toman, months_left, due_year, due_month, due_day, created_at) "
            "VALUES (1, 'وام مسکن', 5000000, 12, 1405, 8, 1, '2026-11-25 12:00:00')"
        ))

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # idempotent
        insp = inspect(conn)
        assert "deleted_at" in {c["name"] for c in insp.get_columns("debts")}
        assert "debt_payments" in insp.get_table_names()
        dp_cols = {c["name"] for c in insp.get_columns("debt_payments")}
        assert {
            "id", "debt_id", "user_id", "paid_on", "amount_toman", "kind",
            "period_jy", "period_jm", "before_months_left", "before_due_year",
            "before_due_month", "before_due_day", "before_last_paid_on", "created_at",
        } <= dp_cols
        fks = insp.get_foreign_keys("debt_payments")
        debt_fk = next(fk for fk in fks if fk["referred_table"] == "debts")
        assert (debt_fk.get("options") or {}).get("ondelete") is None
        row = conn.execute(text("SELECT title, deleted_at FROM debts")).fetchone()
        assert tuple(row) == ("وام مسکن", None)

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0012_monthly_expense_paid")
        insp_after = inspect(conn)
        assert "debt_payments" not in insp_after.get_table_names()
        assert "deleted_at" not in {c["name"] for c in insp_after.get_columns("debts")}
        row = conn.execute(text("SELECT title, months_left FROM debts")).fetchone()
        assert tuple(row) == ("وام مسکن", 12)

    engine.dispose()
