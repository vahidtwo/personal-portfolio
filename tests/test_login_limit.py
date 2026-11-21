"""Failed-login limits: persisted across restarts, per IP, forged headers ignored, web + /api/auth."""
import sys

import pytest
from fastapi.testclient import TestClient

from tests.test_native_api import _csrf as _api_csrf
from tests.test_unified_auth import _csrf as _web_csrf

PEER_A = ("203.0.113.10", 1000)
PEER_B = ("203.0.113.20", 1000)
ARVAN_EDGE = ("185.143.233.133", 1000)
CF_EDGE = ("162.158.1.1", 1000)


def _as(client, peer):
    return TestClient(client.app, client=peer)


def _api(c, username, password, headers=None):
    h = {"X-CSRF-Token": _api_csrf(c), **(headers or {})}
    return c.post("/api/auth/continue", json={"username": username, "password": password}, headers=h)


def _web(c, username, password, headers=None):
    return c.post("/auth/continue", data={"username": username, "password": password, "csrf": _web_csrf(c)},
                  headers=headers or {}, follow_redirects=False)


def _legacy(c, username, password):
    return c.post("/login", data={"username": username, "password": password, "csrf": _web_csrf(c, "/login")},
                  follow_redirects=False)


def _make_user(client, username):
    from app.db import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    db.add(User(username=username, password_hash=hash_password("password123")))
    db.commit()
    db.close()


def _fail(send, c, username, n, headers=None):
    for _ in range(n):
        r = send(c, username, "wrongpass1", headers) if headers is not None else send(c, username, "wrongpass1")
        assert r.status_code != 429
    return r


@pytest.mark.parametrize("send", [_api, _web, _legacy], ids=["api", "web", "legacy-login"])
def test_each_endpoint_locks_with_429_persian(client, send):
    from app import rate_limit

    _make_user(client, "lockme")
    c = _as(client, PEER_A)
    _fail(send, c, "lockme", rate_limit.LOGIN_FAILS_PER_USER)
    r = send(c, "lockme", "password123")
    assert r.status_code == 429
    assert 880 <= int(r.headers["retry-after"]) <= 900
    assert "دقیقه" in r.text
    assert "lockme" not in r.headers.get("location", "")


def test_limit_survives_restart(client, monkeypatch):
    from app import rate_limit

    _make_user(client, "persist")
    c = _as(client, PEER_A)
    _fail(_api, c, "persist", rate_limit.LOGIN_FAILS_PER_USER)
    assert _api(c, "persist", "password123").status_code == 429
    # Restart: drop connections and reload every app module; DATA_DIR (the volume) stays.
    rate_limit.close_all()
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]
    from app.db import init_db
    from app.main import app

    init_db()
    with TestClient(app, client=PEER_A) as c2:
        assert _api(c2, "persist", "password123").status_code == 429
        assert _web(c2, "persist", "password123").status_code == 429
    import app.rate_limit as fresh

    assert fresh._db_path().name == "rate_limit.sqlite" and fresh._db_path().is_file()


def test_ips_are_separate(client):
    from app import rate_limit

    _make_user(client, "shared")
    _fail(_api, _as(client, PEER_A), "shared", rate_limit.LOGIN_FAILS_PER_USER)
    assert _api(_as(client, PEER_A), "shared", "password123").status_code == 429
    r = _api(_as(client, PEER_B), "shared", "password123")
    assert r.status_code == 200 and r.json()["result"] == "ok"


def test_forged_forwarding_headers_are_ignored(client):
    from app import rate_limit

    _make_user(client, "forger")
    c = _as(client, PEER_A)
    # Rotating forged IPs in every header does not spread the count over many "IPs".
    for i in range(rate_limit.LOGIN_FAILS_PER_USER):
        forged = {"X-Forwarded-For": f"198.51.100.{i}", "X-Real-IP": f"198.51.100.{i}",
                  "ar-real-ip": f"198.51.100.{i}", "CF-Connecting-IP": f"198.51.100.{i}"}
        assert _api(c, "forger", "wrongpass1", forged).status_code == 200
    assert _api(c, "forger", "password123", {"X-Forwarded-For": "198.51.100.200",
                                             "ar-real-ip": "198.51.100.200"}).status_code == 429


def test_arvancloud_real_ip_trusted_only_from_arvan_edge(client):
    from app import rate_limit

    _make_user(client, "cdnuser")
    edge = _as(client, ARVAN_EDGE)
    _fail(_api, edge, "cdnuser", rate_limit.LOGIN_FAILS_PER_USER, {"ar-real-ip": "198.51.100.7"})
    assert _api(edge, "cdnuser", "password123", {"ar-real-ip": "198.51.100.7"}).status_code == 429
    # Another visitor behind the same edge is not locked.
    assert _api(edge, "cdnuser", "password123", {"ar-real-ip": "198.51.100.8"}).json()["result"] == "ok"


def test_client_ip_rules():
    from starlette.requests import Request

    from app.rate_limit import client_ip

    def req(peer, headers):
        return Request({"type": "http", "client": (peer, 1),
                        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})

    assert client_ip(req("185.143.233.133", {"ar-real-ip": "1.2.3.4"})) == "1.2.3.4"
    assert client_ip(req("185.143.233.133", {"ar-real-ip": "junk"})) == "185.143.233.133"
    assert client_ip(req("185.143.233.133", {"cf-connecting-ip": "1.2.3.4"})) == "185.143.233.133"
    assert client_ip(req("203.0.113.10", {"ar-real-ip": "1.2.3.4", "x-forwarded-for": "1.2.3.4"})) == "203.0.113.10"
    assert client_ip(req(CF_EDGE[0], {"ar-real-ip": "1.2.3.4"})) == CF_EDGE[0]


def test_ip_lockout_does_not_reveal_whether_username_exists(client):
    from app import rate_limit

    users = [f"ipuser{i}" for i in range(3)]
    for u in users:
        _make_user(client, u)
    c = _as(client, PEER_A)
    for u in users:  # 3 x 10 = LOGIN_FAILS_PER_IP failures from one IP
        _fail(_api, c, u, rate_limit.LOGIN_FAILS_PER_USER)
    known = _api(c, "ipuser0", "password123")
    unknown = _api(c, "nobodyhere", "password123")
    assert known.status_code == unknown.status_code == 429
    kj, uj = known.json(), unknown.json()
    assert (kj["result"], kj["message"], kj["sub"]) == (uj["result"], uj["message"], uj["sub"])
    assert "چند بار" in kj["message"]


def test_backoff_doubles_and_success_resets(monkeypatch):
    from app import rate_limit

    clock = [10_000.0]
    monkeypatch.setattr(rate_limit.time, "time", lambda: clock[0])
    key, limit, window = "login:ip:t", 3, 900
    for _ in range(limit):
        rate_limit.record(key, window, limit)
    assert rate_limit.lock_level(key) == 1 and rate_limit.retry_after(key, limit, window) == 900
    clock[0] += 901
    assert rate_limit.retry_after(key, limit, window) == 0
    for _ in range(limit):
        rate_limit.record(key, window, limit)
    assert rate_limit.lock_level(key) == 2 and rate_limit.retry_after(key, limit, window) == 1800
    clock[0] += 1801
    for _ in range(limit):
        rate_limit.record(key, window, limit)
    assert rate_limit.retry_after(key, limit, window) == 3600
    for _ in range(10):
        clock[0] += 100_000
        for _ in range(limit):
            rate_limit.record(key, window, limit)
    assert rate_limit.retry_after(key, limit, window) <= rate_limit.MAX_LOCK_SECONDS
    rate_limit.clear(key)  # what a successful login does
    assert rate_limit.lock_level(key) == 0 and rate_limit.retry_after(key, limit, window) == 0


def test_success_resets_ip_and_user_counts(client):
    from app import rate_limit

    _make_user(client, "goodone")
    c = _as(client, PEER_A)
    _fail(_api, c, "goodone", rate_limit.LOGIN_FAILS_PER_USER - 1)
    assert _api(c, "goodone", "password123").json()["result"] == "ok"
    ip = PEER_A[0]
    assert rate_limit.retry_after(f"login:ip:{ip}", 1, rate_limit.LOGIN_WINDOW_SECONDS) == 0
    assert rate_limit.retry_after(f"login:user:goodone:{ip}", 1, rate_limit.LOGIN_WINDOW_SECONDS) == 0


def test_bcrypt_cost_default_is_12_in_production():
    import subprocess

    out = subprocess.run(
        [sys.executable, "-c", "import os; os.environ.pop('BCRYPT_ROUNDS', None); "
         "from app.security import BCRYPT_ROUNDS, hash_password; print(BCRYPT_ROUNDS, hash_password('x')[:7])"],
        capture_output=True, text=True, env={k: v for k, v in __import__('os').environ.items() if k != "BCRYPT_ROUNDS"},
    )
    assert out.stdout.split() == ["12", "$2b$12$"], out.stderr
