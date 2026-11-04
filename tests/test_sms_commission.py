"""SMS spends below the commission limit are filed under «کارمزد»."""
from decimal import Decimal

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

DAILY = "/dashboard?tab=daily"


def _sms(client, amount, key):
    r = client.post("/api/sms-spend", json={"amount_toman": str(amount), "note": "خرید", "idempotency_key": key * 64})
    assert r.status_code == 200 and r.json()["ok"], r.text
    return r.json()["id"]


def _rows(client):
    from app.db import SessionLocal
    from app.models import DailySpend, SpendCategory

    with SessionLocal() as db:
        cats = {c.id: c for c in db.query(SpendCategory).all()}
        spends = {s.id: (cats[s.category_id], Decimal(s.amount_toman)) for s in db.query(DailySpend).all()}
        fee = [c for c in cats.values() if c.name == "کارمزد"]
        return spends, fee


def test_threshold_constant_and_boundary():
    from app.spends import SMS_COMMISSION_MAX_TOMAN, is_sms_commission

    assert SMS_COMMISSION_MAX_TOMAN == Decimal("50000")
    assert is_sms_commission(49999)
    assert is_sms_commission(Decimal("49999.9"))
    assert not is_sms_commission(50000)
    assert not is_sms_commission(50001)


@pytest.mark.parametrize(
    "rial,commission",
    [(499_990, True), (499_999, True), (500_000, False), (500_009, False), (500_010, False)],
)
def test_rial_to_toman_boundary(rial, commission):
    from app.spends import is_sms_commission

    assert is_sms_commission(rial // 10) is commission


def test_sms_spends_split_at_limit_and_category_created_once(client, no_network):
    _register(client)
    a = _sms(client, 49999, "a")
    b = _sms(client, 50000, "b")
    c = _sms(client, 50001, "c")
    d = _sms(client, 1200, "d")
    spends, fee = _rows(client)
    assert len(fee) == 1 and fee[0].parent_id is not None and fee[0].slug == "sms_fee"
    assert spends[a][0].id == fee[0].id and spends[d][0].id == fee[0].id
    assert spends[b][0].slug == "sms_bank" and spends[c][0].slug == "sms_bank"
    html = client.get(DAILY).text
    assert "کارمزد" in html and "a" * 64 not in html


def test_existing_category_with_exact_name_is_reused(client, no_network):
    _register(client)
    from app.db import SessionLocal
    from app.models import SpendCategory

    client.get(DAILY)
    with SessionLocal() as db:
        parent = db.query(SpendCategory).filter(SpendCategory.slug == "bills").one()
        mine = SpendCategory(user_id=parent.user_id, parent_id=parent.id, name="کارمزد", sort_order=9)
        db.add(mine)
        db.commit()
        mine_id = mine.id
    a = _sms(client, 300, "a")
    spends, fee = _rows(client)
    assert [c.id for c in fee] == [mine_id]
    assert spends[a][0].id == mine_id


def test_duplicate_sms_does_not_duplicate(client, no_network):
    _register(client)
    first = _sms(client, 500, "a")
    again = _sms(client, 500, "a")
    spends, fee = _rows(client)
    assert first == again and len(spends) == 1 and len(fee) == 1


def test_manual_small_spend_unaffected_and_user_can_recategorize(client, no_network):
    _register(client)
    from app.db import SessionLocal
    from app.models import SpendCategory

    sid = _sms(client, 2000, "a")
    with SessionLocal() as db:
        food = db.query(SpendCategory).filter(SpendCategory.parent_id.isnot(None), SpendCategory.slug != "sms_bank",
                                              SpendCategory.slug != "sms_fee").order_by(SpendCategory.id).first()
        food_id, parent_id = food.id, food.parent_id
    import jdatetime

    t = jdatetime.date.today()
    form = {"amount_toman": "2000", "year": str(t.year), "month": str(t.month), "day": str(t.day),
            "parent_id": str(parent_id), "category_id": str(food_id), "note": "نان"}
    r = client.post("/profile/spends", data={**form, "csrf": _csrf(client, DAILY)}, follow_redirects=False)
    assert r.status_code == 303
    r = client.post(f"/profile/spends/{sid}", data={**form, "note": "x", "csrf": _csrf(client, DAILY)},
                    follow_redirects=False)
    assert r.status_code == 303
    spends, fee = _rows(client)
    assert all(cat.id == food_id for cat, _ in spends.values())
    assert len(spends) == 2 and len(fee) == 1


@pytest.mark.parametrize("name", ["\u0643\u0627\u0631\u0645\u0632\u062f", "  \u06a9\u0627\u0631\u200c\u0645\u0632\u062f ", "\u06a9\u0627\u0631 \u0645\u0632\u062f"])
def test_variant_names_are_reused(client, no_network, name):
    _register(client)
    from app.db import SessionLocal
    from app.models import SpendCategory

    client.get(DAILY)
    with SessionLocal() as db:
        parent = db.query(SpendCategory).filter(SpendCategory.slug == "bills").one()
        mine = SpendCategory(user_id=parent.user_id, parent_id=parent.id, name=name, sort_order=9)
        db.add(mine)
        db.commit()
        mine_id = mine.id
    a = _sms(client, 300, "a")
    b = _sms(client, 400, "b")
    with SessionLocal() as db:
        assert db.query(SpendCategory).filter(SpendCategory.slug == "sms_fee").count() == 0
        assert db.query(SpendCategory).filter(SpendCategory.name == "\u06a9\u0627\u0631\u0645\u0632\u062f").count() == 0
    spends, _ = _rows(client)
    assert spends[a][0].id == mine_id and spends[b][0].id == mine_id
