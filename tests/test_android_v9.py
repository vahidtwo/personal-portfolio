"""Android v9 (domain move): source-level guards. The Kotlin logic itself is unit tested in HostMoveTest.kt."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "android/app/src/main/java/app/myinventory"


def test_version_9_in_gradle_and_release_json():
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert "?.toInt() ?: 9" in gradle and '?: "9.0"' in gradle
    rel = json.loads((ROOT / "app/android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] == 9 and rel["versionName"] == "9.0"
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"


def test_package_id_and_apk_name_unchanged():
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'applicationId = "app.myinventory"' in gradle
    assert (ROOT / "app/static/my-inventory.apk").exists()


def test_both_hosts_known_exact_set():
    src = (SRC / "ServerAddress.kt").read_text(encoding="utf-8")
    assert 'KNOWN_HOSTS = setOf("portfolio.vahidtwo.ir", "daraiito.ir")' in src
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "ServerAddress.isAllowedRemote(uri.scheme, uri.host, savedBaseUrl())" in main


def test_storage_keys_unchanged_and_new_flags_added():
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert 'KEY_URL = "base_url"' in main and 'PREFS = "app.myinventory"' in main
    assert 'KEY_HOST_MIGRATED = "host_migrated"' in main
    # old-host cookies are never cleared by the move
    assert "removeAllCookies" not in main and "removeSessionCookies" not in main


def test_health_probe_no_redirects_and_short_timeouts():
    src = (SRC / "HealthProbe.kt").read_text(encoding="utf-8")
    assert "instanceFollowRedirects = false" in src and re.search(r"connectTimeout = 5000", src)


def test_sms_uses_cookie_fallback():
    src = (SRC / "SmsReceiver.kt").read_text(encoding="utf-8")
    assert "ServerAddress.smsTarget(base)" in src


def test_health_and_app_version_and_apk_ok_on_both_hosts():
    from fastapi.testclient import TestClient
    from app.main import app
    for host in ("portfolio.vahidtwo.ir", "daraiito.ir"):
        c = TestClient(app, base_url=f"https://{host}")
        r = c.get("/health")
        assert r.status_code == 200 and r.json() == {"ok": True}
        v = c.get("/api/app-version")
        assert v.status_code == 200 and v.json()["versionCode"] == 9
        assert not v.json()["url"].startswith("http")  # relative: each host serves its own APK
        a = c.get("/download/my-inventory.apk", follow_redirects=False)
        assert a.status_code == 200
