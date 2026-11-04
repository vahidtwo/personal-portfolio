"""Overdue counts, «اقساط این ماه» and its Jalali month boundary, finished loans, and spend notes."""
import re
from types import SimpleNamespace

import jdatetime

from app import debt_schedule as ds
from tests.test_debts_v2 import P, _seed, clock  # noqa: F401
from tests.test_holdings import _register, no_network  # noqa: F401


def D(months, y, m, d, monthly=1000, i=1):
    return SimpleNamespace(id=i, title="t", monthly_toman=monthly, months_left=months, due_year=y, due_month=m, due_day=d)


def _rows(page):
    return re.findall(r'<li class="dv-row[^"]*" data-dv-row="\d+">.*?</li>', page, re.S)


# 1: every overdue loan shows a count; no «مانده» / «آخرین قسط» badge while overdue
def test_single_missed_shows_count_and_drops_end_badge(client, no_network, clock):
    _register(client)
    _seed([("وام الف", 1000000, 1, 1405, 7, 10), ("وام ب", 1000000, 3, 1405, 7, 5), ("وام ج", 1000000, 2, 1405, 8, 5)])
    page = client.get(P).text
    late = [r for r in _rows(page) if "dv-badge late" in r]
    assert len(late) == 2
    for r in late:
        assert re.search(r"روز گذشته، ۱ قسط عقب</span>", r)
        assert "آخرین قسط" not in r and "dv-badge soon" not in r and "dv-badge end" not in r
    ok = next(r for r in _rows(page) if "وام ج" in r)
    assert "dv-badge soon" in ok and "۲ قسط مانده" in ok


# 2: «قسط بعدی» says how many loans are overdue
def test_next_card_counts_overdue_loans(client, no_network, clock):
    _register(client)
    _seed([("الف", 100, 5, 1405, 6, 1), ("ب", 100, 5, 1405, 7, 2), ("ج", 100, 5, 1405, 7, 3),
           ("د", 100, 5, 1405, 7, 20), ("ه", 100, 5, 1405, 8, 1), ("و", 100, 0, 1405, 1, 1)])
    assert "۴ وام عقب‌افتاده" in client.get(P).text
    assert re.search(r'data-overdue-loans>۴ وام عقب‌افتاده<', client.get("/dashboard").text)


def test_no_overdue_label_when_nothing_is_late(client, no_network, clock):
    _register(client)
    _seed([("الف", 100, 5, 1405, 8, 1)])
    assert "وام عقب‌افتاده" not in client.get(P).text
    assert "وام عقب‌افتاده" not in client.get("/dashboard").text


# 3: due this Jalali month plus overdue, each instalment once
def test_month_due_counts_each_instalment_once():
    today = jdatetime.date(1405, 7, 28)
    debts = [D(10, 1405, 5, 1, 1000), D(5, 1405, 8, 1, 300), D(4, 1405, 7, 30, 50), D(0, 1405, 5, 1, 999)]
    total, overdue = ds.month_due(debts, today)
    assert total == 3000 + 50 and overdue == 3000
    assert ds.active_installment(debts) == 1350  # the old figure: one monthly per active loan


def test_month_due_capped_by_months_left():
    assert ds.month_due([D(2, 1405, 3, 1)], jdatetime.date(1405, 7, 28)) == (2000, 2000)


def test_month_due_jalali_boundaries():
    debt = D(6, 1405, 8, 1)
    assert ds.month_due([debt], jdatetime.date(1405, 7, 30)) == (0, 0)  # last day of مهر: آبان not yet
    assert ds.month_due([debt], jdatetime.date(1405, 8, 1)) == (1000, 0)  # first of آبان: due today
    assert ds.month_due([debt], jdatetime.date(1405, 8, 2)) == (1000, 1000)
    esf = D(3, 1405, 12, 31)  # clamped to 29 اسفند 1405
    assert ds.month_due([esf], jdatetime.date(1405, 12, 29)) == (1000, 0)
    assert ds.month_due([esf], jdatetime.date(1406, 1, 1)) == (2000, 1000)  # year wrap


def test_month_due_on_pages(client, no_network, clock):
    _register(client)
    _seed([("الف", 1000000, 10, 1405, 5, 1), ("ب", 500000, 5, 1405, 8, 1)])
    dash = client.get("/dashboard").text
    assert "اقساط این ماه و عقب‌افتاده" in dash and "data-installment-overdue" in dash
    m = re.search(r"<dt>اقساط این ماه و عقب‌افتاده</dt><dd[^>]*><bdi[^>]*data-amount>([^<]+)</bdi>", dash)
    assert m and m.group(1) == "۳٬۰۰۰٬۰۰۰"
    assert "قسط‌های این ماه و عقب‌افتاده" in client.get(P).text


# 5: finished loans
def test_finished_loan_banner_and_exclusions(client, no_network, clock):
    _register(client)
    _seed([("تمام", 9000000, 0, 1405, 5, 1), ("جاری", 1000000, 3, 1405, 8, 1)])
    page = client.get(P).text
    rows = _rows(page)
    assert "تمام" in rows[-1] and "data-dv-settled>تسویه شد<" in rows[-1] and "dv-row done" in rows[-1]
    assert "data-dv-settled" not in rows[0]
    assert 'data-mask="portfolio"' in rows[-1]
    assert "قسط بعدی: <b>جاری</b>" in page and "وام عقب‌افتاده" not in page
    dash = client.get("/dashboard").text
    assert "۹٬۰۰۰٬۰۰۰" not in dash


def test_finished_loan_out_of_every_total():
    today = jdatetime.date(1405, 7, 28)
    done, live = D(0, 1405, 5, 1, 9000, 1), D(3, 1405, 8, 1, 100, 2)
    assert ds.active_total([done, live]) == 300
    assert ds.month_due([done], today) == (0, 0)
    assert ds.overdue_count([done], today) == 0
    assert ds.soonest([done], today) is None
    assert ds.soonest([done, live], today)["title"] == "t" and ds.soonest([done, live], today)["overdue_count"] == 0


def test_finished_loan_out_of_net_worth():
    from app.debts import debt_rows
    _rows_, total, _ = debt_rows([D(0, 1405, 5, 1, 9000)], jdatetime.date(1405, 7, 28))
    assert total == 0 and len(_rows_) == 1


# 4: notes
def test_sms_note_and_key_never_shown(client, no_network):
    _register(client)
    r = client.post("/api/sms-spend", json={"amount_toman": "350000", "note": "خرید از کارت **** مبلغ 350,000", "idempotency_key": "c" * 64})
    assert r.status_code == 200
    html = client.get("/dashboard?tab=daily").text
    assert "c" * 64 not in html and "خرید از کارت" not in html


def test_manual_note_digits_shown_as_typed():
    from app.spends import sms_spend_parts
    assert sms_spend_parts("نان ۲ عدد و 3 شیر 12500", "food") == (False, "نان ۲ عدد و 3 شیر 12500")
    assert sms_spend_parts("x [" + "d" * 64 + "] y", "food") == (False, "x y")


def test_note_is_outside_amount_mask():
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "app/templates/partials/daily_spend.html").read_text()
    small = re.search(r'<span class="t">.*?</small></span>', tpl, re.S).group(0)
    assert "note_display" in small and "data-mask" not in small and "data-amount" not in small
