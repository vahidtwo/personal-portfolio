"""Phase 6 item 8: monthly cost 'paid this month', unpaid line, undo/unpaid, rollover, migration."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.amounts_helper import with_amounts
from tests.test_debts_v2 import P, _db_user, _seed
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

DEY12 = datetime(2027, 1, 2, 8, 30, tzinfo=timezone.utc)      # 1405/10/12 12:00 Tehran
BAHMAN1 = datetime(2027, 1, 21, 8, 30, tzinfo=timezone.utc)   # 1405/11/01 12:00 Tehran
ESFAND29 = datetime(2027, 3, 20, 8, 30, tzinfo=timezone.utc)  # 1405/12/29 12:00 Tehran
FARVARDIN1 = datetime(2027, 3, 21, 8, 30, tzinfo=timezone.utc)  # 1406/01/01 12:00 Tehran


def _set_clock(monkeypatch, dt: datetime):
    import app.formatting as formatting

    state = {"now": dt}
    monkeypatch.setattr(formatting, "_utcnow", lambda: state["now"])
    return state


def _expense_ids():
    from app.models import MonthlyExpense

    db, user = _db_user()
    rows = db.query(MonthlyExpense).filter_by(user_id=user.id).order_by(MonthlyExpense.due_day, MonthlyExpense.id).all()
    out = [(r.title, r.id, r.paid_jy, r.paid_jm) for r in rows]
    db.close()
    return out


def test_mark_paid_updates_row_and_unpaid_line_without_changing_salary_left(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed(
        [("وام", 1_000_000, 6, 1405, 10, 25)],
        expenses=[("اجاره", 18_000_000, 1), ("بیمه", 1_200_000, 20)],
        salary=40_000_000,
    )
    items = dict((t, eid) for t, eid, _, _ in _expense_ids())
    csrf = _csrf(client, P)
    before_salary = client.get("/api/salary").json()
    assert before_salary["left"] == "۱۹٬۸۰۰٬۰۰۰"

    r = client.post(
        f"/profile/expenses/{items['اجاره']}/paid",
        data={"csrf": csrf},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["toast"] == "اجاره دی پرداخت شد"
    assert body["unpaid_url"] == f"/profile/expenses/{items['اجاره']}/unpaid"

    # Salary leftover and total monthly expenses stay identical.
    assert client.get("/api/salary").json() == before_salary
    debts_api = client.get("/api/debts").json()
    assert debts_api["summary"]["expenses_label"] == "۱۹٬۲۰۰٬۰۰۰"

    # /api/expenses reflects paid state + unpaid sum.
    exp_api = client.get("/api/expenses").json()
    assert exp_api["total_label"] == "۱۹٬۲۰۰٬۰۰۰"
    assert exp_api["unpaid_this_month_label"] == "۱٬۲۰۰٬۰۰۰"
    assert exp_api["all_paid"] is False
    by_title = {e["title"]: e for e in exp_api["expenses"]}
    assert by_title["اجاره"]["paid_this_month"] is True
    assert by_title["اجاره"]["overdue"] is False
    assert by_title["اجاره"]["next_label"] == "۱ بهمن"
    assert by_title["بیمه"]["paid_this_month"] is False
    assert by_title["بیمه"]["overdue"] is False
    assert by_title["بیمه"]["next_label"] == "۲۰ دی"

    # Rendered HTML shows paid badge, next month date, ⋯ unpaid menu item, and unpaid line.
    html = with_amounts(client, P)
    assert "این ماه پرداخت شد ✓" in html
    assert "نوبت بعدی: <b>۱ بهمن</b>" in html
    assert f'action="/profile/expenses/{items["اجاره"]}/unpaid"' in html
    assert ">پرداخت نشده</button>" in html
    assert "هنوز پرداخت‌نشده این ماه:" in html
    assert "۱٬۲۰۰٬۰۰۰</bdi> تومان" in html
    assert "جمع هزینهٔ ماهانه" in html and "۱۹٬۲۰۰٬۰۰۰</bdi> تومان" in html


def test_all_paid_shows_done_line_and_zero_api(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed([], expenses=[("اجاره", 5_000_000, 1), ("اینترنت", 650_000, 10)], salary=10_000_000)
    csrf = _csrf(client, P)
    for _title, eid, _, _ in _expense_ids():
        assert client.post(f"/profile/expenses/{eid}/paid", data={"csrf": csrf}, headers={"Accept": "application/json"}).status_code == 200
    exp_api = client.get("/api/expenses").json()
    assert exp_api["unpaid_this_month_label"] == "۰"
    assert exp_api["all_paid"] is True
    html = with_amounts(client, P)
    assert "همهٔ هزینه‌های این ماه پرداخت شد ✓" in html
    assert "p6-pay" not in html  # no pay buttons remain when all are paid
    assert client.get("/api/salary").json()["left"] == "۴٬۳۵۰٬۰۰۰"


def test_unpaid_restores_state_and_stale_unpaid_is_409(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed([], expenses=[("اینترنت", 650_000, 10)])
    eid = _expense_ids()[0][1]
    csrf = _csrf(client, P)

    # Cannot mark unpaid before paying.
    r0 = client.post(f"/profile/expenses/{eid}/unpaid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert r0.status_code == 409

    client.post(f"/profile/expenses/{eid}/paid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert _expense_ids()[0][2:] == (1405, 10)

    r1 = client.post(f"/profile/expenses/{eid}/unpaid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert r1.status_code == 200 and r1.json()["ok"] is True
    assert _expense_ids()[0][2:] == (None, None)

    exp_api = client.get("/api/expenses").json()
    assert exp_api["expenses"][0]["paid_this_month"] is False
    assert exp_api["expenses"][0]["overdue"] is True
    assert exp_api["unpaid_this_month_label"] == "۶۵۰٬۰۰۰"

    # Second unpaid returns 409.
    r2 = client.post(f"/profile/expenses/{eid}/unpaid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert r2.status_code == 409


def test_month_rollover_resets_automatically_including_year_wrap(client, no_network, monkeypatch):
    state = _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed([], expenses=[("اجاره", 18_000_000, 1), ("قبض", 500_000, 31)])
    ids = dict((t, eid) for t, eid, _, _ in _expense_ids())
    csrf = _csrf(client, P)

    client.post(f"/profile/expenses/{ids['اجاره']}/paid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert client.get("/api/expenses").json()["unpaid_this_month_label"] == "۵۰۰٬۰۰۰"

    # Rollover Dey -> Bahman: paid mark from Dey no longer counts; unpaid for Bahman returns 409.
    state["now"] = BAHMAN1
    exp_bahman = client.get("/api/expenses").json()
    assert exp_bahman["unpaid_this_month_label"] == "۱۸٬۵۰۰٬۰۰۰"
    assert all(not e["paid_this_month"] for e in exp_bahman["expenses"])
    assert client.post(f"/profile/expenses/{ids['اجاره']}/unpaid", data={"csrf": csrf}, headers={"Accept": "application/json"}).status_code == 409

    # Rollover Esfand -> Farvardin (new Jalali year 1405 -> 1406).
    state["now"] = ESFAND29
    # Day 31 clamps to 29 Esfand in non-leap 1405, so due today (not overdue).
    exp_esf = client.get("/api/expenses").json()
    qabz = next(e for e in exp_esf["expenses"] if e["title"] == "قبض")
    assert qabz["overdue"] is False and qabz["next_label"] == "۲۹ اسفند"

    client.post(f"/profile/expenses/{ids['قبض']}/paid", data={"csrf": csrf}, headers={"Accept": "application/json"})
    assert next(e for e in client.get("/api/expenses").json()["expenses"] if e["title"] == "قبض")["paid_this_month"] is True

    state["now"] = FARVARDIN1
    exp_far = client.get("/api/expenses").json()
    assert all(not e["paid_this_month"] for e in exp_far["expenses"])
    assert exp_far["unpaid_this_month_label"] == "۱۸٬۵۰۰٬۰۰۰"


def test_overdue_badge_and_copy_on_page(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed([], expenses=[("اینترنت", 650_000, 10), ("امروز", 300_000, 12), ("بیمه", 1_200_000, 20)])
    html = with_amounts(client, P)
    # Internet (day 10 on Dey 12): overdue
    row_net = re.search(r'data-dv-row="x\d+">.*?اینترنت.*?</li>', html, re.S).group(0)
    assert '<span class="dv-badge late">عقب‌افتاده</span>' in row_net
    assert "سررسید: <b>۱۰ دی</b>" in row_net
    # Today (day 12 on Dey 12): unpaid, not overdue
    row_today = re.search(r'data-dv-row="x\d+">.*?امروز.*?</li>', html, re.S).group(0)
    assert '<span class="dv-badge unpaid">پرداخت‌نشده</span>' in row_today
    assert "نوبت بعدی: <b>۱۲ دی</b>" in row_today


def test_masked_html_keeps_chips_and_pay_button_without_raw_amounts(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client)
    _seed([], expenses=[("اجاره", 18_765_432, 20)])
    raw_html = client.get(P).text
    assert "۱۸٬۷۶۵٬۴۳۲" not in raw_html
    assert "18765432" not in raw_html
    assert 'data-unpaid-line' in raw_html
    assert 'data-amt="expenses-unpaid"' in raw_html
    assert "پرداخت‌نشده" in raw_html
    assert "پرداخت شد" in raw_html


def test_csrf_ownership_and_html_form_post(client, no_network, monkeypatch):
    _set_clock(monkeypatch, DEY12)
    _register(client, "mallory")
    _seed([], expenses=[("اجاره مالوری", 9_000_000, 5)], username="mallory")
    db, mallory_user = _db_user("mallory")
    from app.models import MonthlyExpense
    m_id = db.query(MonthlyExpense).filter_by(user_id=mallory_user.id).one().id
    db.close()
    client.post("/logout", data={"csrf": _csrf(client)})

    _register(client, "alice")
    _seed([], expenses=[("اجاره آلیس", 4_000_000, 5)], username="alice")
    a_id = _expense_ids()[0][1]
    csrf = _csrf(client, P)

    assert client.post(f"/profile/expenses/{a_id}/paid").status_code == 400
    assert client.post(f"/profile/expenses/{m_id}/paid", data={"csrf": csrf}, headers={"Accept": "application/json"}).status_code == 404
    assert client.post(f"/profile/expenses/{m_id}/unpaid", data={"csrf": csrf}, headers={"Accept": "application/json"}).status_code == 404

    # Plain HTML form POST (no-JS) redirects with flash message.
    r = client.post(f"/profile/expenses/{a_id}/paid", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == P
    assert "اجاره آلیس دی پرداخت شد" in client.get(P).text

    r_un = client.post(f"/profile/expenses/{a_id}/unpaid", data={"csrf": csrf}, follow_redirects=False)
    assert r_un.status_code == 303
    assert _expense_ids()[0][2:] == (None, None)


def test_migration_0011_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "copy.sqlite"
    url = f"sqlite:///{db_path}"
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "app/migrations"))

    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["0011_monthly_expense_paid"]

    engine = create_engine(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0010_debt_last_paid_on")
        uid = 1
        conn.execute(text("INSERT INTO monthly_expenses (user_id, title, amount_toman, due_day, created_at) VALUES (:u, 'اجاره', 15000000, 1, '2026-11-25 12:00:00')"), {"u": uid})

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # idempotent
        cols = {c["name"] for c in inspect(conn).get_columns("monthly_expenses")}
        assert {"paid_jy", "paid_jm"} <= cols
        row = conn.execute(text("SELECT title, amount_toman, due_day, paid_jy, paid_jm FROM monthly_expenses")).fetchone()
        assert tuple(row) == ("اجاره", 15000000, 1, None, None)

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0010_debt_last_paid_on")
        cols_after = {c["name"] for c in inspect(conn).get_columns("monthly_expenses")}
        assert "paid_jy" not in cols_after and "paid_jm" not in cols_after
        row = conn.execute(text("SELECT title, amount_toman, due_day FROM monthly_expenses")).fetchone()
        assert tuple(row) == ("اجاره", 15000000, 1)

    engine.dispose()
