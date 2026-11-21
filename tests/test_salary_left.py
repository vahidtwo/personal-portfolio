"""«مانده از حقوق»: salary − this Jalali month's instalments of active loans − fixed monthly costs."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import jdatetime

from tests.test_debts_v2 import clock  # noqa: F401
from tests.test_holdings import no_network  # noqa: F401

from app import debt_schedule as ds
from tests.amounts_helper import with_amounts


def D(months, y, m, d, monthly=1000, created=None):
    return SimpleNamespace(id=1, title="t", monthly_toman=monthly, months_left=months,
                           due_year=y, due_month=m, due_day=d, created_at=created)


TODAY = jdatetime.date(1405, 8, 13)
FIRST = jdatetime.date(1405, 8, 1)
LAST = jdatetime.date(1405, 8, 30)


def test_unpaid_and_paid_this_month_both_count():
    unpaid = D(5, 1405, 8, 20, 1000)
    paid = D(4, 1405, 9, 5, 2000)
    assert ds.this_month_installments([unpaid, paid], TODAY) == Decimal("3000")


def test_older_overdue_months_are_not_added():
    late = D(5, 1405, 6, 10, 1000)
    assert ds.month_due([late], TODAY)[0] == Decimal("3000")
    assert ds.this_month_installments([late], TODAY) == Decimal("1000")


def test_overdue_loan_that_ended_before_this_month_adds_nothing():
    assert ds.this_month_installments([D(1, 1405, 7, 10)], TODAY) == Decimal("0")


def test_finished_and_future_loans_are_out():
    assert ds.this_month_installments([D(0, 1405, 8, 10), D(6, 1405, 10, 1)], TODAY) == Decimal("0")


def test_loan_ending_this_month():
    assert ds.this_month_installments([D(1, 1405, 8, 25, 700)], TODAY) == Decimal("700")
    assert ds.this_month_installments([D(0, 1405, 9, 25, 700)], TODAY) == Decimal("700")


def test_month_boundaries():
    debt = D(3, 1405, 8, 1, 1000)
    assert ds.this_month_installments([debt], FIRST) == Decimal("1000")
    assert ds.this_month_installments([debt], LAST) == Decimal("1000")
    last_day = D(3, 1405, 8, 31, 1000)
    assert ds.this_month_installments([last_day], LAST) == Decimal("1000")
    assert ds.this_month_installments([D(3, 1405, 9, 1, 1000)], LAST) == Decimal("1000")
    assert ds.this_month_installments([D(3, 1405, 9, 1, 1000)], jdatetime.date(1405, 9, 1)) == Decimal("1000")


def test_new_loan_starting_next_month_is_not_counted():
    created = datetime(2026, 11, 3, 8, tzinfo=timezone.utc)
    assert ds.this_month_installments([D(6, 1405, 9, 5, 1000, created)], TODAY) == Decimal("0")
    early = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    assert ds.this_month_installments([D(6, 1405, 9, 5, 1000, early)], TODAY) == Decimal("1000")


def test_salary_left_formula_and_negative():
    debts = [D(5, 1405, 8, 20, 4_000_000), D(4, 1405, 9, 5, 3_000_000), D(2, 1405, 6, 1, 1_000_000)]
    assert ds.salary_left(20_000_000, debts, 5_000_000, TODAY) == Decimal("8000000")
    assert ds.salary_left(6_000_000, debts, 5_000_000, TODAY) == Decimal("-6000000")
    assert ds.salary_left(None, [], None, TODAY) == Decimal("0")


def test_pages_split_remaining_and_month_total(client, no_network, clock):  # noqa: F811
    import re

    from app.db import SessionLocal
    from app.models import Debt
    from tests.test_debts_v2 import P, _seed

    from tests.test_holdings import _register

    _register(client)
    _seed([("عقب", 1000000, 5, 1405, 6, 1), ("پرداخت‌شده", 500000, 3, 1405, 8, 10),
           ("تمام", 9000000, 0, 1405, 7, 5), ("باز", 200000, 2, 1405, 7, 30)],
          expenses=[("اجاره", 1000000, 5)], salary=10000000)
    db = SessionLocal()
    for debt in db.query(Debt).all():
        debt.created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db.commit()
    db.close()

    dash = with_amounts(client, "/dashboard")
    left = re.search(r"<dt>اقساط باقی‌مانده</dt><dd[^>]*><bdi[^>]*data-amount>([^<]+)</bdi>", dash)
    total = re.search(r"<dt>جمع اقساط این ماه</dt><dd[^>]*><bdi[^>]*data-mask=\"portfolio\" data-amount data-month-total>([^<]+)</bdi>", dash)
    assert left.group(1) == "۲٬۲۰۰٬۰۰۰" and total.group(1) == "۱٬۷۰۰٬۰۰۰"
    tab = with_amounts(client, P)
    assert re.search(r'<p class="dv-sumrow lead" data-month-total-row><span>جمع اقساط این ماه</span><b class="num"><bdi class="mask-sm" data-mask="portfolio" data-amount data-month-total>۱٬۷۰۰٬۰۰۰</bdi>', tab)
    assert "جمع اقساط این ماه" not in tab[tab.index("dv-tiles"):tab.index("data-month-total-row")]
    assert re.search(r"<span>اقساط باقی‌مانده</span><b[^>]*data-mask=\"portfolio\"[^>]*><bdi dir=\"ltr\">۲٬۲۰۰٬۰۰۰<", tab)
    assert client.get("/api/salary").json()["left"] == "۷٬۳۰۰٬۰۰۰"


def test_dashboard_month_total_sits_in_monthly_report(client, no_network, clock):  # noqa: F811
    from tests.test_debts_v2 import _seed
    from tests.test_holdings import _register

    _register(client)
    _seed([("باز", 200000, 2, 1405, 7, 30)])
    dash = with_amounts(client, "/dashboard")
    report = dash[dash.index('id="month-report-heading"'):]
    stats = dash[:dash.index('id="month-report-heading"')]
    assert "<dt>جمع اقساط این ماه</dt>" not in stats
    assert report.index("<dt>اقساط باقی‌مانده</dt>") < report.index("<dt>جمع اقساط این ماه</dt>") < report.index("<dt>هزینهٔ ماهانه</dt>")
    assert 'data-mask="portfolio" data-amount data-month-total>۲۰۰٬۰۰۰<' in report


def test_final_instalment_paid_this_month_counts():
    assert ds.this_month_installments([D(0, 1405, 9, 10, 700)], TODAY) == Decimal("700")
    assert ds.this_month_installments([D(0, 1405, 9, 10, 700)], LAST) == Decimal("700")
    assert ds.this_month_installments([D(0, 1405, 9, 10, 700)], FIRST) == Decimal("700")


def test_other_finished_rows_stay_out():
    for stored in ((1405, 8), (1405, 10), (1405, 7), (1406, 9)):
        assert ds.this_month_installments([D(0, *stored, 10, 700)], TODAY) == Decimal("0")


def test_final_paid_in_esfand_rolls_to_farvardin():
    esfand = jdatetime.date(1405, 12, 15)
    assert ds.this_month_installments([D(0, 1406, 1, 10, 900)], esfand) == Decimal("900")
    assert ds.this_month_installments([D(0, 1405, 1, 10, 900)], esfand) == Decimal("0")
    assert ds.this_month_installments([D(0, 1406, 2, 10, 900)], esfand) == Decimal("0")


def test_final_paid_not_double_counted_with_active_loans():
    debts = [D(0, 1405, 9, 10, 700), D(3, 1405, 8, 20, 1000), D(2, 1405, 9, 5, 500)]
    assert ds.this_month_installments(debts, TODAY) == Decimal("2200")
    assert ds.month_due(debts, TODAY)[0] == Decimal("1000")
