"""SMS offer card on the spends tab (Android v7 bridge getSmsAutoState)."""
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def test_sms_offer_card_markup(client, no_network):
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    card = html[html.index('id="sms-offer"') - 60:]
    assert 'hidden>' in card[:200]  # hidden until the Android app says the feature is off
    assert "خرج‌ها خودکار ثبت شوند؟" in card and "فعال کردن" in card and "نه، ممنون" in card
    assert 'aria-label="بستن این پیشنهاد"' in card
    js = (ROOT / "app" / "static" / "sms-offer.js").read_text(encoding="utf-8")
    assert "getSmsAutoState" in js and "localStorage" in js and '!== "off"' in js
