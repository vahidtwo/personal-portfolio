import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_version_is_public_and_complete(client):
    res = client.get("/api/app-version")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"versionCode", "versionName", "url", "sha256", "notes", "min_required"}
    assert isinstance(data["versionCode"], int) and data["versionCode"] >= 5
    assert data["url"] == "/download/my-inventory.apk"
    assert isinstance(data["notes"], list) and data["notes"]
    assert all(isinstance(n, str) for n in data["notes"])
    assert isinstance(data["min_required"], int) and data["min_required"] == 0
    assert res.headers.get("cache-control") == "no-cache"


def test_app_version_sha_matches_served_apk(client):
    apk = ROOT / "app" / "static" / "my-inventory.apk"
    data = client.get("/api/app-version").json()
    assert data["sha256"] == hashlib.sha256(apk.read_bytes()).hexdigest()


def test_release_json_matches_gradle_version():
    release = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert int(re.search(r"versionCode = (\d+)", gradle).group(1)) == release["versionCode"]
    assert re.search(r'versionName = "([^"]+)"', gradle).group(1) == release["versionName"]


def test_min_required_defaults_to_zero(client, tmp_path, monkeypatch):
    import app.pwa as pwa
    alt = tmp_path / "release.json"
    alt.write_text(json.dumps({"versionCode": 9, "versionName": "9.0", "notes": ["الف"]}), encoding="utf-8")
    monkeypatch.setattr(pwa, "_RELEASE_PATH", alt)
    data = client.get("/api/app-version").json()
    assert data["versionCode"] == 9 and data["min_required"] == 0 and data["notes"] == ["الف"]
