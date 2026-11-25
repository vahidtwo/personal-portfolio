"""Landing and SMS-settings copy matches the agreed rule (paths A, B and W)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The agreed copy uses the minus sign (U+2212) in «(−)», not an ASCII hyphen.
MINUS = "\u2212"
LANDING = (
    "دارایی‌تو خرج‌هایت را از پیامک بانک ثبت می‌کند: هر پیامکی که مبلغ منفی ("
    + MINUS
    + ") و «مانده» دارد. با کلمه‌های خودت، پیامک‌های بدون «مانده» یا با «برداشت» هم ثبت می‌شوند."
)
SETTINGS = (
    "پیامکِ دارای مبلغ منفی ("
    + MINUS
    + ") و خط «مانده» خودکار ثبت می‌شود. اگر یکی از کلمه‌های شما در پیامک باشد، مبلغ منفی بدون «مانده» یا «برداشت» کنار مبلغ هم ثبت می‌شود. بقیهٔ پیامک‌ها نادیده گرفته می‌شوند."
)
OLD = "کلمهٔ انتخابی شما"
ASCII_MARK = "(-)"


def test_copy_uses_minus_sign_not_ascii_hyphen():
    assert MINUS == "\u2212"
    assert f"({MINUS})" in LANDING
    assert f"({MINUS})" in SETTINGS
    assert ASCII_MARK not in LANDING
    assert ASCII_MARK not in SETTINGS


def test_landing_sms_copy(client):
    html = client.get("/").text
    assert LANDING in html
    assert f"مبلغ منفی ({MINUS})" in html
    assert "مبلغ منفی (-)" not in html
    assert OLD not in html
    assert "خرج روزانه ثبت می‌شود" not in html


def test_web_sms_settings_copy(client):
    from tests.test_holdings import _register

    _register(client)
    html = client.get("/profile").text
    assert SETTINGS in html
    assert f"مبلغ منفی ({MINUS})" in html
    assert "مبلغ منفی (-)" not in html
    assert 'id="android-sms-legacy-desc"' in html
    assert "عبارت زیر برای فیلتر پیامک بانکی" not in html


def test_android_sms_settings_copy():
    src = (ROOT / "android/app/src/main/java/app/myinventory/SmsSettingsActivity.kt").read_text(encoding="utf-8")
    assert src.count(SETTINGS) >= 3
    assert f"مبلغ منفی ({MINUS})" in src
    assert "مبلغ منفی (-)" not in src
    assert "یکی از کلمه‌های زیر و یک مبلغ" not in src
    assert "یکی از این کلمه‌ها و یک مبلغ" not in src
    assert "از این نسخه فقط پیامک‌هایی ثبت می‌شوند که یکی از کلمه‌های شما و یک مبلغ را دارند" not in src
