"""HTTPS_ONLY (on by default): http -> https redirect, HSTS, Secure cookies, /health exempt, no loop behind the proxy."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tests.conftest import _purge_app_modules
from tests.test_holdings import _register


def _load(monkeypatch, tmp_path: Path, https_only: str | None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'inventory.db'}")
    monkeypatch.setenv("ENABLE_INTERNAL_SCHEDULER", "0")
    if https_only is None:
        monkeypatch.delenv("HTTPS_ONLY", raising=False)
    else:
        monkeypatch.setenv("HTTPS_ONLY", https_only)
    _purge_app_modules()
    from app.db import init_db
    from app.main import app

    init_db()
    return app


@pytest.fixture()
def secure_app(monkeypatch, tmp_path):
    app = _load(monkeypatch, tmp_path, None)  # the default, as deployed
    yield app
    import app.db as db_module
    db_module.engine.dispose()
    _purge_app_modules()


def test_on_by_default(secure_app):
    import app.config as config
    assert config.HTTPS_ONLY is True


def test_http_redirects_to_https_keeping_host_path_and_query(secure_app):
    c = TestClient(secure_app, base_url="http://daraiito.ir")
    r = c.get("/dashboard?tab=debts", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "https://daraiito.ir/dashboard?tab=debts"
    assert "set-cookie" not in r.headers


def test_old_host_redirects_to_its_own_https(secure_app):
    c = TestClient(secure_app, base_url="http://portfolio.vahidtwo.ir")
    r = c.post("/api/sms", follow_redirects=False)
    assert r.status_code == 308  # method and body are kept
    assert r.headers["location"] == "https://portfolio.vahidtwo.ir/api/sms"


def test_https_gets_hsts_modest_no_preload(secure_app):
    c = TestClient(secure_app, base_url="https://daraiito.ir")
    r = c.get("/auth", follow_redirects=False)
    assert r.status_code == 200
    hsts = r.headers["strict-transport-security"]
    assert hsts == "max-age=86400"
    assert "preload" not in hsts and "includesubdomains" not in hsts.lower()


def test_health_exempt_over_plain_http(secure_app):
    c = TestClient(secure_app, base_url="http://127.0.0.1:8000")
    r = c.get("/health", follow_redirects=False)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_cookies_secure_and_marker_stays_one(secure_app):
    c = TestClient(secure_app, base_url="https://daraiito.ir")
    _register(c)
    r = c.get("/dashboard", follow_redirects=False)
    cookies = r.headers.get_list("set-cookie")
    by_name = {h.split("=", 1)[0]: h for h in cookies}
    for name in ("inventory_session", "inventory_signed_in", "inventory_page_key"):
        assert name in by_name, cookies
        assert "secure" in by_name[name].lower()
    assert "httponly" in by_name["inventory_session"].lower()
    assert by_name["inventory_signed_in"].split(";", 1)[0] == "inventory_signed_in=1"


def _behind_proxy(app, trusted):
    return ProxyHeadersMiddleware(app, trusted_hosts=trusted)


def test_no_loop_with_forwarded_proto_https_from_proxy(secure_app):
    # TestClient's peer is "testclient"; trust it as uvicorn --proxy-headers --forwarded-allow-ips would.
    c = TestClient(_behind_proxy(secure_app, "*"), base_url="http://web:8000")
    r = c.get("/auth", headers={"x-forwarded-proto": "https", "host": "daraiito.ir"}, follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["strict-transport-security"] == "max-age=86400"


def test_forwarded_proto_http_from_proxy_redirects(secure_app):
    c = TestClient(_behind_proxy(secure_app, "*"), base_url="http://web:8000")
    r = c.get("/auth", headers={"x-forwarded-proto": "http", "host": "daraiito.ir"}, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "https://daraiito.ir/auth"


def test_forwarded_proto_ignored_from_untrusted_peer(secure_app):
    c = TestClient(_behind_proxy(secure_app, "10.0.0.1"), base_url="http://daraiito.ir")
    r = c.get("/auth", headers={"x-forwarded-proto": "https"}, follow_redirects=False)
    assert r.status_code == 308


def test_off_via_env(monkeypatch, tmp_path):
    app = _load(monkeypatch, tmp_path, "0")
    try:
        r = TestClient(app).get("/auth", follow_redirects=False)
        assert r.status_code == 200 and "strict-transport-security" not in r.headers
    finally:
        import app.db as db_module
        db_module.engine.dispose()
        _purge_app_modules()


def test_dockerfile_runs_uvicorn_with_proxy_headers():
    src = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text()
    assert "--proxy-headers" in src and "--forwarded-allow-ips" in src
    assert "http://127.0.0.1:8000/health" in src
