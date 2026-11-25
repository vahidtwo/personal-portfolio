"""«مانده از حقوق»: salary − this Jalali month's instalments of active loans − fixed monthly costs."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import jdatetime

from tests.test_debts_v2 import clock  # noqa: F401
from tests.test_holdings import no_network  # noqa: F401

from app import debt_schedule as ds
from tests.amounts_helper import with_amounts


def D(months, y, m, d, monthly=1000, created=None, last_paid=None):
    return SimpleNamespace(id=1, title="t", monthly_toman=monthly, months_left=months,
                           due_year=y, due_month=m, due_day=d, created_at=created,
                           last_paid_on=last_paid)


TODAY = jdatetime.date(1405, 8, 13)
FIRST = jdatetime.date(1405, 8, 1)
LAST = jdatetime.date(1405, 8, 30)


def test_unpaid_this_month_counts_and_next_month_does_not():
    unpaid = D(5, 1405, 8, 20, 1000)
    nxt = D(4, 1405, 9, 5, 2000)
    assert ds.this_month_installments([unpaid, nxt], TODAY) == Decimal("1000")


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
    assert ds.this_month_installments([D(3, 1405, 9, 1, 1000)], LAST) == Decimal("0")
    assert ds.this_month_installments([D(3, 1405, 9, 1, 1000)], jdatetime.date(1405, 9, 1)) == Decimal("1000")


def test_new_loan_starting_next_month_is_not_counted():
    created = datetime(2026, 11, 3, 8, tzinfo=timezone.utc)
    assert ds.this_month_installments([D(6, 1405, 9, 5, 1000, created)], TODAY) == Decimal("0")
    early = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    assert ds.this_month_installments([D(6, 1405, 9, 5, 1000, early)], TODAY) == Decimal("0")


def test_salary_left_formula_and_negative():
    debts = [D(5, 1405, 8, 20, 4_000_000), D(4, 1405, 9, 5, 3_000_000), D(2, 1405, 6, 1, 1_000_000)]
    assert ds.salary_left(20_000_000, debts, 5_000_000, TODAY) == Decimal("11000000")
    assert ds.salary_left(6_000_000, debts, 5_000_000, TODAY) == Decimal("-3000000")
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
    assert left.group(1) == "۲٬۲۰۰٬۰۰۰" and total.group(1) == "۱٬۲۰۰٬۰۰۰"
    tab = with_amounts(client, P)
    assert re.search(r'<p class="dv-sumrow lead" data-month-total-row><span>جمع اقساط این ماه</span><b class="num"><bdi class="mask-sm" data-mask="portfolio" data-amount data-month-total>۱٬۲۰۰٬۰۰۰</bdi>', tab)
    assert "جمع اقساط این ماه" not in tab[tab.index("dv-tiles"):tab.index("data-month-total-row")]
    assert re.search(r"<span>اقساط باقی‌مانده</span><b[^>]*data-mask=\"portfolio\"[^>]*><bdi dir=\"ltr\">۲٬۲۰۰٬۰۰۰<", tab)
    assert client.get("/api/salary").json()["left"] == "۷٬۸۰۰٬۰۰۰"


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
    assert ds.this_month_installments(debts, TODAY) == Decimal("1700")
    assert ds.month_due(debts, TODAY)[0] == Decimal("1000")


def test_next_month_loan_after_due_day_is_not_counted():
    """A next-month unpaid loan is out, even when its due day has already passed this month."""
    early = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    # Prod case: 30 آبان, loan due 30 آذر, entered earlier.
    assert ds.this_month_installments([D(6, 1405, 9, 30, 10_000_000, early)], LAST) == Decimal("0")
    assert ds.this_month_installments([D(6, 1405, 9, 13, 10_000_000, early)], TODAY) == Decimal("0")
    assert ds.this_month_installments([D(6, 1405, 9, 5, 2000)], TODAY) == Decimal("0")


def test_this_month_loan_is_counted():
    assert ds.this_month_installments([D(5, 1405, 8, 20, 2_000_000)], TODAY) == Decimal("2000000")
    assert ds.this_month_installments([D(5, 1405, 8, 10, 2_000_000)], TODAY) == Decimal("2000000")
    assert ds.this_month_installments([D(3, 1405, 8, 30, 1000)], LAST) == Decimal("1000")


def test_overdue_loan_adds_only_this_month_slice():
    late = D(5, 1405, 6, 10, 1000)
    assert ds.month_due([late], TODAY) == (Decimal("3000"), Decimal("3000"))
    assert ds.this_month_installments([late], TODAY) == Decimal("1000")
    # Earlier-month overdue plus a this-month unpaid plus a next-month unpaid.
    debts = [D(5, 1405, 6, 10, 1_000_000), D(3, 1405, 8, 30, 2_000_000), D(4, 1405, 9, 30, 10_000_000)]
    assert ds.this_month_installments(debts, LAST) == Decimal("3000000")
    assert ds.month_due(debts, LAST)[0] == Decimal("5000000")


def test_month_boundary_last_day_and_next_first():
    end = jdatetime.date(1405, 8, 30)
    start = jdatetime.date(1405, 9, 1)
    this_month = D(1, 1405, 8, 30, 1000)
    next_month = D(3, 1405, 9, 1, 2000)
    assert ds.this_month_installments([this_month, next_month], end) == Decimal("1000")
    assert ds.this_month_installments([this_month, next_month], start) == Decimal("2000")
    # Year wrap: 29 اسفند / 1 فروردین.
    esf = jdatetime.date(1405, 12, 29)
    far = jdatetime.date(1406, 1, 1)
    assert ds.this_month_installments([D(2, 1405, 12, 29, 400)], esf) == Decimal("400")
    assert ds.this_month_installments([D(2, 1406, 1, 1, 500)], esf) == Decimal("0")
    assert ds.this_month_installments([D(2, 1406, 1, 1, 500)], far) == Decimal("500")


def test_overdue_unit_is_not_glued_to_toman(client, no_network, clock):  # noqa: F811
    from tests.test_debts_v2 import P, _seed
    from tests.test_holdings import _register

    _register(client)
    _seed([("عقب", 1000000, 5, 1405, 6, 1)])
    html = client.get(P).text
    assert "تومانشامل" not in html
    assert 'data-installment-overdue' in html
    assert "تومان</small> <small class=\"dv-unit\" data-installment-overdue>" in html


def test_mid_loan_paid_this_month_still_counts():
    """After «پرداخت شد» the due date is next month, but last_paid_on is this month, so it still counts."""
    paid = D(4, 1405, 9, 20, 2_000_000, last_paid=TODAY.togregorian())
    assert ds.this_month_installments([paid], TODAY) == Decimal("2000000")
    assert ds.this_month_installments([paid], LAST) == Decimal("2000000")
    # Jalali last_paid_on is accepted the same way as the stored Gregorian date.
    assert ds.this_month_installments([D(4, 1405, 9, 20, 2_000_000, last_paid=TODAY)], TODAY) == Decimal("2000000")
    # 5M salary, 2M mid-loan pay, no other costs → 3M left.
    assert ds.salary_left(5_000_000, [paid], 0, TODAY) == Decimal("3000000")
    unpaid = D(5, 1405, 8, 20, 2_000_000)
    assert ds.this_month_installments([unpaid], TODAY) == ds.this_month_installments([paid], TODAY)


def test_mid_loan_undo_stops_using_the_cleared_date():
    paid = D(4, 1405, 9, 20, 2_000_000, last_paid=TODAY.togregorian())
    undone = D(5, 1405, 8, 20, 2_000_000, last_paid=None)
    assert ds.this_month_installments([paid], TODAY) == Decimal("2000000")
    assert ds.this_month_installments([undone], TODAY) == Decimal("2000000")
    # A previous month's payment is restored on undo: next-month due must not count.
    restored_old = D(4, 1405, 9, 20, 2_000_000, last_paid=jdatetime.date(1405, 7, 20).togregorian())
    assert ds.this_month_installments([restored_old], TODAY) == Decimal("0")


def test_loan_starting_next_month_is_not_counted_even_after_due_day():
    early = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    starts = D(6, 1405, 9, 30, 10_000_000, early)
    assert ds.this_month_installments([starts], LAST) == Decimal("0")
    assert ds.this_month_installments([starts], TODAY) == Decimal("0")
    # Mid-loan pay and a next-month loan together: only the paid one counts.
    paid = D(4, 1405, 9, 20, 2_000_000, last_paid=TODAY.togregorian())
    assert ds.this_month_installments([paid, starts], TODAY) == Decimal("2000000")


def test_last_instalment_paid_this_month_still_counts():
    finished = D(0, 1405, 9, 25, 700, last_paid=TODAY.togregorian())
    assert ds.this_month_installments([finished], TODAY) == Decimal("700")
    # Pre-deploy final payment (no last_paid_on) still counts via the stored next month.
    assert ds.this_month_installments([D(0, 1405, 9, 25, 700)], TODAY) == Decimal("700")


def test_overdue_plus_mid_loan_pay():
    late = D(5, 1405, 6, 10, 1_000_000)
    paid = D(4, 1405, 9, 30, 2_000_000, last_paid=LAST.togregorian())
    starts = D(4, 1405, 9, 30, 10_000_000)
    assert ds.this_month_installments([late, paid, starts], LAST) == Decimal("3000000")
    assert ds.month_due([late, paid, starts], LAST)[0] == Decimal("3000000")


def test_year_boundary_paid_this_month_and_next_year_start():
    esf = jdatetime.date(1405, 12, 29)
    far = jdatetime.date(1406, 1, 1)
    paid = D(4, 1406, 1, 10, 400, last_paid=esf.togregorian())
    starts = D(6, 1406, 1, 10, 500)
    assert ds.this_month_installments([paid], esf) == Decimal("400")
    assert ds.this_month_installments([starts], esf) == Decimal("0")
    # On 1 Farvardin the Esfand payment is no longer this month; the Farvardin instalment is now due.
    assert ds.this_month_installments([paid], far) == Decimal("400")
    assert ds.this_month_installments([starts], far) == Decimal("500")
    # Unpaid Esfand loan still counts on the last day of the year.
    assert ds.this_month_installments([D(2, 1405, 12, 29, 400)], esf) == Decimal("400")
