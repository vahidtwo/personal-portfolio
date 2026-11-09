"""«جمع اقساط این ماه» on the debts tab: top of the loans list, same calc as the dashboard, amount only via /api/amounts."""
import re
from datetime import datetime, timezone
from decimal import Decimal

from tests.amounts_helper import amounts_for
from tests.test_debts_v2 import P, _seed, clock  # noqa: F401
from tests.test_holdings import _register, no_network  # noqa: F401


def _seed_loans(client):
    from app.db import SessionLocal
    from app.models import Debt

    _register(client)
    # unpaid this month 1_000_000 + paid this month 500_000 + finished (out) + overdue contributes 200_000 this month only
    _seed([("عقب", 1000000, 5, 1405, 6, 1), ("پرداخت‌شده", 500000, 3, 1405, 8, 10),
           ("تمام", 9000000, 0, 1405, 7, 5), ("باز", 200000, 2, 1405, 7, 30),
           ("آخرین", 700000, 0, 1405, 8, 10)],
          expenses=[("اجاره", 1000000, 5)], salary=10000000)
    db = SessionLocal()
    for debt in db.query(Debt).all():
        debt.created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db.commit()
    db.close()


def test_api_month_total_matches_dashboard_calc(client, no_network, clock):  # noqa: F811
    _seed_loans(client)
    # Same base as test_salary_left (۱٬۷۰۰٬۰۰۰ under the Mehr 28 clock) plus final-paid-this-month ۷۰۰٬۰۰۰.
    from app.formatting import format_toman

    expected = format_toman(Decimal("2400000"))
    amounts = amounts_for(client, P)
    assert amounts["installments-month"] == expected
    dash = amounts_for(client, "/dashboard")
    assert dash["installments-month"] == expected


def test_debts_html_has_no_month_total_amount(client, no_network, clock):  # noqa: F811
    _seed_loans(client)
    html = client.get(P).text
    assert 'data-amt="installments-month"' in html
    assert "۲٬۴۰۰٬۰۰۰" not in html
    assert "2400000" not in html
    assert "2,400,000" not in html
    assert re.search(
        r'<p class="dv-sumrow lead" data-month-total-row><span>جمع اقساط این ماه</span>'
        r'<b class="num"><bdi class="mask-sm" data-mask="portfolio" data-amount data-month-total>'
        r'<span data-amt="installments-month"></span></bdi>',
        html,
    )


def test_month_total_sits_at_top_of_loans_list(client, no_network, clock):  # noqa: F811
    _seed_loans(client)
    html = client.get(P).text
    loans = html[html.index('data-dv-list="debts"'):html.index('data-dv-list="expenses"')]
    assert 'data-month-total-row' in loans
    assert loans.index("data-month-total-row") < loans.index('aria-label="وام و قسط"')
    assert loans.index('aria-label="وام و قسط"') < loans.index("جمع بدهی مانده")
    tiles = html[html.index("dv-tiles"):html.index('data-dv-list="debts"')]
    assert "جمع اقساط این ماه" not in tiles
