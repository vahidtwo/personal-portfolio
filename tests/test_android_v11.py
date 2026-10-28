"""v11 Android startup: native splash held to first paint, no spinner overlay, R2/R2c paths intact."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "app"
SRC = APP / "src" / "main"
MAIN = (SRC / "java" / "app" / "myinventory" / "MainActivity.kt").read_text(encoding="utf-8")
GATE = (SRC / "java" / "app" / "myinventory" / "StartupGate.kt").read_text(encoding="utf-8")


def test_version_11_and_splash_dependency():
    g = (APP / "build.gradle.kts").read_text(encoding="utf-8")
    assert "?.toInt() ?: 11" in g and '?: "11.0"' in g
    assert 'implementation("androidx.core:core-splashscreen:' in g
    assert not (APP / "google-services.json").exists() or "google-services.json" in (ROOT / ".gitignore").read_text()


def test_native_splash_theme_with_logo_b():
    manifest = (SRC / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:name=".MainActivity"\n            android:exported="true"\n            android:theme="@style/Theme.MyInventory.Starting"' in manifest
    themes = (SRC / "res" / "values" / "themes.xml").read_text(encoding="utf-8")
    assert 'parent="Theme.SplashScreen.IconBackground"' in themes
    assert "@drawable/ic_launcher_foreground" in themes and "@style/Theme.MyInventory</item>" in themes
    assert "installSplashScreen().setKeepOnScreenCondition" in MAIN
    assert MAIN.index("installSplashScreen()") < MAIN.index("super.onCreate(savedInstanceState)")
    assert "SPLASH_MAX_MS = 2500L" in GATE


def test_grey_spinner_overlay_removed():
    layout = (SRC / "res" / "layout" / "activity_main.xml").read_text(encoding="utf-8")
    assert "ProgressBar" not in layout and "@string/connecting" not in layout
    assert 'android:id="@+id/loading"' in layout and "@mipmap/ic_launcher_round" in layout


def test_cover_hidden_on_first_paint_not_load():
    commit = MAIN[MAIN.index("override fun onPageCommitVisible"):MAIN.index("override fun onPageStarted")]
    assert "StartupGate.revealOnCommit(url, readingOldPrivacy, errorPending)" in commit and "showLoading(false)" in commit
    assert "CookieManager.getInstance().flush()" in commit  # v10 flush kept


def test_offline_marker_and_fallback_paths_kept():
    finished = MAIN[MAIN.index("override fun onPageFinished"):MAIN.index("onBackPressedDispatcher")]
    assert "checkNewHostPage(url)" in finished and "applyPendingHide(url)" in finished
    assert "maybeFallBackToOldHost(url)" in MAIN and "probeNewHostThenStart" in MAIN
    assert "'privacy-portfolio'" in MAIN  # key never renamed


def test_release_json_v11_notes_unapproved_and_same_cert():
    import json
    rel = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] == 11 and rel["versionName"] == "11.0"
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"
    assert rel["notes_approved"] is False and len(rel["notes"]) == 3


def test_native_splash_released_when_webview_starts_loading():
    """Late-paint fix: a kept splash cancels draws, so it must hand off to the logo cover at loadUrl."""
    assert "fun handOffToCover()" in GATE and "painted || handedOff" in GATE
    load = MAIN[MAIN.index("fun loadRemote("):]
    assert load.index("startup.handOffToCover()") < load.index("web.loadUrl(")
