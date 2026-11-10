"""Per-loan «یادآوری قسط»: NULL = default 1 day, N days, 0 = same day, -1 = off; form, API and migration."""
import json
import re
import shutil
import sqlite3
from decimal import Decimal
from html import unescape

import pytest

from tests.amounts_helper import with_amounts
from tests.test_due_reminders import FakePush, _utc_noon
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

P = "/profile?tab=debts"
JSON = {"Accept": "application/json"}


@pytest.fixture()
def db(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import User

    monkeypatch.delenv("DUE_REMINDER_DAYS", raising=False)
    s = SessionLocal()
    s.add(User(id=1, username="fake_rem", password_hash="h"))
    s.commit()
    yield s
    s.close()


def _loan(db, reminder=None, d=20, title="وام فیک"):
    from app.models import Debt

    debt = Debt(user_id=1, title=title, monthly_toman=Decimal("7654321"), months_left=4, due_year=1405, due_month=8,
                due_day=d, reminder_days_before=reminder)
    db.add(debt)
    db.commit()
    return debt


def _send(db, day, push, shift=0):
    from app.due_reminders import send_due_reminders

    return send_due_reminders(db, now=_utc_noon(1405, 8, day, shift), push=push)


def _first_day_sent(db, push, days=range(5, 21)):
    for day in days:
        if _send(db, day, push):
            return day
    return None


def test_null_uses_default_one_day(db):
    _loan(db, None)
    push = FakePush()
    assert _first_day_sent(db, push) == 19
    assert "فردا" in push.calls[0]["body"]
    assert _first_day_sent(db, push, range(19, 21)) is None and len(push.calls) == 1


def test_custom_three_days(db):
    _loan(db, 3)
    push = FakePush()
    assert _first_day_sent(db, push) == 17 and "۳ روز دیگر" in push.calls[0]["body"]
    assert _first_day_sent(db, push, range(17, 21)) is None and len(push.calls) == 1


def test_one_week(db):
    _loan(db, 7)
    push = FakePush()
    assert _first_day_sent(db, push) == 13 and "۷ روز دیگر" in push.calls[0]["body"]


def test_same_day(db):
    _loan(db, 0)
    push = FakePush()
    assert _first_day_sent(db, push) == 20 and "امروز" in push.calls[0]["body"]
    assert _send(db, 20, push, 3) == 0 and len(push.calls) == 1


def test_off_sends_no_upcoming_but_overdue_still_goes(db):
    _loan(db, -1)
    push = FakePush()
    assert _first_day_sent(db, push) is None and push.calls == []
    assert _send(db, 21, push) == 1 and push.calls[0]["data"]["type"] == "debt_overdue"
    assert _send(db, 22, push) == 0 and len(push.calls) == 1


def test_env_default_still_applies_to_null_only(db, monkeypatch):
    monkeypatch.setenv("DUE_REMINDER_DAYS", "3")
    _loan(db, None, title="الف")
    _loan(db, 1, title="ب")
    push = FakePush()
    assert _send(db, 17, push) == 1 and "الف" in push.calls[0]["body"]
    assert _send(db, 18, push) == 0
    assert _send(db, 19, push) == 1 and "ب" in push.calls[1]["body"]


def test_loan_created_late_inside_window_gets_one_reminder(db):
    push = FakePush()
    assert _send(db, 18, push) == 0
    _loan(db, 3)  # added 2 days before with «۳ روز قبل»: the 17th already passed
    assert _send(db, 18, push) == 1 and "۲ روز دیگر" in push.calls[0]["body"]
    for day in (18, 19, 20):
        for shift in (0, 2, 5):
            assert _send(db, day, push, shift) == 0
    assert len(push.calls) == 1


def test_created_late_at_night_sends_next_allowed_hour(db):
    _loan(db, 1)
    push = FakePush()
    assert _send(db, 19, push, 10) == 0  # 22:00 Tehran: quiet
    assert _send(db, 20, push, -5) == 0  # 07:00 on the due day: quiet
    assert _send(db, 20, push, -3) == 1 and "امروز" in push.calls[0]["body"]  # 09:00


def test_dedupe_holds_when_setting_changes_after_sending(db):
    debt = _loan(db, 3)
    push = FakePush()
    assert _send(db, 17, push) == 1
    debt.reminder_days_before = 1
    db.commit()
    assert _first_day_sent(db, push, range(17, 21)) is None and len(push.calls) == 1


def test_unknown_stored_value_is_treated_as_default(db):
    from app.due_reminders import loan_days_before

    class D:
        reminder_days_before = "x"

    assert loan_days_before(D(), 1) == 1
    D.reminder_days_before = -5
    assert loan_days_before(D(), 1) is None


def test_push_payload_has_no_amount(db):
    _loan(db, 2)
    push = FakePush()
    _first_day_sent(db, push)
    _send(db, 21, push)
    assert len(push.calls) == 2
    for call in push.calls:
        text = call["title"] + call["body"] + repr(call["data"])
        assert not re.search(r"7654321|۷٬?۶۵۴٬?۳۲۱|7,654,321|تومان", text)


# ---- web form and API ----

def _form(**kw):
    base = {"title": "وام تست", "monthly_toman": "۱٬۰۰۰٬۰۰۰", "months_left": "۳", "due_year": "1405", "due_month": "8",
            "due_day": "20"}
    base.update(kw)
    return base


def _loans(username):
    from app.db import SessionLocal
    from app.models import Debt, User

    s = SessionLocal()
    uid = s.query(User).filter_by(username=username).one().id
    out = [(d.id, d.reminder_days_before) for d in s.query(Debt).filter_by(user_id=uid).order_by(Debt.id)]
    s.close()
    return out


def test_form_has_select_with_default_one_day(client, no_network):
    _register(client, "fake_form")
    html = client.get(P).text
    sel = re.search(r'<select id="dv-reminder_days_before" name="reminder_days_before"[^>]*>(.*?)</select>', html, re.S)
    assert sel and "یادآوری قسط" in html
    opts = re.findall(r'<option value="(-?\d)"( selected)?>([^<]+)</option>', sel.group(1))
    assert [(v, label) for v, _, label in opts] == [("-1", "خاموش"), ("0", "همان روز"), ("1", "۱ روز قبل"),
                                                   ("2", "۲ روز قبل"), ("3", "۳ روز قبل"), ("7", "۱ هفته قبل")]
    assert [v for v, s, _ in opts if s] == ["1"]


def test_api_create_and_update_store_value(client, no_network):
    _register(client, "fake_api")
    t = _csrf(client, P)
    assert client.post("/profile/debts", data={**_form(), "csrf": t}, headers=JSON).json()["ok"]  # field absent
    assert client.post("/profile/debts", data={**_form(reminder_days_before="3"), "csrf": t}, headers=JSON).json()["ok"]
    assert client.post("/profile/debts", data={**_form(reminder_days_before="-1"), "csrf": t}, headers=JSON).json()["ok"]
    assert client.post("/profile/debts", data={**_form(reminder_days_before="۷"), "csrf": t}, headers=JSON).json()["ok"]
    rows = _loans("fake_api")
    assert [r for _, r in rows] == [None, 3, -1, 7]
    a, b = rows[0][0], rows[1][0]
    assert client.post(f"/profile/debts/{a}", data={**_form(reminder_days_before="0"), "csrf": t}, headers=JSON).json()["ok"]
    assert client.post(f"/profile/debts/{b}", data={**_form(), "csrf": t}, headers=JSON).json()["ok"]  # absent: kept
    assert [r for _, r in _loans("fake_api")] == [0, 3, -1, 7]
    assert client.post(f"/profile/debts/{b}", data={**_form(reminder_days_before=""), "csrf": t}, headers=JSON).json()["ok"]
    assert [r for _, r in _loans("fake_api")] == [0, None, -1, 7]


@pytest.mark.parametrize("bad", ["4", "5", "-2", "14", "abc", "1.5", "99999999999999999999"])
def test_api_rejects_other_values(client, no_network, bad):
    _register(client, "fake_bad")
    t = _csrf(client, P)
    r = client.post("/profile/debts", data={**_form(reminder_days_before=bad), "csrf": t}, headers=JSON)
    assert r.status_code == 422 and set(r.json()["fields"]) == {"reminder_days_before"}
    assert _loans("fake_bad") == []
    assert client.post("/profile/debts", data={**_form(), "csrf": t}, headers=JSON).json()["ok"]
    did = _loans("fake_bad")[0][0]
    r = client.post(f"/profile/debts/{did}", data={**_form(reminder_days_before=bad), "csrf": t}, headers=JSON)
    assert r.status_code == 422 and "reminder_days_before" in r.json()["fields"]
    assert _loans("fake_bad")[0][1] is None
    # no-JS path: the error shows at the field
    html = client.post("/profile/debts", data={**_form(reminder_days_before=bad), "csrf": t}).text
    assert 'id="dv-err-reminder_days_before" data-dv-err>یکی از گزینه' in html


def test_edit_shows_stored_value_and_null_as_one_day(client, no_network):
    from app.db import SessionLocal
    from app.models import Debt

    _register(client, "fake_edit")
    t = _csrf(client, P)
    client.post("/profile/debts", data={**_form(), "csrf": t}, headers=JSON)
    client.post("/profile/debts", data={**_form(reminder_days_before="7"), "csrf": t}, headers=JSON)
    (null_id, _), (week_id, _) = _loans("fake_edit")
    for did, expect in ((null_id, "1"), (week_id, "7")):
        html = client.get(f"{P}&edit={did}").text
        sel = re.search(r'name="reminder_days_before".*?</select>', html, re.S).group(0)
        assert re.findall(r'<option value="(-?\d)" selected>', sel) == [expect]
    page = with_amounts(client, P)
    forms = [json.loads(unescape(f)) for f in re.findall(r'data-form="([^"]*)"', page)]
    assert sorted(f["reminder_days_before"] for f in forms) == ["1", "7"]
    s = SessionLocal()
    assert s.get(Debt, null_id).reminder_days_before is None  # viewing never writes
    s.close()


def test_debts_page_js_fills_select():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "debts-page.js").read_text()
    assert 'select[data-default]' in js and '"reminder_days_before"' in js


# ---- migration ----

def test_migration_0008_up_down_keeps_rows(tmp_path):
    from tests.test_sanjeh_migration import _dump, _insert
    from tests.test_sanjeh_token_encrypt import _alembic

    db = tmp_path / "fake.db"

    def ok(*args):
        r = _alembic(db, *args)
        assert r.returncode == 0, r.stderr

    ok("upgrade", "0007_global_categories")
    c = sqlite3.connect(db)
    _insert(c, "users", id=1, username="fake_m")
    for i in (1, 2):
        _insert(c, "debts", id=i, user_id=1, title=f"fake-{i}", monthly_toman=1000 * i, months_left=i, due_year=1405,
                due_month=8, due_day=i, created_at="2026-01-01 00:00:00")
    c.commit()
    schema_before = sorted(c.execute("select type, name, sql from sqlite_master where name not like 'sqlite_%'").fetchall(),
                           key=repr)
    c.close()
    before = _dump(db)
    copy = tmp_path / "copy.db"
    shutil.copyfile(db, copy)

    ok("upgrade", "head")
    c = sqlite3.connect(db)
    assert c.execute("select version_num from alembic_version").fetchone()[0] == "0008_debt_reminder_days"
    info = {r[1]: r for r in c.execute("pragma table_info(debts)")}
    assert info["reminder_days_before"][2].upper() == "INTEGER" and info["reminder_days_before"][3] == 0
    assert c.execute("select id, reminder_days_before from debts order by id").fetchall() == [(1, None), (2, None)]
    assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert c.execute("pragma foreign_key_check").fetchall() == []
    c.close()
    after = _dump(db)
    cols, rows = after["debts"]
    i = cols.index("reminder_days_before")
    after["debts"] = (cols[:i] + cols[i + 1:], [r[:i] + r[i + 1:] for r in rows])
    assert after == before

    ok("stamp", "0007_global_categories")
    ok("upgrade", "head")  # column already there: no-op

    ok("downgrade", "0007_global_categories")
    c = sqlite3.connect(db)
    assert "reminder_days_before" not in {r[1] for r in c.execute("pragma table_info(debts)")}
    schema_after = sorted(c.execute("select type, name, sql from sqlite_master where name not like 'sqlite_%'").fetchall(),
                          key=repr)
    c.close()
    assert _dump(db) == before and schema_after == schema_before
    ok("downgrade", "0007_global_categories")  # nothing to drop: still fine
    assert _dump(copy) == before


def test_app_model_matches_migrated_schema(tmp_path):
    from tests.test_sanjeh_token_encrypt import _alembic

    db = tmp_path / "m.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    cols = {r[1] for r in sqlite3.connect(db).execute("pragma table_info(debts)")}
    from app.models import Debt

    assert {c.name for c in Debt.__table__.columns} == cols
