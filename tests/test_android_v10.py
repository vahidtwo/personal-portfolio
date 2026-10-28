"""Android v10: logo B launcher icon, setup brand symbol, cookie flush guards. Source-level checks."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android/app/src/main/res"
MAIN = ROOT / "android/app/src/main/java/app/myinventory/MainActivity.kt"


def test_version_10():
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert __import__("re").search(r'\?\.toInt\(\) \?: 1\d\b', gradle)  # v10 or later (v11)
    assert 'applicationId = "app.myinventory"' in gradle
    rel = json.loads((ROOT / "app/android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] >= 10
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"
    assert rel["notes"] and all(isinstance(n, str) and n for n in rel["notes"])


def test_adaptive_icon_with_monochrome_and_round():
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        x = (RES / "mipmap-anydpi-v26" / name).read_text(encoding="utf-8")
        for layer in ("background", "foreground", "monochrome"):
            assert f'@drawable/ic_launcher_{layer}' in x
    for layer in ("background", "foreground", "monochrome"):
        assert "<vector" in (RES / "drawable" / f"ic_launcher_{layer}.xml").read_text(encoding="utf-8")
    for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        for n in ("ic_launcher.png", "ic_launcher_round.png"):
            assert (RES / f"mipmap-{d}" / n).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:icon="@mipmap/ic_launcher"' in manifest
    assert 'android:roundIcon="@mipmap/ic_launcher_round"' in manifest


def test_setup_uses_brand_symbol_like_web_header():
    html = (ROOT / "android/app/src/main/assets/www/setup.html").read_text(encoding="utf-8")
    assert 'src="static/brand/daraiito-symbol-dark.svg"' in html and 'src="static/brand/daraiito-symbol-light.svg"' in html
    assert 'src="static/logo.svg"' not in html
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    assert "/static/brand/daraiito-symbol-dark.svg" in base
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert '"daraiito-symbol-dark.svg", "daraiito-symbol-light.svg"' in gradle
    assert 'logo.copyTo(assetWwwDir.resolve("logo.svg")' in gradle


def test_cookie_flush_everywhere():
    src = MAIN.read_text(encoding="utf-8")
    for fn in ("override fun onPageCommitVisible", "override fun onPageFinished", "override fun onPause", "override fun onStop"):
        i = src.index(fn)
        body = src[i:src.index("\n    }", i) if fn.startswith("override fun onP") and "Page" not in fn or fn.endswith("onStop") else src.index("\n            }", i)]
        assert "CookieManager.getInstance().flush()" in body, fn
    assert "removeAllCookies" not in src and "removeSessionCookies" not in src
