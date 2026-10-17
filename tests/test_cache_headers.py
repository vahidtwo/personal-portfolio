"""Every HTML response is sent with Cache-Control: no-store; versioned static assets are left alone."""
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def _no_store(r):
    return r.headers.get("cache-control") == "no-store"


def test_anonymous_html_pages_are_no_store(client):
    for path in ("/", "/login", "/register", "/offline.html"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), path
        assert _no_store(r), path


def test_logged_in_html_pages_are_no_store(client, no_network):
    _register(client)
    for path in ("/dashboard", "/dashboard?tab=daily", "/assets", "/profile", "/profile?tab=debts"):
        r = client.get(path)
        assert r.status_code == 200 and _no_store(r), path
    # an HTML error page (validation error re-render) too
    r = client.post("/profile", data={"btc": "x.y.z", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 200 and _no_store(r)


def test_static_assets_and_non_html_keep_their_caching(client):
    for path in ("/static/style.css", "/static/pwa.js", "/static/logo.svg"):
        r = client.get(path)
        assert r.status_code == 200 and "no-store" not in r.headers.get("cache-control", ""), path
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"  # unchanged
    assert client.get("/manifest.webmanifest").headers["cache-control"] == "no-cache"
    assert "no-store" not in client.get("/health").headers.get("cache-control", "")


def test_service_worker_registration_never_auto_reloads():
    js = (STATIC / "pwa.js").read_text(encoding="utf-8")
    assert 'updateViaCache: "none"' in js and "registration.update()" in js
    handler = js[js.index('addEventListener("controllerchange"'):]
    handler = handler[:handler.index("});")]
    assert "reload" not in handler.split('btn.addEventListener("click"')[0]  # only the button reloads
    assert "نسخه جدید، تازه‌سازی" in js
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    # HTML stays network-first; the cache is only the offline fallback; logout still clears the page cache
    assert 'request.mode === "navigate"' in sw and "fetch(request).catch(" in sw
    assert "await caches.delete(PAGE_CACHE)" in sw and 'finalUrl.pathname === "/login"' in sw
