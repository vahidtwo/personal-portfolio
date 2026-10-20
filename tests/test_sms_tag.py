"""«از پیامک» tag on spends saved from bank SMS."""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _sms_spend(client, note):
    r = client.post("/api/sms-spend", json={"amount_toman": "350000", "note": note, "idempotency_key": "a" * 64})
    assert r.status_code == 200 and r.json()["ok"]


def test_sms_spend_shows_tag_and_hides_internal_key(client, no_network):
    _register(client)
    _sms_spend(client, "برداشت از کارت **** خرید فروشگاه نمونه")
    html = client.get("/dashboard?tab=daily").text
    assert '<span class="tag tag-sms" title="ثبت خودکار از پیامک">از پیامک</span>' in html
    assert "[" + "a" * 64 + "]" not in html.split("<tbody>")[1].split("</tbody>")[0]
    assert "برداشت از کارت **** خرید فروشگاه نمونه" in html


def test_manual_spend_has_no_tag(client, no_network):
    from app.spends import sms_spend_parts
    assert sms_spend_parts("[" + "b" * 64 + "] x", "sms_bank") == (True, "x")
    assert sms_spend_parts("[" + "b" * 64 + "] x", "food") == (False, "[" + "b" * 64 + "] x")
    assert sms_spend_parts("نان", "sms_bank") == (False, "نان")
    assert sms_spend_parts(None, None) == (False, "")
