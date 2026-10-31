"""Missed instalments stay overdue; «پرداخت شد» pays the oldest unpaid one and moves exactly one month."""
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import jdatetime
import pytest

from app import debt_schedule as ds
from tests.test_debts_v2 import P, _debt, _seed, clock  # noqa: F401
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401


def D(months, y, m, d):
    return SimpleNamespace(id=1, title="t", monthly_toman=1000, months_left=months, due_year=y, due_month=m, due_day=d)


def test_missed_date_stays_and_counts_days():
    today = jdatetime.date(1405, 8, 10)
    debt = D(5, 1405, 8, 1)
    assert ds.next_due(debt, today) == jdatetime.date(1405, 8, 1)
    assert ds.overdue_days(debt, today) == 9
    assert ds.days_chip(-9) == "۹ روز گذشته"
    assert ds.missed_count(debt, today) == 1
    assert ds.overdue_days(D(5, 1405, 8, 10), today) == 0 and ds.missed_count(D(5, 1405, 8, 10), today) == 0


def test_several_missed_months_capped_by_months_left():
    today = jdatetime.date(1405, 8, 10)
    assert ds.missed_count(D(12, 1405, 4, 5), today) == 5  # تیر..آبان 5th: 4,5,6,7,8
    assert ds.missed_count(D(2, 1405, 4, 5), today) == 2


def test_paying_missed_ones_walks_month_by_month_without_skipping():
    today = jdatetime.date(1405, 8, 10)
    debt = D(6, 1405, 5, 20)
    seen = []
    for _ in range(4):
        y, m = ds.after_payment(debt, today)
        debt.due_year, debt.due_month = y, m
        debt.months_left -= 1
        seen.append((y, m))
    assert seen == [(1405, 6), (1405, 7), (1405, 8), (1405, 9)]
    assert ds.overdue_days(debt, today) == 0


@pytest.mark.parametrize("y,m,expect", [
    (1405, 6, (1405, 6, 31)),   # 31-day month keeps 31
    (1405, 7, (1405, 7, 30)),   # مهر has 30 days
    (1405, 12, (1405, 12, 29)),  # اسفند 1405 is not leap
    (1403, 12, (1403, 12, 30)),  # اسفند 1403 is leap
])
def test_month_end_clamp_on_jalali_months(y, m, expect):
    nxt = ds.next_due(D(3, y, m, 31), jdatetime.date(1406, 1, 1))
    assert (nxt.year, nxt.month, nxt.day) == expect


def test_year_wrap_after_payment():
    assert ds.after_payment(D(3, 1405, 12, 31), jdatetime.date(1406, 1, 15)) == (1406, 1)


def test_end_due_counts_from_oldest_unpaid():
    assert ds.end_due(D(3, 1405, 6, 15), jdatetime.date(1405, 8, 1)) == jdatetime.date(1405, 8, 15)


def test_overdue_page_and_pay_oldest(client, no_network, clock):
    _register(client)
    (debt_id,) = _seed([("وام", 1000000, 10, 1405, 5, 1)])  # today 1405/07/28: مرداد, شهریور, مهر missed
    page = client.get(P).text
    assert re.search(r'<span class="dv-badge late">[^<]*روز گذشته، ۳ قسط عقب</span>', page)
    assert "قسط بعدی: <b>۱ مرداد</b>" in page and 'class="d late"' in page
    t = _csrf(client, P)
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "10", "csrf": t})
    assert _debt(debt_id) == (9, 1405, 6, 1)
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "9", "csrf": t})
    assert _debt(debt_id) == (8, 1405, 7, 1)
    page = client.get(P).text
    assert "قسط بعدی: <b>۱ مهر</b>" in page and "۲۷ روز گذشته" in page
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "8", "csrf": t})
    assert _debt(debt_id) == (7, 1405, 8, 1)
    assert "dv-badge late" not in client.get(P).text


def test_dashboard_chip_shows_overdue(client, no_network, clock):
    _register(client)
    _seed([("وام", 1000000, 4, 1405, 7, 20)])
    html = client.get("/dashboard").text
    m = re.search(r'<span class="badge badge-due is-soon">([^<]+)</span>', html)
    assert m and m.group(1).strip() == "۸ روز گذشته"
