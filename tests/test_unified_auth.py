"""Phase 3 unified sign-in (/auth): login, new-account confirm step, errors, rate limit, redirects."""
import re

from app.formatting import persian_digits  # noqa: F401


def _csrf(client, path="/auth"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def _continue(client, username, password):
    return client.post("/auth/continue", data={"username": username, "password": password, "csrf": _csrf(client)},
                       follow_redirects=False)




def _signup(client, username="newuser", password="password123"):
    r = _continue(client, username, password)
    assert r.status_code == 200 and "حساب تازه بسازیم؟" in r.text and username in r.text
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    return client.post("/auth/create", data={"password_confirm": password, "csrf": csrf}, follow_redirects=False)


def test_old_routes_redirect_to_auth(client):
    for path in ("/login", "/register"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/auth"
    page = client.get("/auth").text
    assert "ورود یا ساخت حساب" in page and "ادامه" in page
    assert "رمزتان را فراموش کردید؟ مدیر سایت می‌تواند آن را بازنشانی کند." in page
    assert 'autocomplete="username"' in page and 'autocomplete="current-password"' in page


def test_new_user_confirm_step_then_create(client):
    from app.db import SessionLocal
    from app.models import User

    r = _continue(client, "newuser", "password123")
    assert "حساب تازه بسازیم؟" in r.text and 'autocomplete="new-password"' in r.text
    db = SessionLocal()
    assert db.query(User).count() == 0  # nothing created before «ساخت حساب»
    db.close()
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    bad = client.post("/auth/create", data={"password_confirm": "different1", "csrf": csrf}, follow_redirects=False)
    assert "دو رمز یکی نیستند." in bad.text and "رمز را یک بار دیگر بنویسید، یا برگردید و از اول بنویسید." in bad.text and 'role="alert"' in bad.text
    ok = client.post("/auth/create", data={"password_confirm": "password123", "csrf": csrf}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/assets"
    assert client.get("/dashboard").status_code == 200
    db = SessionLocal()
    assert [u.username for u in db.query(User).all()] == ["newuser"]
    db.close()


def test_back_keeps_username(client):
    _continue(client, "keepme", "password123")
    page = client.get("/auth?back=1").text
    assert 'value="keepme"' in page and "حساب تازه بسازیم؟" not in page


def test_password_never_in_url_or_page(client):
    r = _continue(client, "newuser", "s3cret-pass-xyz")
    assert "s3cret-pass-xyz" not in r.text


def test_existing_user_login_and_generic_error(client):
    assert _signup(client).status_code == 303
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    wrong = _continue(client, "newuser", "wrongpass1")
    assert wrong.status_code == 200 and "نام کاربری یا رمز درست نیست." in wrong.text
    assert 'value="newuser"' in wrong.text and "حساب تازه بسازیم؟" not in wrong.text
    ok = _continue(client, "newuser", "password123")
    assert ok.status_code == 303 and ok.headers["location"] == "/dashboard"


def test_rate_limit_message(client):
    from app import rate_limit
    assert _signup(client).status_code == 303
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    for _ in range(rate_limit.LOGIN_FAILS_PER_USER):
        _continue(client, "newuser", "wrongpass1")
    r = _continue(client, "newuser", "password123")
    assert r.status_code == 429 and "چند بار پشت سر هم اشتباه شد." in r.text


def test_unknown_user_runs_bcrypt_like_a_wrong_password(client, monkeypatch):
    """Equal work: an unknown username runs the same bcrypt check as a wrong password (no fast path).
    Counted, not timed, so a busy CI runner cannot make it flaky."""
    import app.unified_auth as ua

    assert _signup(client, "timer1").status_code == 303
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    calls = {"verify": 0, "hash": 0}
    real_verify, real_hash = ua.verify_password, ua.hash_password

    def verify(*a, **k):
        calls["verify"] += 1
        return real_verify(*a, **k)

    def hash_(*a, **k):
        calls["hash"] += 1
        return real_hash(*a, **k)

    monkeypatch.setattr(ua, "verify_password", verify)
    monkeypatch.setattr(ua, "hash_password", hash_)
    _continue(client, "timer1", "wrongpass1")
    known = dict(calls)
    calls.update(verify=0, hash=0)
    _continue(client, "nobody99", "wrongpass1")
    unknown = dict(calls)
    assert known == {"verify": 1, "hash": 0}
    assert unknown["verify"] == 1  # the dummy check, same cost as the wrong password
    assert unknown["hash"] == 1  # plus hashing the pending signup


def test_pending_signup_expires(client, monkeypatch):
    import app.unified_auth as ua
    r = _continue(client, "slowuser", "password123")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    monkeypatch.setattr(ua, "_now", lambda: 10**12)
    late = client.post("/auth/create", data={"password_confirm": "password123", "csrf": csrf}, follow_redirects=False)
    assert "زمان ساخت حساب تمام شد" in late.text


def test_logout_goes_to_auth(client):
    assert _signup(client).status_code == 303
    out = client.post("/logout", data={"csrf": _csrf(client, "/profile")}, follow_redirects=False)
    assert out.headers["location"] == "/auth"
