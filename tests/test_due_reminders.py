"""Due reminders: fake clock, mocked push (no real Firebase), once per instalment, Jalali, no amounts."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jdatetime
import pytest

from tests.test_holdings import no_network  # noqa: F401

TEHRAN_EVENING = timedelta(hours=16, minutes=30)  # 20:00 Asia/Tehran in UTC (UTC+3:30, no DST)


def _evening(jy, jm, jd, hour_shift=0, minute_shift=0):
    """20:00 Asia/Tehran on a Jalali day (as a UTC datetime), shifted by whole hours / minutes."""
    g = jdatetime.date(jy, jm, jd).togregorian()
    return datetime(g.year, g.month, g.day, tzinfo=timezone.utc) + TEHRAN_EVENING + timedelta(hours=hour_shift,
                                                                                               minutes=minute_shift)


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


def test_sent_one_day_before_once_with_jalali_and_no_amount(db, monkeypatch):
    monkeypatch.delenv("DUE_REMINDER_DAYS", raising=False)
    _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 18), push) == 0  # 2 days before: too early
    assert _run(db, _evening(1405, 8, 19), push) == 1  # 1 day before
    body = push.calls[0]["body"]
    assert "۱۴۰۵/۰۸/۲۰" in body and "فردا" in body and "وام فیک" in body
    for amount in ("12345678", "۱۲٬۳۴۵٬۶۷۸", "۱۲,۳۴۵,۶۷۸", "۱۲۳۴۵۶۷۸", "تومان"):
        assert amount not in body + push.calls[0]["title"] + repr(push.calls[0]["data"])
    # later hours and the due day itself: never again
    for day in (19, 20):
        for shift in (0, 3):
            assert _run(db, _evening(1405, 8, day, shift), push) == 0
    assert len(push.calls) == 1


def test_next_instalment_after_payment_gets_its_own_reminder(db):
    debt = _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 19), push) == 1
    debt.months_left, debt.due_month = 4, 9  # paid: next one a month on
    db.commit()
    assert _run(db, _evening(1405, 9, 19), push) == 1
    assert "۱۴۰۵/۰۹/۲۰" in push.calls[-1]["body"]


def test_finished_loan_is_skipped(db):
    _debt(db, months=0)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 19), push) == 0
    assert _run(db, _evening(1405, 8, 25), push) == 0 and push.calls == []


def test_overdue_gets_one_separate_notice(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 22), push) == 1  # never got the upcoming one: only the overdue notice
    assert push.calls[0]["data"]["type"] == "debt_overdue" and "پرداخت نشده" in push.calls[0]["body"]
    for day in (23, 24, 30):
        assert _run(db, _evening(1405, 8, day), push) == 0
    assert len(push.calls) == 1


def test_upcoming_then_overdue_is_two_notices_total(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 19), push) == 1
    assert _run(db, _evening(1405, 8, 21), push) == 1
    assert [c["data"]["type"] for c in push.calls] == ["debt_upcoming", "debt_overdue"]


def test_not_delivered_is_retried_then_sent_once(db):
    _debt(db)
    failing = FakePush(delivered=0)
    assert _run(db, _evening(1405, 8, 19), failing) == 0
    ok = FakePush()
    assert _run(db, _evening(1405, 8, 19, 1), ok) == 1
    assert _run(db, _evening(1405, 8, 19, 2), ok) == 0


def test_push_exception_does_not_crash_or_record(db):
    _debt(db)

    def boom(*a, **k):
        raise RuntimeError("fcm down")

    assert _run(db, _evening(1405, 8, 19), boom) == 0
    assert _run(db, _evening(1405, 8, 19), FakePush()) == 1


def test_outside_the_evening_window_sends_nothing(db):
    _debt(db)
    push = FakePush()
    for shift in (-13, -11, -8, -1):  # 07:00, 09:00, 12:00, 19:00 Tehran
        assert _run(db, _evening(1405, 8, 19, shift), push) == 0
    assert _run(db, _evening(1405, 8, 19, 0, -1), push) == 0  # 19:59
    assert _run(db, _evening(1405, 8, 19, 2), push) == 0  # 22:00
    assert _run(db, _evening(1405, 8, 19, 3, 59), push) == 0  # 23:59
    assert push.calls == []


def test_window_uses_tehran_time_not_server_time():
    from zoneinfo import ZoneInfo

    from app.due_reminders import in_send_window

    tehran = ZoneInfo("Asia/Tehran")
    assert in_send_window(datetime(2026, 11, 10, 20, 0, tzinfo=tehran))
    assert in_send_window(datetime(2026, 11, 10, 21, 59, tzinfo=tehran))
    assert not in_send_window(datetime(2026, 11, 10, 19, 59, tzinfo=tehran))
    assert not in_send_window(datetime(2026, 11, 10, 22, 0, tzinfo=tehran))
    assert in_send_window(datetime(2026, 11, 10, 16, 30, tzinfo=timezone.utc))  # 20:00 Tehran
    assert in_send_window(datetime(2026, 11, 10, 16, 30))  # naive = UTC
    assert not in_send_window(datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc))  # 23:30 Tehran
    assert in_send_window(datetime(2026, 11, 10, 12, 0, tzinfo=ZoneInfo("America/New_York")))  # 20:30 Tehran


def test_evening_send_then_catch_up_then_next_day(db):
    _debt(db)  # due 1405/08/20, default 1 day before
    push = FakePush()
    assert _run(db, _evening(1405, 8, 19, 0, -1), push) == 0  # 19:59
    assert _run(db, _evening(1405, 8, 19), push) == 1  # 20:00 the evening before
    assert "فردا" in push.calls[0]["body"]
    assert _run(db, _evening(1405, 8, 19, 1, 30), push) == 0  # 21:30: already sent, no duplicate
    assert _run(db, _evening(1405, 8, 19, 2), push) == 0  # 22:00
    assert _run(db, _evening(1405, 8, 20), push) == 0  # due day 20:00: upcoming already sent
    assert _run(db, _evening(1405, 8, 21, 0, -1), push) == 0  # 19:59 the day after: not yet
    assert _run(db, _evening(1405, 8, 21), push) == 1  # 20:00: overdue
    assert push.calls[-1]["data"]["type"] == "debt_overdue"
    assert _run(db, _evening(1405, 8, 21, 1, 30), push) == 0
    assert _run(db, _evening(1405, 8, 22), push) == 0
    assert [c["data"]["type"] for c in push.calls] == ["debt_upcoming", "debt_overdue"]


def test_catch_up_at_2130_when_the_2000_run_missed_it(db):
    _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 19, 1, 30), push) == 1  # no run at 20:xx: the 21:xx run sends it
    assert _run(db, _evening(1405, 8, 19, 1, 59), push) == 0
    assert _run(db, _evening(1405, 8, 19, 2), push) == 0 and len(push.calls) == 1


def test_missed_whole_window_waits_for_next_evening(db):
    _debt(db, d=21)
    failing = FakePush(delivered=0)
    assert _run(db, _evening(1405, 8, 20), failing) == 0  # not delivered at 20:00
    assert _run(db, _evening(1405, 8, 20, 1), failing) == 0  # nor at 21:00
    ok = FakePush()
    for shift in (2, 3, 10, 15):  # 22:00 .. 11:00 next morning
        assert _run(db, _evening(1405, 8, 20, shift), ok) == 0
    assert _run(db, _evening(1405, 8, 21), ok) == 1 and "امروز" in ok.calls[0]["body"]  # due day, 20:00


def test_loan_created_after_the_window_sends_next_evening(db):
    push = FakePush()
    assert _run(db, _evening(1405, 8, 18, 2, 30), push) == 0
    _debt(db, d=20, title="دیر ثبت شده")  # added at 22:30, two days before
    assert _run(db, _evening(1405, 8, 18, 3), push) == 0  # 23:00
    assert _run(db, _evening(1405, 8, 19, -8), push) == 0  # noon next day
    assert _run(db, _evening(1405, 8, 19), push) == 1 and "دیر ثبت شده" in push.calls[0]["body"]
    assert _run(db, _evening(1405, 8, 19, 1), push) == 0 and len(push.calls) == 1


def test_default_days_configurable_by_env(db, monkeypatch):
    monkeypatch.setenv("DUE_REMINDER_DAYS", "3")
    _debt(db)
    push = FakePush()
    assert _run(db, _evening(1405, 8, 16), push) == 0
    assert _run(db, _evening(1405, 8, 17), push) == 1 and "۳ روز دیگر" in push.calls[0]["body"]


def test_firebase_not_configured_sends_nothing(db):
    from app.due_reminders import send_due_reminders

    _debt(db)
    assert send_due_reminders(db, now=_evening(1405, 8, 19)) == 0  # default push: Firebase admin not set


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


def test_migration_chain_0004_0005_0006_up_and_down(tmp_path):
    import sqlite3

    from tests.test_sanjeh_migration import _dump, _fake_db_at_0003
    from tests.test_sanjeh_token_encrypt import _alembic, _tokens

    def ok(*args):
        r = _alembic(db, *args)
        assert r.returncode == 0, r.stderr

    def version():
        return sqlite3.connect(db).execute("select version_num from alembic_version").fetchone()[0]

    def tables():
        return {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}

    db = _fake_db_at_0003(tmp_path)
    ok("upgrade", "0004_sanjeh_status")
    before = _dump(db)
    ok("upgrade", "0005_sanjeh_token_encrypt")
    assert version() == "0005_sanjeh_token_encrypt" and _tokens(db)[1].startswith("enc1:")
    assert "due_reminders" not in tables()
    ok("upgrade", "head")
    assert version() == "0008_debt_reminder_days"
    ok("stamp", "0005_sanjeh_token_encrypt")
    ok("upgrade", "head")  # table already there: no-op
    after = _dump(db)
    assert after.pop("due_reminders") == (["id", "user_id", "debt_id", "kind", "due_date", "sent_at"], [])
    ok("downgrade", "0005_sanjeh_token_encrypt")
    assert version() == "0005_sanjeh_token_encrypt" and "due_reminders" not in tables()
    assert _tokens(db)[1].startswith("enc1:")
    ok("downgrade", "0004_sanjeh_status")
    assert version() == "0004_sanjeh_status" and _dump(db) == before


def test_single_alembic_head():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "app" / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0008_debt_reminder_days"]


def _hourly(monkeypatch, **kw):
    import asyncio

    import app.due_reminders as dr
    import app.jobs as jobs

    called = []
    monkeypatch.setattr(dr, "send_due_reminders", lambda db: called.append(1) or 0)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(jobs, "fetch_and_store_prices", _noop)
    monkeypatch.setattr(jobs, "refresh_all_sanjeh_cars", _noop)
    asyncio.run(jobs.run_hourly_job(**kw))
    return called


def test_startup_run_sends_no_reminders_with_scheduler_off(monkeypatch, client):
    import asyncio

    import app.main as main

    seen = []

    async def _fake_job(**kw):
        seen.append(kw)

    monkeypatch.setattr(main, "ENABLE_INTERNAL_SCHEDULER", False)
    monkeypatch.setattr(main, "run_hourly_job", _fake_job)

    async def _boot():
        async with main.lifespan(main.app):
            pass

    asyncio.run(_boot())
    assert seen and all(kw.get("send_reminders") is False for kw in seen)
    assert _hourly(monkeypatch, take_snapshots=False, send_reminders=False) == []


def test_scheduler_run_still_sends_reminders(monkeypatch, client):
    import inspect

    import app.scheduler as scheduler

    assert "send_reminders=False" not in inspect.getsource(scheduler)
    monkeypatch.setattr("app.jobs.create_snapshots", lambda: 0)
    assert _hourly(monkeypatch, take_snapshots=True) == [1]


def test_deleting_loan_deletes_its_reminders(client, no_network):
    from app.db import SessionLocal
    from app.models import Debt, DueReminder
    from tests.test_holdings import _csrf, _register

    _register(client, "fake_del")
    s = SessionLocal()
    from app.models import User

    uid = s.query(User).filter(User.username == "fake_del").one().id
    keep = Debt(user_id=uid, title="نگه", monthly_toman=Decimal("1000"), months_left=3, due_year=1405, due_month=8, due_day=1)
    gone = Debt(user_id=uid, title="حذف", monthly_toman=Decimal("1000"), months_left=3, due_year=1405, due_month=8, due_day=1)
    s.add_all([keep, gone])
    s.flush()
    s.add_all([DueReminder(user_id=uid, debt_id=gone.id, kind="upcoming", due_date="1405/08/01"),
               DueReminder(user_id=uid, debt_id=gone.id, kind="overdue", due_date="1405/08/01"),
               DueReminder(user_id=uid, debt_id=keep.id, kind="upcoming", due_date="1405/08/01")])
    s.commit()
    gone_id, keep_id = gone.id, keep.id
    s.close()
    t = _csrf(client, "/profile?tab=debts")
    client.post(f"/profile/debts/{gone_id}/delete", data={"csrf": t})
    s = SessionLocal()
    assert s.get(Debt, gone_id) is None
    assert s.query(DueReminder).filter(DueReminder.debt_id == gone_id).count() == 0
    assert s.query(DueReminder).filter(DueReminder.debt_id == keep_id).count() == 1
    s.close()
