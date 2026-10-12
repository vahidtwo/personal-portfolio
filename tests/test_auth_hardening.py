"""Register confirmation, login/register rate limits, and HEAD /."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _csrf(client: TestClient, path: str) -> str:
    html = client.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _register(client: TestClient, username: str, password: str = "password123", confirm: str | None = None):
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": password if confirm is None else confirm,
            "csrf": _csrf(client, "/register"),
        },
        follow_redirects=False,
    )


def test_head_root_ok(client: TestClient):
    assert client.head("/").status_code == 200


def test_register_rejects_mismatched_confirm(client: TestClient):
    resp = _register(client, "mismatch", confirm="different123")
    assert resp.status_code == 200
    assert "یکسان نیستند" in resp.text


def test_register_success_redirects_to_profile(client: TestClient):
    resp = _register(client, "gooduser")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/profile"


def test_login_locks_after_repeated_failures(client: TestClient):
    _register(client, "victim")
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    for _ in range(10):
        resp = client.post(
            "/login",
            data={"username": "victim", "password": "wrong-pass", "csrf": _csrf(client, "/login")},
            follow_redirects=False,
        )
        assert "نادرست" in resp.text
    resp = client.post(
        "/login",
        data={"username": "victim", "password": "password123", "csrf": _csrf(client, "/login")},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "۱۵ دقیقه" in resp.text


def test_successful_login_clears_failures(client: TestClient):
    _register(client, "forgetful")
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    for _ in range(9):
        client.post(
            "/login",
            data={"username": "forgetful", "password": "wrong-pass", "csrf": _csrf(client, "/login")},
        )
    resp = client.post(
        "/login",
        data={"username": "forgetful", "password": "password123", "csrf": _csrf(client, "/login")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_register_limited_per_ip(client: TestClient):
    for i in range(5):
        assert _register(client, f"bulk{i}").status_code == 303
        client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    resp = _register(client, "bulk5")
    assert resp.status_code == 200
    assert "تعداد ثبت‌نام زیاد" in resp.text


def test_client_ip_ignores_spoofed_cf_header_off_cloudflare():
    from starlette.requests import Request

    from app.rate_limit import client_ip

    def req(headers):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()], "client": ("10.0.0.5", 1)})

    assert client_ip(req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})) == "9.9.9.9"
    assert client_ip(req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "5.5.5.5, 162.158.1.1"})) == "1.2.3.4"
    assert client_ip(req({"cf-connecting-ip": "1.2.3.4"})) == "10.0.0.5"
