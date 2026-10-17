import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_version_is_public_and_complete(client):
    res = client.get("/api/app-version")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"versionCode", "versionName", "url", "sha256", "size_bytes", "cert_sha256", "notes", "min_required"}
    assert isinstance(data["versionCode"], int) and data["versionCode"] >= 5
    assert data["url"] == "/download/my-inventory.apk"
    assert isinstance(data["notes"], list) and data["notes"]
    assert all(isinstance(n, str) for n in data["notes"])
    assert isinstance(data["min_required"], int) and data["min_required"] == 0
    assert res.headers.get("cache-control") == "no-cache"


def test_app_version_sha_and_size_match_served_apk(client):
    apk = ROOT / "app" / "static" / "my-inventory.apk"
    data = client.get("/api/app-version").json()
    assert data["sha256"] == hashlib.sha256(apk.read_bytes()).hexdigest()
    assert data["size_bytes"] == apk.stat().st_size
    assert re.fullmatch(r"[0-9a-f]{64}", data["cert_sha256"])


def test_landing_shows_version_and_real_size_with_persian_comma(client):
    from app.pwa import apk_size_label_fa
    apk = ROOT / "app" / "static" / "my-inventory.apk"
    html = client.get("/").text
    label = apk_size_label_fa(apk.stat().st_size)
    from app.pwa import load_android_release, to_fa_digits
    version = to_fa_digits(load_android_release()["versionCode"])
    assert f"<strong>نسخهٔ {version}</strong>، {label}" in html
    row = html[html.index('class="card-desc apk-version"'):]
    row = row[: row.index("</p>")]
    assert "·" not in row
    assert "نسخهٔ ۳ یا قدیمی‌تر" in html


def test_size_label_rounds_to_whole_megabytes():
    from app.pwa import apk_size_label_fa
    assert apk_size_label_fa(3_287_333) == "حدود ۳ مگابایت"
    assert apk_size_label_fa(400_000) == "حدود ۱ مگابایت"
    assert apk_size_label_fa(None) is None


def test_release_json_matches_gradle_version():
    release = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    code = re.search(r"versionCode = (?:.*\?: )?(\d+)", gradle).group(1)
    name = re.search(r'versionName = (?:.*\?: )?"([^"]+)"', gradle).group(1)
    assert int(code) == release["versionCode"]
    assert name == release["versionName"]


def test_min_required_defaults_to_zero(client, tmp_path, monkeypatch):
    import app.pwa as pwa
    alt = tmp_path / "release.json"
    alt.write_text(json.dumps({"versionCode": 9, "versionName": "9.0", "notes": ["الف"]}), encoding="utf-8")
    monkeypatch.setattr(pwa, "_RELEASE_PATH", alt)
    data = client.get("/api/app-version").json()
    assert data["versionCode"] == 9 and data["min_required"] == 0 and data["notes"] == ["الف"]
