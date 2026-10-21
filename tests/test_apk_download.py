"""«دریافت اپ اندروید» row for logged-in users (settings + avatar/side menu); route unchanged."""
import re
import zipfile
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _fake_info(monkeypatch, info={"size": "۴ مگابایت", "version": "۳٫۰"}):
    from app.web import templates
    monkeypatch.setitem(templates.env.globals, "android_apk_info", lambda: info)


def test_download_row_renders_for_logged_in_user_in_settings_and_menu(client, no_network, monkeypatch):
    _fake_info(monkeypatch)
    _register(client)
    html = client.get("/profile").text
    links = re.findall(r'<a class="([^"]+) apk-download" href="/download/my-inventory\.apk" data-apk-download>', html)
    assert sorted(links) == ["nav-link", "settings-row v2-row"]  # avatar/side menu + Settings
    assert html.count('<span class="settings-row-label">دریافت اپ اندروید</span>') == 2
    # version and size in their own isolated spans, so the digits can never run together («نسخهٔ ۴۰۳٫۰ مگابایت»)
    metas = re.findall(r'<span class="apk-meta">(.*?)</span>\s*<span class="apk-note">', html)
    assert len(metas) == 2
    for meta in metas:
        assert '<span class="apk-version">نسخهٔ <bdi>۳٫۰</bdi></span>' in meta
        assert '<span class="apk-size"><bdi>۴ مگابایت</bdi></span>' in meta
        assert re.sub(r"<[^>]+>", "", meta).strip() == "نسخهٔ ۳٫۰ · ۴ مگابایت"
    rows = html[html.index('id="settings-account-actions"'):]  # settings v2: «اپ و اتصال‌ها» then the «خروج» card
    rows = rows[:rows.index("</section>", rows.index('id="logout"'))]
    assert "کروم" in rows and rows.index("دریافت اپ اندروید") < rows.index("خروج از حساب")  # logout stays last
    assert "روی گوشی اندروید باز کنید" in html and "data-apk-hint hidden" in html
    assert "/Android/i.test(navigator.userAgent)" in html
    assert "data-apk-download" in client.get("/dashboard").text  # side menu on every logged-in page


def test_download_row_not_for_anonymous_and_hidden_without_apk(client, monkeypatch):
    _fake_info(monkeypatch)
    for path in ("/", "/login"):
        assert "data-apk-download" not in client.get(path).text
    _fake_info(monkeypatch, None)
    _register(client)
    assert "data-apk-download" not in client.get("/profile").text  # no file on the server: no dead link


def test_hidden_inside_android_app_css():
    css = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".in-android-app [data-apk-download] { display: none !important; }" in css
    js = (ROOT / "app" / "static" / "android-bridge.js").read_text(encoding="utf-8")
    assert 'classList.add("in-android-app")' in js


def test_size_from_the_real_file_and_missing_or_broken_apk(tmp_path):
    from app.apk_info import apk_info
    apk = tmp_path / "a.apk"
    assert apk_info(apk) is None
    apk.write_bytes(b"x" * 4057232)  # not a zip: size still shown, version hidden
    assert apk_info(apk) == {"size": "۴ مگابایت", "version": None}
    apk.write_bytes(b"x" * 300 * 1024)
    assert apk_info(apk)["size"] == "۰٫۳ مگابایت"


def test_version_read_from_the_served_apk_matches_gradle():
    apk = ROOT / "app" / "static" / "my-inventory.apk"
    gradle = ROOT / "android" / "app" / "build.gradle.kts"
    if not apk.is_file() or not zipfile.is_zipfile(apk):
        import pytest
        pytest.skip("APK not in this checkout")
    from app.apk_info import apk_info
    from app.formatting import persian_digits
    info = apk_info(apk)
    assert info["version"], "versionName not found in the APK manifest"
    if gradle.is_file():
        line = re.search(r'^\s*versionName\s*=.*$', gradle.read_text(encoding="utf-8"), re.M).group(0)
        name = re.findall(r'"([^"]+)"', line)[-1]  # last literal = default (QA override comes first)
        assert info["version"] == persian_digits(name).replace(".", "٫")
