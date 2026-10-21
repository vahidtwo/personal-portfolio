"""Settings v2 (/profile): sections saved on their own, per-field errors, salary privacy, theme per
device (no server state), in-app confirms for logout and MCP revoke."""
import re
from decimal import Decimal
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
JSON = {"Accept": "application/json"}


def _user(name="alice"):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=name).one()
        db.expunge(u)
        return u
    finally:
        db.close()


def _set_salary(value, name="alice"):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    db.query(User).filter_by(username=name).one().salary_toman = Decimal(value)
    db.commit(); db.close()


def _post(client, headers=None, **fields):
    data = {"full_name": "", "username": "alice", "mobile": "", "salary_toman": "", "current_password": "",
            "new_password": "", "csrf": _csrf(client), **fields}
    return client.post("/profile/account", data=data, headers=headers or {}, follow_redirects=False)


def test_sections_and_copy(client, no_network):
    _register(client)
    html = client.get("/profile").text
    assert "<h1>تنظیمات</h1>" in html and "ظاهر، حساب و امنیت. هر بخش جدا ذخیره می‌شود." in html
    for h in ("ظاهر", "حساب", "حقوق ماهانه", "رمز عبور", "اپ و اتصال‌ها"):
        assert re.search(rf'<h2 id="[^"]+">{h}</h2>', html), h
    assert 'role="radiogroup" aria-label="پوسته"' in html
    for value, text in (("dark", "تیره"), ("light", "روشن"), ("auto", "خودکار")):
        assert f'<input type="radio" name="theme_choice" value="{value}">{text}' in html
    assert html.count('data-v2-section="') == 3 and html.count('action="/profile/account"') == 3
    assert "ذخیرهٔ حساب" in html and "تغییر رمز" in html and "ذخیرهٔ حقوق" in html
    assert 'placeholder="0912' not in html and "اختیاری. مثلاً ۰۹۱۲۳۴۵۶۷۸۹" in html
    # «رمز فعلی» in «حساب» is hidden until the username changes
    assert re.search(r'class="v2-field span-2 v2-hide" id="v2-cpw"', html)
    assert 'href="/profile">تنظیمات</a>' in html and "پروفایل" not in html
    assert "چنده</a>، به‌روزرسانی ساعتی" in html
    assert "/static/amount-input.js" in html and "/static/settings-page.js" in html


def test_theme_is_per_device_only(client, no_network):
    _register(client)
    html = client.get("/profile").text
    assert 'name="theme' not in html.split('data-theme-options')[0][-200:]  # radios are not inside any form
    for form in re.findall(r"<form.*?</form>", html, re.S):
        assert "theme_choice" not in form  # never posted to the server
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert 'localStorage.removeItem(STORAGE_KEY)' in js and 'addEventListener("change"' in js
    assert "prefers-color-scheme: light" in js
    assert 'class="theme-toggle-label"' in html and 'aria-label="پوسته: تیره. تغییر به روشن"' in html


def test_salary_masked_never_in_html_and_no_salary_state(client, no_network):
    _register(client)
    html = client.get("/profile").text
    assert "هنوز حقوقی ثبت نکرده‌اید." in html and 'id="v2-eye"' not in html
    assert 'id="v2-salform"' in html and re.search(r'class="v2-form" id="v2-salform"', html)  # field open
    _set_salary("65000000")
    html = client.get("/profile").text
    assert "۶۵٬۰۰۰٬۰۰۰" not in html and "65000000" not in html and "65,000,000" not in html
    assert '<span class="v" id="v2-salv" data-salary-mask>••••••</span>' in html
    assert 'id="v2-eye" aria-pressed="false"' in html and re.search(r'class="v2-form v2-hide" id="v2-salform"', html)
    js = (STATIC / "settings-page.js").read_text(encoding="utf-8")
    assert 'fetch("/api/salary"' in js and '"pagehide", mask' in js and '"pageshow", mask' in js
    assert "localStorage" not in js and "sessionStorage" not in js
    assert client.get("/api/salary").json()["salary"] == "۶۵٬۰۰۰٬۰۰۰"


def test_salary_is_whole_toman_and_decimal_rejected_at_the_field(client, no_network):
    _register(client)
    _post(client, full_name="Ali", mobile="09123456789")
    _set_salary("45000000")
    r = _post(client, headers=JSON, salary_toman="۱٬۵۰۰٫۵", section="salary")
    assert r.status_code == 422
    assert r.json()["errors"] == {"salary_toman": "حقوق را بدون ممیز و به تومان کامل بنویسید؛ مثلاً ۴۵٬۰۰۰٬۰۰۰"}
    html = _post(client, salary_toman="1500.5", section="salary").text
    assert 'id="e-salary_toman"' in html and "بدون ممیز" in html and "1500.5" not in html
    assert Decimal(_user().salary_toman) == Decimal("45000000")
    r = _post(client, salary_toman="۱٬۵۰۰٬۰۰۰", section="salary")
    assert r.status_code == 303
    u = _user()
    assert Decimal(u.salary_toman) == Decimal("1500000") and u.full_name == "Ali" and u.mobile == "09123456789"
    assert "حقوق ذخیره شد" in client.get("/profile").text


def test_legacy_fractional_salary_survives_other_sections(client, no_network):
    """Like old fractional spends (#22): a stored 45000000.5 shows (masked/revealed) and is never touched
    by saving another section; re-sending it unchanged is accepted, only a NEW fraction is rejected."""
    _register(client)
    _set_salary("45000000.5")
    assert client.get("/profile").status_code == 200
    assert client.get("/api/salary").status_code == 200
    assert _post(client, full_name="Ali", section="account").status_code == 303
    assert _post(client, section="salary", salary_toman="").status_code == 303  # empty keeps it
    assert Decimal(_user().salary_toman) == Decimal("45000000.5")
    assert _post(client, section="salary", salary_toman="45000000.5").status_code == 303
    assert Decimal(_user().salary_toman) == Decimal("45000000.5")
    assert _post(client, headers=JSON, section="salary", salary_toman="45000000.7").status_code == 422
    assert Decimal(_user().salary_toman) == Decimal("45000000.5")


def test_salary_save_ignores_bad_stored_mobile_and_other_fields(client, no_network):
    """Review fix: a legacy invalid stored mobile must not block the salary section, and fields of other
    sections posted along (stale hidden copies) are ignored."""
    from app.db import SessionLocal
    from app.models import User
    _register(client)
    db = SessionLocal(); u = db.query(User).filter_by(username="alice").one(); u.mobile = "12345"; u.full_name = "Old"; db.commit(); db.close()
    r = _post(client, headers=JSON, section="salary", salary_toman="50000000", mobile="12345", full_name="Stale",
              username="zzz", new_password="newpassword1")
    assert r.status_code == 200, r.text
    u = _user()
    assert Decimal(u.salary_toman) == Decimal("50000000")
    assert (u.mobile, u.full_name, u.username) == ("12345", "Old", "alice")
    from app.security import verify_password
    assert verify_password("password123", u.password_hash)  # password untouched by the salary save


def test_stale_hidden_name_cannot_revert_other_tab_edit(client, no_network):
    _register(client)
    assert _post(client, full_name="New name from tab B", section="account").status_code == 303
    before_hash = _user().password_hash
    # tab A (stale) saves the password section and still carries the old name
    r = _post(client, section="password", full_name="Old name tab A", current_password="password123",
              new_password="anotherpass9")
    assert r.status_code == 303
    u = _user()
    assert u.full_name == "New name from tab B" and u.password_hash != before_hash
    # and the rendered forms carry no hidden copies of other sections' fields
    html = client.get("/profile").text
    for sec in ("salary", "password"):
        form = re.search(r'<form[^>]*>(?:(?!</form>).)*name="section" value="%s"(?:(?!</form>).)*</form>' % sec, html, re.S).group(0)
        for f in ("full_name", "username", "mobile"):
            assert f'name="{f}"' not in form, (sec, f)


def test_name_only_change_needs_no_password(client, no_network):
    _register(client)
    r = _post(client, headers=JSON, full_name="کاربر نمونه")
    assert r.status_code == 200 and r.json()["title"] == "حساب ذخیره شد"
    assert _user().full_name == "کاربر نمونه"


def test_errors_at_once_and_nothing_saved(client, no_network):
    _register(client)
    before = _user()
    r = _post(client, headers=JSON, username="newname", mobile="۰۹۱۲", full_name="X")
    assert r.status_code == 422
    assert r.json()["errors"] == {
        "mobile": "شماره موبایل ۱۰ تا ۱۵ رقم است؛ مثلاً ۰۹۱۲۳۴۵۶۷۸۹",
        "current_password": "برای تغییر نام کاربری، رمز فعلی را وارد کنید",
    }
    r = _post(client, headers=JSON, section="password", new_password="1234")
    assert r.json()["errors"] == {"new_password": "رمز جدید دست‌کم ۸ نویسه باشد",
                                  "current_password": "برای تغییر رمز، رمز فعلی را وارد کنید"}
    after = _user()
    assert (after.username, after.full_name, after.password_hash) == (before.username, before.full_name, before.password_hash)
    # HTML path: every error at its field plus a linked summary
    html = _post(client, username="2bad", mobile="12").text
    assert "۲ مورد نیاز به اصلاح دارد" in html
    assert 'id="e-username"' in html and 'id="e-mobile"' in html and 'href="#f-username"' in html
    assert 'aria-invalid="true" aria-describedby="e-mobile"' in html


def test_username_change_password_rules(client, no_network):
    _register(client)
    r = _post(client, headers=JSON, username="alice2")
    assert r.json()["errors"] == {"current_password": "برای تغییر نام کاربری، رمز فعلی را وارد کنید"}
    r = _post(client, headers=JSON, username="alice2", current_password="wrong-pass")
    assert r.json()["errors"] == {"current_password": "رمز فعلی درست نیست"}
    r = _post(client, headers=JSON, username="alice2", current_password="password123")
    assert r.status_code == 200 and _user("alice2").username == "alice2"


def test_password_section_changes_password(client, no_network):
    from app.security import verify_password
    _register(client)
    r = _post(client, section="password", current_password="password123", new_password="newpass456")
    assert r.status_code == 303 and verify_password("newpass456", _user().password_hash)
    assert "رمز عبور تغییر کرد" in client.get("/profile").text


def test_logout_and_revoke_use_in_app_dialog(client, no_network):
    _register(client)
    client.post("/profile/mcp-token", data={"csrf": _csrf(client)})
    html = client.get("/profile").text
    assert "confirm(" not in html
    assert html.count('action="/logout" class="settings-row-form" data-confirm="logout"') == 1
    assert 'class="side-logout" data-confirm="logout"' in html and 'data-confirm="revoke"' in html
    assert "/static/confirm-dialog.js" in client.get("/dashboard").text
    js = (STATIC / "confirm-dialog.js").read_text(encoding="utf-8")
    assert "confirm(" not in js.replace("data-confirm", "").replace("dataset.confirm", "")
    assert 'role", "alertdialog"' in js and 'aria-modal", "true"' in js and '"Escape"' in js
    assert "از حساب خارج شوید؟" in js and "توکن MCP غیرفعال شود؟" in js and "cancel.focus()" in js
    # logout itself still works with the same POST
    assert client.post("/logout", data={"csrf": _csrf(client)}, follow_redirects=False).status_code in (302, 303)
