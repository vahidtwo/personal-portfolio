"""Android 12.0.0 (13), Phase 4: native login and home, static checks on the app source."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "android" / "app"
SRC = APP / "src" / "main"
KT = SRC / "java" / "app" / "myinventory"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_version_14_and_approved_notes():
    g = _read(APP / "build.gradle.kts")
    assert "?.toInt() ?: 14" in g and '?: "12.0.1"' in g
    rel = json.loads(_read(ROOT / "app" / "android_release.json"))
    assert rel["versionCode"] == 14 and rel["versionName"] == "12.0.1"
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"
    assert rel["notes_approved"] is True and rel["notes"]


def test_fixed_origin_and_flags():
    g = _read(APP / "build.gradle.kts")
    assert 'buildConfigField("String", "APP_BASE", "\\"https://daraiito.ir\\"")' in g
    assert 'buildConfigField("boolean", "BIOMETRIC_UNLOCK", "false")' in g
    assert "SECURE_SCREENS" not in g
    assert "val BASE: String = BuildConfig.APP_BASE" in _read(KT / "NativeSession.kt")


def test_screenshots_allowed_no_flag_secure():
    """12.0.1: FLAG_SECURE is removed everywhere (login, home and WebView tabs)."""
    for f in KT.glob("*.kt"):
        assert "FLAG_SECURE" not in _read(f).replace("no FLAG_SECURE since 12.0.1", ""), f.name


def test_launcher_is_native_and_setup_is_gone():
    manifest = _read(SRC / "AndroidManifest.xml")
    launcher = manifest[: manifest.index("android.intent.category.LAUNCHER")]
    assert launcher.rindex('android:name=".HomeActivity"') > launcher.rfind('android:name=".MainActivity"')
    assert 'android:name=".MainActivity"\n            android:exported="false"' in manifest
    assert "connection_settings" not in _read(SRC / "res" / "xml" / "shortcuts.xml")


def test_native_session_shares_webview_cookies():
    s = _read(KT / "NativeSession.kt")
    assert "CookieManager.getInstance()" in s
    assert "X-CSRF-Token" in s


def test_logout_clears_native_and_web():
    home = _read(KT / "HomeActivity.kt")
    sign_out = home[home.index("private fun signOutLocal("):]
    sign_out = sign_out[: sign_out.index("\n    }\n")]
    assert "cache.clear()" in sign_out and "WebPrewarm.stop()" in sign_out
    assert "NativeSession.clearLocal()" in sign_out


def test_prewarm_waits_for_the_home_frame():
    home = _read(KT / "HomeActivity.kt")
    assert "WebPrewarm.start(this) }, PREWARM_DELAY_MS)" in home


def test_full_vazirmatn_with_license():
    assert (SRC / "res" / "font" / "vazirmatn.ttf").stat().st_size > 100_000
    assert (SRC / "res" / "font" / "vazirmatn_bold.ttf").stat().st_size > 100_000
    assert "SIL OPEN FONT LICENSE" in _read(SRC / "assets" / "licenses" / "vazirmatn-OFL.txt").upper()


def test_google_services_json_not_committed():
    import subprocess

    root = APP.parents[1]
    tracked = subprocess.run(["git", "ls-files", "--", "android/app/google-services.json"], cwd=root,
                             capture_output=True, text=True).stdout
    assert tracked == ""
    ignored = subprocess.run(["git", "check-ignore", "-q", "android/app/google-services.json"], cwd=root)
    assert ignored.returncode == 0
    # Builds (and the parallel test run) copy the fake example in place; a real config must never be here.
    gs = APP / "google-services.json"
    if gs.exists():
        assert gs.read_bytes() == (APP / "google-services.json.example").read_bytes()


def test_native_hide_amounts_defaults_hidden():
    home = _read(KT / "HomeActivity.kt")
    assert "const val MASK_DEFAULT = true" in home
    assert "getBoolean(KEY_MASK, MASK_DEFAULT)" in home
    assert "getBoolean(KEY_MASK, false)" not in home


def test_webview_error_page_is_retry_only():
    page = _read(SRC / "assets" / "www" / "error.html")
    assert "تلاش دوباره" in page and "AndroidBridge.retry" in page

    assert "تنظیمات پیشرفته" not in page and "setup.html" not in page
    main = _read(KT / "MainActivity.kt")
    assert "?error=connect" not in main and "error.html" in main
    assert "MainFrameErrors" in main


def test_tab_launch_shows_skeleton_not_blank():
    main = _read(KT / "MainActivity.kt")
    assert "LoadingSkeleton.install" in main
    assert "!tabLaunch && startup.keepSplash" in main


def test_review_fixes_in_home_activity():
    home = _read(KT / "HomeActivity.kt")
    assert "smoothScrollTo" in home and "KeyboardScroll.target" in home
    assert "MaskRules.netUnit(m," in home and "MaskRules.todayLine(m," in home
    assert 'optString("color")' not in home and "MaskRules.trendColor" in home
    assert "AutofillManager::class.java)?.commit()" in home
    assert "onSaveInstanceState" in home and "announceForAccessibility" in home


def test_error_page_fonts_are_bundled_at_build():
    """error.html loads static/fonts/*.woff2; Gradle copies app/static/fonts into assets/www/static/fonts."""
    page = _read(SRC / "assets" / "www" / "error.html")
    gradle = _read(APP / "build.gradle.kts")
    assert 'resolve("fonts")' in gradle
    for name in ("vazirmatn-arabic.woff2", "vazirmatn-latin.woff2"):
        assert f"static/fonts/{name}" in page
        assert (ROOT / "app" / "static" / "fonts" / name).is_file()


def test_locked_button_has_no_alpha():
    home = _read(KT / "HomeActivity.kt")
    assert "alpha = 0.6f" not in home
    assert "bg(c.surface2, 12); button.setTextColor(c.muted)" in home
    assert "defaultFocusHighlightEnabled = false" in home
