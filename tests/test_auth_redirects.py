"""Auth redirect and session cookie behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME
from app.models import User


def _register_and_login(client: TestClient, username: str = "testuser") -> None:
    page = client.get("/register")
    token = _csrf_from_page(page.text)
    response = client.post(
        "/register",
        data={"username": username, "password": "password123", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _csrf_from_page(html: str) -> str:
    marker = 'name="csrf" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def test_no_cookie_home_200_dashboard_redirects_login(client: TestClient):
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200

    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code == 303
    assert dash.headers["location"] == "/login"


def test_valid_session_home_to_dashboard_and_dashboard_200(client: TestClient):
    _register_and_login(client, username="validuser")

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/dashboard"

    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code == 200


def test_stale_session_cleared_and_no_redirect_loop(client: TestClient):
    _register_and_login(client, username="staleuser")
    session_cookie = client.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie

    from app.db import SessionLocal

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "staleuser").one()
        db.delete(user)
        db.commit()
    finally:
        db.close()

    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code == 303
    assert dash.headers["location"] == "/login"
    set_cookie = dash.headers.get("set-cookie", "").lower()
    assert SESSION_COOKIE_NAME in set_cookie
    assert "max-age=0" in set_cookie or 'max-age="0"' in set_cookie

    login = client.get("/login", follow_redirects=False)
    assert login.status_code == 200

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200

    chain = client.get("/dashboard", follow_redirects=True)
    assert chain.status_code == 200
    assert chain.url.path == "/login"
