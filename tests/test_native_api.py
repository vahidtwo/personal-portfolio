"""Phase 4 JSON auth and home API for the native Android screens."""


def _csrf(client):
    return client.get("/api/auth/csrf").json()["csrf"]


def _post(client, path, body, csrf=None):
    token = _csrf(client) if csrf is None else csrf
    return client.post(path, json=body, headers={"X-CSRF-Token": token})


def _signup(client, username="alice", password="password123"):
    r = _post(client, "/api/auth/continue", {"username": username, "password": password})
    assert r.json()["result"] == "stepb"
    r = _post(client, "/api/auth/create", {"password_confirm": password})
    assert r.json()["result"] == "ok"
    return r


def test_csrf_required(client):
    r = client.post("/api/auth/continue", json={"username": "alice", "password": "password123"})
    assert r.status_code == 400
    r = _post(client, "/api/auth/continue", {"username": "alice", "password": "password123"}, csrf="forged")
    assert r.status_code == 400
    _signup(client)
    assert client.post("/api/auth/logout").status_code == 400


def test_signup_login_session_and_cookies(client):
    from app.db import SessionLocal
    from app.models import User

    r = _post(client, "/api/auth/continue", {"username": "alice", "password": "password123"})
    assert r.json()["result"] == "stepb"
    db = SessionLocal()
    assert db.query(User).count() == 0
    db.close()
    r = _post(client, "/api/auth/create", {"password_confirm": "password123"})
    assert r.json() == {"result": "ok", "username": "alice", "focus": "", "retry_after": 0, "message": "", "sub": ""}
    assert client.cookies.get("inventory_signed_in") == "1"
    assert client.cookies.get("inventory_session") and client.cookies.get("inventory_page_key")
    assert client.get("/api/auth/session").json() == {"signed_in": True, "username": "alice"}
    assert client.get("/dashboard", follow_redirects=False).status_code == 200
    assert _post(client, "/api/auth/logout", {}).json()["result"] == "ok"
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    r = _post(client, "/api/auth/continue", {"username": "alice", "password": "password123"})
    assert r.json()["result"] == "ok" and client.cookies.get("inventory_signed_in") == "1"


def test_wrong_password_is_generic_and_locks(client):
    _signup(client)
    _post(client, "/api/auth/logout", {})
    for _ in range(10):
        r = _post(client, "/api/auth/continue", {"username": "alice", "password": "wrongpass1"})
        assert r.json()["result"] == "wrong" and r.json()["message"] == "نام کاربری یا رمز درست نیست."
    r = _post(client, "/api/auth/continue", {"username": "alice", "password": "password123"})
    assert r.status_code == 429 and r.json()["result"] == "locked"
    assert int(r.headers["Retry-After"]) > 0 and r.json()["retry_after"] > 0
    assert "دقیقهٔ دیگر" in r.json()["sub"]


def test_badname_shortpw_mismatch(client):
    assert _post(client, "/api/auth/continue", {"username": "1x", "password": "password123"}).json()["result"] == "badname"
    assert _post(client, "/api/auth/continue", {"username": "bob", "password": "short"}).json()["result"] == "shortpw"
    assert _post(client, "/api/auth/continue", {"username": "bob", "password": "password123"}).json()["result"] == "stepb"
    assert _post(client, "/api/auth/create", {"password_confirm": "other12345"}).json()["result"] == "mismatch"


def test_home_requires_login_and_has_no_salary(client):
    assert client.get("/api/home").status_code == 401
    _signup(client)
    r = client.get("/api/home")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["empty"] is True and data["rows"] == [] and data["username"] == "alice"
    for key in ("net", "assets_total", "debt_total", "usd", "changes", "price", "month_spend"):
        assert key in data
    text = r.text.lower()
    assert "salary" not in text and "مانده" not in text and "income" not in text


def test_home_rows_have_no_asset_colour():
    """Mini charts are coloured by trend in the app, so /api/home rows carry no `color`."""
    import inspect

    from app import native_api

    src = inspect.getsource(native_api)
    assert '"color":' not in src and "ASSET_SPARKLINE_COLORS" not in src
