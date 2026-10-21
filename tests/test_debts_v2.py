"""Debts v2: manual «پرداخت شد» + undo, 0-left debts out of every total, per-field errors, sorting, legacy rows."""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

P = "/profile?tab=debts"
MEHR28 = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)  # 1405/07/28 12:00 Tehran
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


@pytest.fixture()
def clock(monkeypatch):
    import app.formatting as formatting

    state = {"now": MEHR28}
    monkeypatch.setattr(formatting, "_utcnow", lambda: state["now"])
    return state


def _db_user(username="alice"):
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    return db, db.query(User).filter_by(username=username).one()


def _seed(rows, username="alice", expenses=(), salary=None):
    """Legacy-shaped rows written straight to the DB (as old versions stored them)."""
    from app.models import Debt, MonthlyExpense

    db, user = _db_user(username)
    ids = []
    for title, monthly, months, y, m, d in rows:
        debt = Debt(user_id=user.id, title=title, monthly_toman=Decimal(monthly), months_left=months, due_year=y, due_month=m, due_day=d)
        db.add(debt)
        db.flush()
        ids.append(debt.id)
    for title, amount, day in expenses:
        db.add(MonthlyExpense(user_id=user.id, title=title, amount_toman=Decimal(amount), due_day=day))
    if salary is not None:
        user.salary_toman = Decimal(salary)
    db.commit()
    db.close()
    return ids


def _debt(debt_id):
    from app.models import Debt

    db, _ = _db_user()
    d = db.get(Debt, debt_id)
    out = (d.months_left, d.due_year, d.due_month, d.due_day) if d else None
    db.close()
    return out


def _form(**kw):
    base = {"title": "لپ‌تاپ", "monthly_toman": "۱٬۷۵۰٬۰۰۰", "months_left": "۹", "due_year": "۱۴۰۵", "due_month": "۸", "due_day": "۱۰"}
    base.update(kw)
    return base


# ---------- validation ----------
CASES = [
    ("۲٬۵۰۰٬۰۰۰", "۱۲", "۱۴۰۵", "۸", "۱", None),
    ("2,500,000", "1", "1405", "12", "29", None),
    ("۲٫۵۰۰٫۰۰۰", "۰", "۱۴۰۵", "۱۳", "۱", None),
    ("۲۵۰۰٫۵", "۳", "۱۴۰۵", "۷", "۳۱", None),
    ("۰", "x", "99", "0", "40", None),
    ("-۵", "۱٫۵", "۱۴۰۳", "۱۲", "۳۰", None),
    ("1500.5", "2", "1405", "8", "1", "1500.5"),
    ("1500.7", "2", "1405", "8", "1", "1500.5"),
]


def test_validate_debt_reports_every_field():
    from app.debt_validation import validate_debt

    assert validate_debt(*CASES[0][:5])[0] == {}
    errors, _ = validate_debt(*CASES[2][:5])
    assert errors == {"monthly_toman": "مبلغ را بدون ممیز بنویسید؛ مثلاً ۲٬۵۰۰٬۰۰۰", "months_left": "دست‌کم ۱ قسط باید مانده باشد",
                      "due_month": "ماه بین ۱ تا ۱۲ است"}
    assert validate_debt("۵۰۰", "۲", "۱۴۰۵", "۷", "۳۱")[0] == {"due_day": "این ماه ۳۰ روز دارد"}
    assert validate_debt("1500.5", "2", "1405", "8", "1", Decimal("1500.5"))[0] == {}  # legacy fraction kept on edit


def test_js_validation_matches_server():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    from app.debt_validation import validate_debt, validate_expense

    script = (f"const v=require({str(STATIC / 'debts-page.js')!r});const c={json.dumps(CASES, ensure_ascii=False)};"
              "console.log(JSON.stringify([c.map(x=>v.validateDebt({monthly_toman:x[0],months_left:x[1],due_year:x[2],due_month:x[3],due_day:x[4],orig:x[5]||''})),"
              "c.map(x=>v.validateExpense({amount_toman:x[0],due_day:x[4],orig:x[5]||''})),"
              "v.preview({monthly_toman:'۱٬۷۵۰٬۰۰۰',months_left:'۹',due_year:'۱۴۰۵',due_month:'۸',due_day:'۱۰'})]));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20, cwd=STATIC)
    assert out.returncode == 0, out.stderr
    debts, expenses, preview = json.loads(out.stdout)
    orig = lambda x: Decimal(x[5]) if x[5] else None  # noqa: E731
    assert debts == [validate_debt(*x[:5], orig(x))[0] for x in CASES]
    assert expenses == [validate_expense(x[0], x[4], orig(x))[0] for x in CASES]
    assert preview == "جمع مانده: ۱۵٬۷۵۰٬۰۰۰ تومان، آخرین قسط: ۱۰ تیر ۱۴۰۶"


def test_invalid_post_shows_all_errors_and_saves_nothing(client, no_network, clock):
    from app.models import Debt

    _register(client)
    html = client.post("/profile/debts", data={**_form(monthly_toman="۲٫۵۰۰٫۰۰۰", months_left="۰", due_month="۱۳"),
                                               "csrf": _csrf(client, P)}).text
    assert "۳ مورد نیاز به اصلاح دارد" in html and html.count('aria-invalid="true"') == 3
    assert 'id="dv-err-months_left" data-dv-err>دست‌کم ۱ قسط باید مانده باشد</span>' in html
    assert 'data-dv-open="debt"' in html and 'value="۱۳"' in html  # typed values kept, in Persian digits
    r = client.post("/profile/expenses", data={"title": "x", "amount_toman": "abc", "due_day": "۴۰", "csrf": _csrf(client, P)},
                    headers={"Accept": "application/json"})
    assert r.status_code == 422 and r.json()["fields"] == {"amount_toman": "مبلغ را بدون ممیز بنویسید؛ مثلاً ۲٬۵۰۰٬۰۰۰",
                                                           "due_day": "روز بین ۱ تا ۳۱ است"}
    ok = client.post("/profile/debts", data={**_form(), "csrf": _csrf(client, P)}, headers={"Accept": "application/json"})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "redirect": P}
    db, user = _db_user()
    assert [(d.title, d.monthly_toman, d.months_left) for d in db.query(Debt).filter_by(user_id=user.id)] == [("لپ‌تاپ", Decimal("1750000"), 9)]
    db.close()


# ---------- rows ----------
def test_rows_sorted_by_next_due_with_badges_and_end_month(client, no_network, clock):
    _register(client)
    _seed([("وام مسکن", 12500000, 34, 1405, 8, 5), ("وام ازدواج", 1150000, 52, 1405, 8, 1), ("اسنپ‌پی", 890000, 2, 1405, 8, 3),
           ("صندوق", 3000000, 1, 1405, 8, 25), ("تمام‌شده", 500000, 0, 1405, 1, 1)],
          expenses=[("بیمه", 1100000, 28), ("اجاره", 18000000, 1), ("قبض", 700000, 31)])
    html = client.get(P).text
    titles = re.findall(r'<li class="dv-row[^"]*" data-dv-row="\d+">\s*<div class="t"><b>([^<]+)</b>', html)
    assert titles == ["وام ازدواج", "اسنپ‌پی", "وام مسکن", "صندوق", "تمام‌شده"]
    assert "۳۴ قسط مانده، تا مرداد ۱۴۰۸" in html  # 1405/08 + 33 months (spec example)
    assert '<span class="dv-badge end">آخرین قسط</span>' in html and '<span class="dv-badge soon">۲ قسط مانده</span>' in html
    assert "قسط بعدی: <b>وام ازدواج</b>، ۱ آبان، <bdi class=\"num\">۱٬۱۵۰٬۰۰۰</bdi> تومان" in html and "۳ روز دیگر" in html
    exp = re.findall(r'data-dv-row="x\d+">\s*<div class="t"><b>([^<]+)</b><small>روز ([^ ]+) هر ماه', html)
    assert exp == [("اجاره", "۱"), ("بیمه", "۲۸"), ("قبض", "۳۱")]
    assert "نوبت بعدی: <b>۳۰ مهر</b>" in html  # day 31 in a 30-day month counts the last day
    assert " · " not in html.split('data-dv-page')[1].split('<footer')[0]


# ---------- «پرداخت شد» and undo ----------
def test_paid_moves_one_instalment_and_undo_restores(client, no_network, clock):
    _register(client)
    (debt_id,) = _seed([("وام ازدواج", 1150000, 52, 1405, 8, 1)])
    t = _csrf(client, P)
    r = client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "52", "csrf": t}, follow_redirects=False)
    assert r.status_code == 303 and _debt(debt_id) == (51, 1405, 9, 1)
    page = client.get(P).text
    assert "یک قسط از «وام ازدواج» کم شد. قسط بعدی به ماه بعد رفت." in page and f'action="/profile/debts/{debt_id}/unpaid"' in page
    assert "قسط بعدی: <b>وام ازدواج</b>، ۱ آذر" in page
    assert "یک قسط از" not in client.get(P).text  # banner shown once
    # double tap / stale tab: the count the user saw no longer matches -> nothing changes
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "52", "csrf": t})
    assert _debt(debt_id) == (51, 1405, 9, 1)
    client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": t})
    assert _debt(debt_id) == (52, 1405, 8, 1)
    client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": t})  # undo is one-shot
    assert _debt(debt_id) == (52, 1405, 8, 1)


def test_paid_needs_csrf_and_ownership(client, no_network, clock):
    _register(client, "mallory")
    (mine,) = _seed([("m", 100, 3, 1405, 8, 1)], username="mallory")
    client.post("/logout", data={"csrf": _csrf(client)})
    _register(client)
    (theirs,) = _seed([("a", 100, 3, 1405, 8, 1)])
    assert client.post(f"/profile/debts/{theirs}/paid", data={"expect": "3"}).status_code == 400  # no CSRF
    client.post(f"/profile/debts/{mine}/paid", data={"expect": "3", "csrf": _csrf(client, P)})
    assert _debt(mine) == (3, 1405, 8, 1) and _debt(theirs) == (3, 1405, 8, 1)


def test_day_31_loan_keeps_its_day_and_last_payment_ends_it(client, no_network, clock):
    _register(client)
    (debt_id,) = _seed([("روز ۳۱", 1000, 2, 1405, 6, 31)])  # stored date in the past: next due is from the calendar
    t = _csrf(client, P)
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "2", "csrf": t})
    assert _debt(debt_id) == (1, 1405, 8, 31)  # next due was 30 مهر (clamped); moved to آبان, day 31 kept
    assert "قسط بعدی: <b>۳۰ آبان</b>" in client.get(P).text
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "1", "csrf": t})
    assert _debt(debt_id)[0] == 0
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "0", "csrf": t})
    assert _debt(debt_id)[0] == 0  # never below 0


# ---------- 0-left debts are out of every total ----------
def test_zero_left_debts_drop_out_of_all_totals(client, no_network, clock):
    from app.expenses import monthly_view
    from app.mcp_http import _debts, _monthly_left

    _register(client)
    _seed([("فعال", 1000000, 3, 1405, 8, 5), ("تمام‌شده", 9000000, 0, 1405, 8, 2)], expenses=[("اجاره", 2000000, 1)], salary=10000000)
    page = client.get(P).text
    assert '<b class="num" data-dv-num><bdi dir="ltr">۱٬۰۰۰٬۰۰۰</bdi></b>' in page  # قسط‌های این ماه
    assert '<b class="num" data-dv-num><bdi dir="ltr">۳٬۰۰۰٬۰۰۰</bdi></b>' in page  # جمع بدهی مانده
    assert "قسط بعدی: <b>فعال</b>" in page
    dash = client.get("/dashboard").text
    tile = dash[dash.index('id="tile-next-debt"'):dash.index('id="tile-month-spend"')]
    assert "فعال" in tile and "تمام‌شده" not in tile and "۹٬۰۰۰٬۰۰۰" not in tile
    assert client.get("/api/salary").json()["left"] == "۷٬۰۰۰٬۰۰۰"  # 10M − 1M − 2M
    db, user = _db_user()
    try:
        assert monthly_view(db, user)["installment_month_label"] == "۱٬۰۰۰٬۰۰۰"
        mcp = _debts(db, user)
        assert mcp["total_toman"] in ("3000000", "3000000.00", 3000000) or Decimal(str(mcp["total_toman"])) == Decimal("3000000")
        assert [d["paid_off"] for d in mcp["debts"]] == [False, True]
        left = _monthly_left(db, user)
        assert Decimal(str(left.get("installments_toman", left.get("installment_toman", "1000000")))) == Decimal("1000000")
    finally:
        db.close()


# ---------- legacy rows and the manual-only countdown ----------
def test_legacy_rows_load_edit_and_never_count_down_by_themselves(client, no_network, clock):
    from app.formatting import format_amount_input

    _register(client)
    (debt_id,) = _seed([("قدیمی", "1500000.5", 10, 1404, 1, 15)])  # past date and a fraction, as old versions saved
    page = client.get(P).text
    assert "۱۰ قسط مانده" in page and "قسط بعدی: <b>۱۵ آبان</b>" in page
    snapshot = re.findall(r'data-dv-num><bdi dir="ltr">([^<]+)<', page)
    clock["now"] = datetime(2026, 11, 25, 8, 30, tzinfo=timezone.utc)  # a month later, no «پرداخت شد»
    later = client.get(P).text
    assert re.findall(r'data-dv-num><bdi dir="ltr">([^<]+)<', later) == snapshot and "۱۰ قسط مانده" in later
    assert _debt(debt_id) == (10, 1404, 1, 15)  # nothing written by reading
    edit = client.get(f"{P}&edit={debt_id}").text
    amount = format_amount_input(Decimal("1500000.5"))
    assert f'value="{amount}"' in edit and 'data-dv-orig="1500000.5"' in edit
    r = client.post(f"/profile/debts/{debt_id}", data={**_form(title="قدیمی ویرایش‌شده", monthly_toman=amount, months_left="۱۰",
                                                               due_year="۱۴۰۵", due_month="۹", due_day="۱۵"), "csrf": _csrf(client, P)},
                    headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json()["ok"]
    from app.models import Debt

    db, _ = _db_user()
    d = db.get(Debt, debt_id)
    assert (d.title, Decimal(d.monthly_toman), d.months_left) == ("قدیمی ویرایش‌شده", Decimal("1500000.5"), 10)
    db.close()


def test_page_contract(client, no_network, clock):
    _register(client)
    _seed([("لپ‌تاپ", 1750000, 9, 1405, 8, 10)], expenses=[("اجاره", 18000000, 1)])
    html = client.get(P).text
    assert 'class="tabs"' not in html and "رفتن به فرم" not in html and "confirm(" not in html
    assert 'data-salary-reveal' in html and 'data-salary-field="left">••••••' in html and 'data-salary-field="salary">••••••' in html
    assert 'role="menu"' in html and 'aria-label="گزینه‌های لپ‌تاپ"' in html and 'role="alertdialog"' in html
    assert 'id="debt-form"' in html and 'id="expense-form"' in html and 'data-dv-close>انصراف</button>' in html
    assert "پرداخت شد، یک قسط کم کن" in html and 'name="expect" value="9"' in html
    assert "۹ قسط ۱٬۷۵۰٬۰۰۰ تومانی، جمعاً ۱۵٬۷۵۰٬۰۰۰ تومان، از فهرست و از جمع بدهی برداشته می‌شود. حذف برگشت ندارد." in html
    assert "/static/debts-page.js?v=20261020y" in html
