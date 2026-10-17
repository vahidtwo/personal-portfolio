from pathlib import Path

BRIDGE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "android-bridge.js"


def test_web_pages_never_trigger_app_navigation():
    """Regression: calling setServerUrl from every page made the Android app
    (v4) reload in a loop, because the app navigates to /dashboard on that call."""
    src = BRIDGE_JS.read_text(encoding="utf-8")
    assert "setServerUrl(" not in src
    assert "in-android-app" in src
