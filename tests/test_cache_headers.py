"""HTML responses are no-store, except GET form pages (no-cache, private) so Back/Forward restores typed
input; versioned static assets are left alone."""
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def _no_store(r):
    return r.headers.get("cache-control") == "no-store"


def _form_page(r):
    cc = r.headers.get("cache-control", "")
    return "no-cache" in cc and "private" in cc and "no-store" not in cc


def test_anonymous_html_pages(client):
    for path in ("/", "/offline.html"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), path
        assert _no_store(r), path
    for path in ("/login", "/register"):  # form pages
        r = client.get(path)
        assert r.status_code == 200 and _form_page(r), path


def test_logged_in_html_pages(client, no_network):
    _register(client)
    for path in ("/dashboard", "/dashboard?tab=portfolio"):
        r = client.get(path)
        assert r.status_code == 200 and _no_store(r), path
    for path in ("/dashboard?tab=daily", "/assets", "/profile", "/profile?tab=debts", "/profile?section=settings"):
        r = client.get(path)
        assert r.status_code == 200 and _form_page(r), (path, r.headers.get("cache-control"))
    # an HTML error page (validation error re-render of a POST) stays no-store
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
    assert 'request.mode === "navigate"' in sw and "response = await fetch(request);" in sw and ".catch(async () =>" in sw
    assert "caches.delete(PAGE_CACHE)" in sw and 'url.pathname === "/login"' in sw
