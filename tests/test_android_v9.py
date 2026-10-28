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
    assert "instanceFollowRedirects = false" in src and "connectTimeout = timeoutMs" in src and "TIMEOUT_MS = 3500" in src


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


def test_release_notes_v9_final():
    rel = json.loads((ROOT / "app/android_release.json").read_text(encoding="utf-8"))
    assert rel["notes"][2] == "اطلاعات و پنهان‌بودن مبلغ‌ها بعد از به‌روزرسانی می‌ماند"
    assert rel["notes"][0].startswith("نشانی برنامه daraiito.ir شد")


def test_move_carries_privacy_flag_and_never_renames_key():
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "localStorage.getItem('privacy-portfolio')" in main
    assert "localStorage.setItem('privacy-portfolio','1')" in main
    assert "ServerAddress.moveTarget(hide)" in main
    # the #36 handoff the app relies on is still on the pages the move lands on
    for t in ("base.html", "auth.html", "landing.html"):
        assert "hide_handoff" in (ROOT / "app/templates" / t).read_text(encoding="utf-8")
    h = (ROOT / "app/templates/partials/hide_handoff.html").read_text(encoding="utf-8")
    assert 'location.hash!=="#hide=1"' in h and 'setItem("privacy-portfolio","1")' in h


def test_fallback_clears_migrated_so_move_retries():
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "putBoolean(KEY_HOST_MIGRATED, false)" in main and "KEY_HOST_FALLBACK_COUNT" in main
    assert "moveTriedThisLaunch" in main and "fallbackThisLaunch" in main


def test_sms_session_cookie_names_match_server():
    from app.config import SESSION_COOKIE_NAME
    from app.session_marker import MARKER_COOKIE
    src = (SRC / "ServerAddress.kt").read_text(encoding="utf-8")
    assert f'SESSION_COOKIE = "{SESSION_COOKIE_NAME}"' in src
    assert f'SIGNED_IN_COOKIE = "{MARKER_COOKIE}"' in src


def test_anonymous_auth_visit_sets_session_cookie_but_no_marker():
    """Why fix 3 needs the marker: /auth alone already sets inventory_session (CSRF)."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, base_url="https://daraiito.ir")
    r = c.get("/auth")
    assert r.status_code == 200
    assert "inventory_signed_in" not in c.cookies


def test_sms_no_session_never_silent():
    src = (SRC / "SmsReceiver.kt").read_text(encoding="utf-8")
    assert "catch (t: Throwable)" in src and "KEY_LOGIN_NEEDED" in src
    assert "instanceFollowRedirects = false" in src
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "showSmsLoginPromptIfNeeded()" in main


def test_auth_page_serves_hide_handoff():
    """After the move the app lands on /auth (no session on the new host yet); #hide=1 must work there."""
    from fastapi.testclient import TestClient
    from app.main import app
    html = TestClient(app, base_url="https://daraiito.ir").get("/auth").text
    assert 'location.hash!=="#hide=1"' in html and 'localStorage.setItem("privacy-portfolio","1")' in html


def test_offline_page_has_marker_and_is_precached():
    """The SW serves /offline.html from its cache when the network is dead; the app detects this marker."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import STATIC_ASSET_VERSION
    c = TestClient(app, base_url="https://daraiito.ir")
    html = c.get("/offline.html").text
    assert '<meta name="x-offline" content="1">' in html
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and '"/offline.html"' in sw.text and STATIC_ASSET_VERSION in sw.text
    assert STATIC_ASSET_VERSION >= "20261028e"
    src = (SRC / "ServerAddress.kt").read_text(encoding="utf-8")
    assert "meta[name=\\\"x-offline\\\"]" in src and "m.content==='1'" in src


def test_launch_probe_and_offline_marker_wired():
    main = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "probeNewHostThenStart(savedInstanceState)" in main
    assert "ServerAddress.isOfflinePage(r)" in main and "KEY_HOST_CONFIRMED" in main
    assert "TIMEOUT_MS = 3500" in (SRC / "HealthProbe.kt").read_text(encoding="utf-8")
