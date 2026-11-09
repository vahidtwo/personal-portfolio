"""Bank SMS that writes «برداشت» directly against its amount: the stored note keeps no account, balance or format word."""
import re

from tests.test_holdings import _register, no_network  # noqa: F401

KEY = "d" * 64
# What the app sends for «حساو<account>\nبرداشت<amount>\nمانده<balance>\n<date>» once the note is cleaned.
NOTE = "حساو**** برداشت260,000,****/08/18-19:45"
NOTE_FA = "حساو**** برداشت۲۶۰٬۰۰۰٬****/۰۸/۱۸-۱۹:۴۵"


def test_format_words_are_not_a_merchant():
    from app.spends import sms_note_text

    assert sms_note_text(NOTE) == ""
    assert sms_note_text(NOTE_FA) == ""
    assert sms_note_text("حساو1234567890\nبرداشت260,000,700\nمانده9,876,543\n05/08/18-19:45") == ""


def test_stored_note_has_no_merchant_and_old_layout(client, no_network):
    from app.db import SessionLocal
    from app.models import DailySpend
    from app.spends import sms_spend_parts

    _register(client, "glued")
    r = client.post("/api/sms-spend", json={"amount_toman": "26000070", "note": NOTE, "idempotency_key": KEY})
    assert r.status_code == 200 and r.json()["ok"] is True
    with SessionLocal() as db:
        row = db.query(DailySpend).one()
        assert row.amount_toman == 26000070
        assert row.note == f"[{KEY}] {NOTE}"
        assert not re.search(r"1234567890|9,876,543|9876543|مانده", row.note)
        assert sms_spend_parts(row.note, "sms_bank") == (True, "")
