"""Batch 1: gzip only static CSS/JS; never HTML (BREACH) and never the APK (size/sha256)."""
from tests.test_holdings import _register  # noqa: F401

GZ = {"Accept-Encoding": "gzip"}


def test_static_css_and_js_are_gzipped(client):
    for path in ("/static/style.css", "/static/dashboard.js"):
        r = client.get(path, headers=GZ)
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip", path
        assert "accept-encoding" in r.headers.get("vary", "").lower()


def test_html_pages_are_not_gzipped(client):
    assert "content-encoding" not in client.get("/login", headers=GZ).headers
    _register(client)
    r = client.get("/dashboard", headers=GZ)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "content-encoding" not in r.headers


def test_apk_never_gzipped(client):
    from app.static_gzip import should_gzip

    for path in ("/download/my-inventory.apk", "/static/my-inventory.apk"):
        assert not should_gzip(path)
        r = client.get(path, headers=GZ)
        assert "content-encoding" not in r.headers, path
        if r.status_code == 200:
            assert int(r.headers["content-length"]) == len(r.content)


def test_should_gzip_rules():
    from app.static_gzip import should_gzip

    assert should_gzip("/static/style.css") and should_gzip("/static/pwa.js")
    assert not should_gzip("/dashboard") and not should_gzip("/sw.js") and not should_gzip("/static/logos/a.svg")
