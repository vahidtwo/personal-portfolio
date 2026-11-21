"""JSON settings writes for the native settings tab: same rules and columns as POST /profile/account."""
import json
import logging
from decimal import Decimal

from tests.test_holdings import _register

SALARY = 93_410_000


def _token(client):
    return client.get("/api/auth/csrf").json()["csrf"]


def _send(client, path, body, method="POST", token=None):
    headers = {"X-CSRF-Token": _token(client) if token is None else token}
    return client.request(method, path, json=body, headers=headers)


def _user(username="alice"):
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    user = db.query(User).filter_by(username=username).one()
    out = {"full_name": user.full_name, "username": user.username, "mobile": user.mobile,
           "salary": Decimal(user.salary_toman or 0), "hash": user.password_hash,
           "btc": Decimal(user.btc or 0)}
    db.close()
    return out


def test_writes_need_csrf_and_login(client):
    for path in ("/api/settings/account", "/api/settings/password", "/api/settings/salary"):
        assert client.post(path, json={}).status_code == 400, path
        assert _send(client, path, {}, token="forged").status_code == 400, path
        assert _send(client, path, {}).status_code == 401, path


def test_account_saves_name_and_mobile_only(client):
    _register(client)
    before = _user()
    r = _send(client, "/api/settings/account",
              {"full_name": "  سارا نمونه  ", "username": "alice", "mobile": "۰۹۱۲۰۰۰۰۰۰۰"}, method="PATCH")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["account"] == {"full_name": "سارا نمونه", "username": "alice", "mobile": "09120000000"}
    after = _user()
    assert after["full_name"] == "سارا نمونه" and after["mobile"] == "09120000000"
    assert after["hash"] == before["hash"] and after["salary"] == before["salary"]
    assert "no-store" in r.headers["cache-control"]


def test_account_errors_match_the_web_copy(client):
    from app.profile import CURRENT_PW_MISSING_USER, MOBILE_ERROR, USERNAME_ERROR

    _register(client)
    r = _send(client, "/api/settings/account", {"username": "1x", "mobile": "12"})
    assert r.status_code == 422
    assert r.json()["errors"] == {"username": USERNAME_ERROR, "mobile": MOBILE_ERROR}
    r = _send(client, "/api/settings/account", {"username": "alice2", "mobile": ""})
    assert r.status_code == 422 and r.json()["errors"] == {"current_password": CURRENT_PW_MISSING_USER}
    assert _user()["username"] == "alice"


def test_username_change_needs_the_current_password_and_keeps_the_session(client):
    _register(client)
    r = _send(client, "/api/settings/account", {"username": "alice2", "current_password": "wrongpass1"})
    assert r.status_code == 422 and "current_password" in r.json()["errors"]
    r = _send(client, "/api/settings/account", {"username": "alice2", "current_password": "password123"})
    assert r.status_code == 200 and r.json()["account"]["username"] == "alice2"
    assert client.get("/api/auth/session").json() == {"signed_in": True, "username": "alice2"}
    assert client.cookies.get("inventory_signed_in") == "1"


def test_taken_username_is_refused(client):
    _register(client, "bob")
    client.cookies.clear()
    _register(client)
    r = _send(client, "/api/settings/account", {"username": "bob", "current_password": "password123"})
    assert r.status_code == 422 and "username" in r.json()["errors"]


def test_password_change(client):
    from app.profile import CURRENT_PW_WRONG, PASSWORD_ERROR

    _register(client)
    r = _send(client, "/api/settings/password", {"current_password": "password123", "new_password": "short"})
    assert r.status_code == 422 and r.json()["errors"] == {"new_password": PASSWORD_ERROR}
    r = _send(client, "/api/settings/password", {"current_password": "nope-nope-1", "new_password": "newpass-1234"})
    assert r.status_code == 422 and r.json()["errors"] == {"current_password": CURRENT_PW_WRONG}
    before = _user()
    r = _send(client, "/api/settings/password", {"current_password": "password123", "new_password": "newpass-1234"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "newpass" not in r.text and "password123" not in r.text
    after = _user()
    assert after["hash"] != before["hash"] and after["full_name"] == before["full_name"]
    from app.security import verify_password
    assert verify_password("newpass-1234", after["hash"])


def test_salary_save_never_echoes_the_value(client, caplog):
    _register(client)
    caplog.set_level(logging.DEBUG)
    r = _send(client, "/api/settings/salary", {"salary_toman": "۹۳٬۴۱۰٬۰۰۰"}, method="PATCH")
    assert r.status_code == 200 and r.json() == {"ok": True, "title": "حقوق ذخیره شد",
                                                  "detail": "مبلغ همچنان پنهان است.", "has_salary": True}
    assert _user()["salary"] == Decimal(SALARY)
    for text in (r.text, json.dumps(client.get("/api/settings").json(), ensure_ascii=False), caplog.text):
        assert "93410000" not in text and "۹۳٬۴۱۰٬۰۰۰" not in text
    assert client.get("/api/settings").json()["has_salary"] is True


def test_salary_rules_match_the_web(client):
    from app.profile import SALARY_INVALID, SALARY_WHOLE

    _register(client)
    _send(client, "/api/settings/salary", {"salary_toman": "45000000"})
    r = _send(client, "/api/settings/salary", {"salary_toman": "45000000.5"})
    assert r.status_code == 422 and r.json()["errors"] == {"salary_toman": SALARY_WHOLE}
    r = _send(client, "/api/settings/salary", {"salary_toman": "-5"})
    assert r.status_code == 422 and r.json()["errors"] == {"salary_toman": SALARY_INVALID}
    assert _user()["salary"] == Decimal(45_000_000)
    assert _send(client, "/api/settings/salary", {"salary_toman": ""}).status_code == 200
    assert _user()["salary"] == Decimal(45_000_000)
    _send(client, "/api/settings/salary", {"salary_toman": "0"})
    assert _user()["salary"] == 0 and client.get("/api/settings").json()["has_salary"] is False


def test_settings_writes_touch_no_holdings(client):
    from app.db import SessionLocal
    from app.models import User

    _register(client)
    db = SessionLocal()
    u = db.query(User).filter_by(username="alice").one()
    u.btc = Decimal("0.25")
    db.commit()
    db.close()
    _send(client, "/api/settings/account", {"full_name": "x", "username": "alice"})
    _send(client, "/api/settings/salary", {"salary_toman": "1000"})
    _send(client, "/api/settings/password", {"current_password": "password123", "new_password": "newpass-1234"})
    assert _user()["btc"] == Decimal("0.25")


def test_web_settings_form_still_works(client):
    import re

    _register(client)
    page = client.get("/profile").text
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    r = client.post("/profile/account", data={"section": "account", "full_name": "وب", "username": "alice",
                                              "mobile": "", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and _user()["full_name"] == "وب"
    r = client.post("/profile/account", headers={"Accept": "application/json"},
                    data={"section": "salary", "salary_toman": "1.5", "csrf": csrf})
    assert r.status_code == 422 and "salary_toman" in r.json()["errors"]
