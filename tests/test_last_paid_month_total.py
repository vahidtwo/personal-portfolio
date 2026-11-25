"""Mid-loan «پرداخت شد» this month still counts in «جمع اقساط این ماه»; undo restores last_paid_on."""
from datetime import date

from tests.amounts_helper import amounts_for
from tests.test_debts_v2 import P, _seed, clock  # noqa: F401
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401


def _last_paid(debt_id):
    from app.db import SessionLocal
    from app.models import Debt

    db = SessionLocal()
    try:
        return db.get(Debt, debt_id).last_paid_on
    finally:
        db.close()


def test_mid_loan_pay_this_month_stays_in_the_total_and_undo_clears_it(client, no_network, clock):  # noqa: F811
    """On 28 مهر a Mehr loan still counts after «پرداخت شد», and undo puts last_paid_on back to NULL."""
    from tests.test_debts_v2 import _debt

    _register(client)
    (debt_id,) = _seed([("وام مهر", 2000000, 5, 1405, 7, 20)], salary=5_000_000)
    before = amounts_for(client, P)
    assert before["installments-month"] == "۲٬۰۰۰٬۰۰۰"
    assert client.get("/api/salary").json()["left"] == "۳٬۰۰۰٬۰۰۰"
    assert _last_paid(debt_id) is None

    t = _csrf(client, P)
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "5", "csrf": t})
    assert _debt(debt_id) == (4, 1405, 8, 20)
    assert _last_paid(debt_id) == date(2026, 10, 20)  # 28 مهر 1405 in Tehran
    after = amounts_for(client, P)
    assert after["installments-month"] == "۲٬۰۰۰٬۰۰۰"
    assert client.get("/api/salary").json()["left"] == "۳٬۰۰۰٬۰۰۰"

    client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": t})
    assert _debt(debt_id) == (5, 1405, 7, 20)
    assert _last_paid(debt_id) is None
    undone = amounts_for(client, P)
    assert undone["installments-month"] == "۲٬۰۰۰٬۰۰۰"
    assert client.get("/api/salary").json()["left"] == "۳٬۰۰۰٬۰۰۰"


def test_undo_restores_the_previous_last_paid_on(client, no_network, clock):  # noqa: F811
    from app.db import SessionLocal
    from app.models import Debt
    from tests.test_debts_v2 import _debt

    _register(client)
    (debt_id,) = _seed([("وام مهر", 2000000, 5, 1405, 7, 20)])
    db = SessionLocal()
    db.get(Debt, debt_id).last_paid_on = date(2026, 9, 21)  # a previous month
    db.commit()
    db.close()

    t = _csrf(client, P)
    client.post(f"/profile/debts/{debt_id}/paid", data={"expect": "5", "csrf": t})
    assert _last_paid(debt_id) == date(2026, 10, 20)
    client.post(f"/profile/debts/{debt_id}/unpaid", data={"csrf": t})
    assert _debt(debt_id) == (5, 1405, 7, 20)
    assert _last_paid(debt_id) == date(2026, 9, 21)


def test_next_month_loan_stays_out_of_the_total(client, no_network, clock):  # noqa: F811
    _register(client)
    _seed([("از آبان", 2000000, 6, 1405, 8, 5)], salary=5_000_000)
    amounts = amounts_for(client, P)
    assert amounts["installments-month"] == "۰"
    assert client.get("/api/salary").json()["left"] == "۵٬۰۰۰٬۰۰۰"
