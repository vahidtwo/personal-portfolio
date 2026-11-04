"""Long SMS notes keep the merchant ahead of the key."""
import re

from tests.test_holdings import _register, no_network  # noqa: F401

KEY = "c" * 64
LONG = (
    "بانک ملت برداشت از کارت ****-1234 مبلغ -1,250,000 ریال تاریخ 1405/08/13 ساعت 10:21 "
    "پایانه 99887766 کد پیگیری 556677 بابت خرید از فروشگاه آزمایشی مرکزی مانده 12,345,678 ریال"
)


def _stored():
    from app.db import SessionLocal
    from app.models import DailySpend

    with SessionLocal() as db:
        return [r.note for r in db.query(DailySpend).order_by(DailySpend.id).all()]


def test_merchant_first_then_key_and_fits():
    from app.spends import SMS_NOTE_MAX, sms_note_for_storage, sms_note_key

    note = sms_note_for_storage(LONG, KEY)
    assert len(note) <= SMS_NOTE_MAX
    assert note.startswith("فروشگاه آزمایشی مرکزی [" + KEY + "]")
    merchant, text = sms_note_key(note)
    assert merchant == "فروشگاه آزمایشی مرکزی" and text.startswith("بانک ملت")


def test_no_more_digits_than_the_sms_text():
    from app.spends import sms_note_for_storage, sms_note_key

    merchant, _ = sms_note_key(sms_note_for_storage(LONG, KEY))
    assert not re.search(r"[0-9۰-۹٠-٩*]", merchant)


def test_no_merchant_keeps_old_layout():
    from app.spends import sms_note_for_storage

    assert sms_note_for_storage("برداشت -50,000 ریال", KEY) == f"[{KEY}] برداشت -50,000 ریال"
    assert sms_note_for_storage("abc", "") == "abc"


def test_old_format_notes_still_parse():
    from app.spends import sms_spend_parts

    assert sms_spend_parts(f"[{KEY}] خرید نان", "sms_bank") == (True, "خرید نان")
    assert sms_spend_parts(f"[{KEY}]", "sms_bank") == (True, "")
    assert sms_spend_parts("نان", "sms_bank") == (False, "نان")
    assert sms_spend_parts(f"[{KEY}] x", "food") == (False, f"[{KEY}] x")


def test_api_long_sms_merchant_survives_tag_and_dedup(client, no_network):
    _register(client)
    body = {"amount_toman": "125000", "note": LONG, "idempotency_key": KEY}
    first = client.post("/api/sms-spend", json=body).json()
    again = client.post("/api/sms-spend", json=body).json()
    assert first["ok"] and again.get("duplicate") and again["id"] == first["id"]
    notes = _stored()
    assert len(notes) == 1 and len(notes[0]) <= 120 and "فروشگاه آزمایشی مرکزی" in notes[0]
    html = client.get("/dashboard?tab=daily").text
    assert "از پیامک" in html and "فروشگاه آزمایشی مرکزی" in html and KEY not in html


def test_dedup_matches_old_layout_rows(client, no_network):
    _register(client)
    client.get("/dashboard?tab=daily")
    from app.db import SessionLocal
    from app.models import DailySpend, SpendCategory

    from datetime import date

    with SessionLocal() as db:
        cat = db.query(SpendCategory).filter(SpendCategory.slug == "sms_bank").one()
        old = DailySpend(user_id=cat.user_id, category_id=cat.id, amount_toman=125000,
                         spent_on=date(2026, 11, 1), note=f"[{KEY}] بانک ملت برداشت")
        db.add(old)
        db.commit()
        old_id = old.id
    r = client.post("/api/sms-spend", json={"amount_toman": "125000", "note": LONG, "idempotency_key": KEY}).json()
    assert r["duplicate"] and r["id"] == old_id
    assert _stored() == [f"[{KEY}] بانک ملت برداشت"]
