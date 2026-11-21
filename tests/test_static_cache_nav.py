"""Fast tab switches: versioned /static assets are immutable (HTTP cache + service worker cache-first)."""
from fastapi.testclient import TestClient

from app.config import STATIC_ASSET_VERSION
from app.main import app


def _c():
    return TestClient(app, base_url="https://daraiito.ir")


def test_versioned_static_is_immutable():
    for path in ("/static/style.css", "/static/dashboard.js", "/static/logo.svg"):
        r = _c().get(f"{path}?v={STATIC_ASSET_VERSION}")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_unversioned_or_old_static_revalidates():
    assert _c().get("/static/style.css").headers["cache-control"] == "no-cache"
    assert _c().get("/static/style.css?v=old").headers["cache-control"] == "no-cache"


def test_html_and_sw_not_long_cached():
    c = _c()
    assert "immutable" not in c.get("/sw.js").headers.get("cache-control", "")
    assert "immutable" not in c.get("/").headers.get("cache-control", "")


def test_sw_serves_current_version_assets_cache_first():
    sw = _c().get("/sw.js").text
    assert f'const ASSET_VERSION = "{STATIC_ASSET_VERSION}";' in sw
    assert 'url.searchParams.get("v") !== ASSET_VERSION' in sw
