"""Due reminders: fake clock, mocked push (no real Firebase), once per instalment, Jalali, no amounts."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jdatetime
import pytest

TEHRAN_NOON = timedelta(hours=8, minutes=30)  # 12:00 Asia/Tehran in UTC


def _utc_noon(jy, jm, jd, hour_shift=0):
    g = jdatetime.date(jy, jm, jd).togregorian()
    return datetime(g.year, g.month, g.day, tzinfo=timezone.utc) + TEHRAN_NOON + timedelta(hours=hour_shift)


class FakePush:
    def __init__(self, delivered=1):
        self.calls, self.delivered = [], delivered

    def __call__(self, db, user_id, *, title, body, data=None):
        self.calls.append({"user_id": user_id, "title": title, "body": body, "data": data})
        return self.delivered


@pytest.fixture()
def db(client):
    from app.db import SessionLocal
    from app.models import User

    s = SessionLocal()
    s.add(User(id=1, username="fake_due", password_hash="h"))
    s.commit()
    yield s
    s.close()


def _debt(db, title="وام فیک", months=5, y=1405, m=8, d=20, amount="12345678"):
    from app.models import Debt

    debt = Debt(user_id=1, title=title, monthly_toman=Decimal(amount), months_left=months, due_year=y, due_month=m, due_day=d)
    db.add(debt)
    db.commit()
    return debt


def _run(db, now, push, monkeypatch=None):
    from app.due_reminders import send_due_reminders

    return send_due_reminders(db, now=now, push=push)


def test_sent_three_days_before_once_with_jalali_and_no_amount(db, monkeypatch):
    monkeypatch.delenv("DUE_REMINDER_DAYS", raising=False)
    _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 16), push) == 0  # 4 days before: too early
    assert _run(db, _utc_noon(1405, 8, 17), push) == 1  # 3 days before
    body = push.calls[0]["body"]
    assert "۱۴۰۵/۰۸/۲۰" in body and "۳ روز دیگر" in body and "وام فیک" in body
    for amount in ("12345678", "۱۲٬۳۴۵٬۶۷۸", "۱۲,۳۴۵,۶۷۸", "۱۲۳۴۵۶۷۸", "تومان"):
        assert amount not in body + push.calls[0]["title"]
    # later hours and days before the due date: never again
    for day in (17, 18, 19, 20):
        for shift in (0, 3):
            assert _run(db, _utc_noon(1405, 8, day, shift), push) == 0
    assert len(push.calls) == 1


def test_next_instalment_after_payment_gets_its_own_reminder(db):
    debt = _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 18), push) == 1
    debt.months_left, debt.due_month = 4, 9  # paid: next one a month on
    db.commit()
    assert _run(db, _utc_noon(1405, 9, 17), push) == 1
    assert "۱۴۰۵/۰۹/۲۰" in push.calls[-1]["body"]


def test_finished_loan_is_skipped(db):
    _debt(db, months=0)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 19), push) == 0
    assert _run(db, _utc_noon(1405, 8, 25), push) == 0 and push.calls == []


def test_overdue_gets_one_separate_notice(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 22), push) == 1  # never got the upcoming one: only the overdue notice
    assert push.calls[0]["data"]["type"] == "debt_overdue" and "پرداخت نشده" in push.calls[0]["body"]
    for day in (23, 24, 30):
        assert _run(db, _utc_noon(1405, 8, day), push) == 0
    assert len(push.calls) == 1


def test_upcoming_then_overdue_is_two_notices_total(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 18), push) == 1
    assert _run(db, _utc_noon(1405, 8, 21), push) == 1
    assert [c["data"]["type"] for c in push.calls] == ["debt_upcoming", "debt_overdue"]


def test_not_delivered_is_retried_then_sent_once(db):
    _debt(db)
    failing = FakePush(delivered=0)
    assert _run(db, _utc_noon(1405, 8, 18), failing) == 0
    ok = FakePush()
    assert _run(db, _utc_noon(1405, 8, 18, 1), ok) == 1
    assert _run(db, _utc_noon(1405, 8, 18, 2), ok) == 0


def test_push_exception_does_not_crash_or_record(db):
    _debt(db)

    def boom(*a, **k):
        raise RuntimeError("fcm down")

    assert _run(db, _utc_noon(1405, 8, 18), boom) == 0
    assert _run(db, _utc_noon(1405, 8, 18), FakePush()) == 1


def test_quiet_hours(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 18, -5), push) == 0  # 07:00 Tehran
    assert _run(db, _utc_noon(1405, 8, 18, 10), push) == 0  # 22:00 Tehran
    assert push.calls == []


def test_days_configurable_by_env(db, monkeypatch):
    monkeypatch.setenv("DUE_REMINDER_DAYS", "1")
    _debt(db)
    push = FakePush()
    assert _run(db, _utc_noon(1405, 8, 18), push) == 0
    assert _run(db, _utc_noon(1405, 8, 19), push) == 1 and "فردا" in push.calls[0]["body"]


def test_firebase_not_configured_sends_nothing(db):
    from app.due_reminders import send_due_reminders

    _debt(db)
    assert send_due_reminders(db, now=_utc_noon(1405, 8, 18)) == 0  # default push: Firebase admin not set


def test_hourly_job_calls_reminders(monkeypatch, client):
    import asyncio

    import app.due_reminders as dr
    import app.jobs as jobs

    called = []
    monkeypatch.setattr(dr, "send_due_reminders", lambda db: called.append(1) or 0)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(jobs, "fetch_and_store_prices", _noop)
    monkeypatch.setattr(jobs, "refresh_all_sanjeh_cars", _noop)
    asyncio.run(jobs.run_hourly_job(take_snapshots=False))
    assert called == [1]


def test_migration_0006_adds_only_the_table_and_downgrade_drops_it(tmp_path):
    import sqlite3

    from tests.test_sanjeh_migration import _alembic, _dump, _fake_db_at_0003

    db = _fake_db_at_0003(tmp_path)
    _alembic(db, "upgrade", "0004_sanjeh_status")
    before = _dump(db)
    _alembic(db, "upgrade", "0006_due_reminders")
    _alembic(db, "stamp", "0004_sanjeh_status")
    _alembic(db, "upgrade", "0006_due_reminders")  # table already there: no-op
    after = _dump(db)
    assert after.pop("due_reminders") == (["id", "user_id", "debt_id", "kind", "due_date", "sent_at"], [])
    assert after == before
    _alembic(db, "downgrade", "0004_sanjeh_status")
    tables = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}
    assert "due_reminders" not in tables and _dump(db) == before
