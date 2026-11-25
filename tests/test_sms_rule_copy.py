"""Landing and SMS-settings copy matches the agreed rule (paths A, B and W)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = "دارایی‌تو خرج‌هایت را از پیامک بانک ثبت می‌کند: هر پیامکی که مبلغ منفی (−) و «مانده» دارد. با کلمه‌های خودت، پیامک‌های بدون «مانده» یا با «برداشت» هم ثبت می‌شوند."
SETTINGS = "پیامکِ دارای مبلغ منفی (−) و خط «مانده» خودکار ثبت می‌شود. اگر یکی از کلمه‌های شما در پیامک باشد، مبلغ منفی بدون «مانده» یا «برداشت» کنار مبلغ هم ثبت می‌شود. بقیهٔ پیامک‌ها نادیده گرفته می‌شوند."
OLD = "کلمهٔ انتخابی شما"


def test_landing_sms_copy(client):
    html = client.get("/").text
    assert LANDING in html
    assert OLD not in html
    assert "خرج روزانه ثبت می‌شود" not in html


def test_web_sms_settings_copy(client):
    from tests.test_holdings import _register

    _register(client)
    html = client.get("/profile").text
    assert SETTINGS in html
    assert 'id="android-sms-legacy-desc"' in html
    assert "عبارت زیر برای فیلتر پیامک بانکی" not in html


def test_android_sms_settings_copy():
    src = (ROOT / "android/app/src/main/java/app/myinventory/SmsSettingsActivity.kt").read_text(encoding="utf-8")
    assert src.count(SETTINGS) >= 3
    assert "یکی از کلمه‌های زیر و یک مبلغ" not in src
    assert "یکی از این کلمه‌ها و یک مبلغ" not in src
    assert "از این نسخه فقط پیامک‌هایی ثبت می‌شوند که یکی از کلمه‌های شما و یک مبلغ را دارند" not in src
