"""Settings current-password check: one attempt limit for web and app; a password change rotates the session."""
from fastapi.testclient import TestClient

from tests.test_holdings import _csrf, _register


def _token(client):
    return client.get("/api/auth/csrf").json()["csrf"]


def _app_pw(client, current, new="new-password-123"):
    return client.post("/api/settings/password", json={"current_password": current, "new_password": new},
                       headers={"X-CSRF-Token": _token(client)})


def _web_pw(client, current, new="new-password-123", json=False):
    headers = {"Accept": "application/json"} if json else {}
    return client.post("/profile/account", data={"section": "password", "current_password": current,
                                                 "new_password": new, "csrf": _csrf(client)}, headers=headers)


def _limit():
    from app import rate_limit

    return rate_limit.LOGIN_FAILS_PER_USER


def _hash(username):
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        return db.query(User).filter_by(username=username).one().password_hash


def test_app_and_web_share_one_limit_with_retry_after(client):
    _register(client, "fake_guard_a")
    for i in range(_limit()):
        r = _app_pw(client, "wrong-pass") if i % 2 else _web_pw(client, "wrong-pass", json=True)
        assert r.status_code == 422, i
    before = _hash("fake_guard_a")
    app = _app_pw(client, "password123")
    assert app.status_code == 429 and int(app.headers["retry-after"]) > 0
    assert app.json()["retry_after"] > 0 and "دقیقه" in app.json()["errors"]["current_password"]
    web_json = _web_pw(client, "password123", json=True)
    assert web_json.status_code == 429 and int(web_json.headers["retry-after"]) > 0
    page = _web_pw(client, "password123")
    assert page.status_code == 429 and "retry-after" in page.headers
    assert "چند بار پشت سر هم اشتباه شد" in page.text
    username = client.post("/api/settings/account", json={"username": "fake_guard_a2", "current_password": "password123"},
                           headers={"X-CSRF-Token": _token(client)})
    assert username.status_code == 429
    assert _hash("fake_guard_a") == before


def test_right_password_resets_the_count(client):
    _register(client, "fake_guard_b")
    for _ in range(_limit() - 1):
        assert _app_pw(client, "wrong-pass").status_code == 422
    assert _app_pw(client, "password123", new="second-pass-123").status_code == 200
    for _ in range(_limit() - 1):
        assert _web_pw(client, "wrong-pass", json=True).status_code == 422
    assert _app_pw(client, "second-pass-123", new="third-pass-123").status_code == 200


def test_other_users_are_not_affected(client):
    _register(client, "fake_guard_c")
    for _ in range(_limit()):
        _app_pw(client, "wrong-pass")
    assert _app_pw(client, "password123").status_code == 429
    client.post("/logout", data={"csrf": _csrf(client)})
    _register(client, "fake_guard_d")
    assert _app_pw(client, "password123").status_code == 200


def test_password_change_rotates_session_and_drops_old_ones(client):
    _register(client, "fake_guard_e")
    old_device = TestClient(client.app)
    old_device.cookies.update(client.cookies)
    assert old_device.get("/api/settings").status_code == 200
    old_cookie = client.cookies.get("inventory_session")
    r = _app_pw(client, "password123")
    assert r.status_code == 200
    assert client.cookies.get("inventory_session") != old_cookie
    assert client.cookies.get("inventory_signed_in") == "1"
    assert client.get("/api/settings").status_code == 200
    assert old_device.get("/api/settings").status_code == 401


def test_web_password_change_keeps_this_browser_signed_in(client):
    _register(client, "fake_guard_f")
    old_device = TestClient(client.app)
    old_device.cookies.update(client.cookies)
    r = _web_pw(client, "password123", json=True)
    assert r.status_code == 200 and r.json()["title"] == "رمز عبور تغییر کرد"
    assert client.get("/api/settings").status_code == 200
    assert old_device.get("/api/settings").status_code == 401


def test_other_changes_keep_the_session(client):
    _register(client, "fake_guard_g")
    old_device = TestClient(client.app)
    old_device.cookies.update(client.cookies)
    r = client.post("/api/settings/salary", json={"salary_toman": "1000"}, headers={"X-CSRF-Token": _token(client)})
    assert r.status_code == 200
    assert old_device.get("/api/settings").status_code == 200


def test_a_new_login_is_stamped_at_once(client):
    _register(client, "fake_guard_h")
    other = TestClient(client.app)
    r = other.post("/api/auth/continue", json={"username": "fake_guard_h", "password": "password123"},
                   headers={"X-CSRF-Token": _token(other)})
    assert r.status_code == 200
    assert _app_pw(client, "password123").status_code == 200
    assert other.get("/api/settings").status_code == 401
