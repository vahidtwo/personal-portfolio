"""Web-only prep for v9: offline marker, SW cache bump, #hide=1 handoff on /auth. Ships no APK."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parent.parent


def test_offline_page_has_marker_and_sw_precaches_it():
    from app.config import STATIC_ASSET_VERSION
    assert STATIC_ASSET_VERSION >= "20261028e"
    for host in ("portfolio.vahidtwo.ir", "daraiito.ir"):
        c = TestClient(app, base_url=f"https://{host}")
        html = c.get("/offline.html").text
        assert '<meta name="x-offline" content="1">' in html
        sw = c.get("/sw.js")
        assert sw.status_code == 200 and '"/offline.html"' in sw.text
        assert f"inventory-v{STATIC_ASSET_VERSION}" in sw.text


def test_auth_page_serves_hide_handoff():
    html = TestClient(app, base_url="https://daraiito.ir").get("/auth").text
    assert 'location.hash!=="#hide=1"' in html and 'localStorage.setItem("privacy-portfolio","1")' in html


def test_does_not_publish_v9():
    rel = json.loads((ROOT / "app/android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] < 9
