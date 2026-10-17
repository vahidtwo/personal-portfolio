"""«دانلود اپلیکیشن اندروید» row for logged-in users (settings + avatar/side menu); route unchanged."""
import re

from tests.test_holdings import _register, no_network  # noqa: F401


def _fake_size(monkeypatch, label="۴ مگابایت"):
    from app.web import templates
    monkeypatch.setitem(templates.env.globals, "apk_size_label", lambda: label)


def test_download_row_renders_for_logged_in_user_in_settings_and_menu(client, no_network, monkeypatch):
    _fake_size(monkeypatch)
    _register(client)
    html = client.get("/profile").text
    links = re.findall(r'<a class="([^"]+) apk-download" href="/download/my-inventory\.apk" data-apk-download>', html)
    assert sorted(links) == ["nav-link", "settings-row"]  # avatar/side menu + Settings
    rows = html[html.index('id="settings-account-actions"'):]
    rows = rows[:rows.index("</section>")]
    assert "دانلود اپلیکیشن اندروید" in rows and "(۴ مگابایت)" in rows and "کروم" in rows
    assert rows.index("دانلود اپلیکیشن اندروید") < rows.index("خروج از حساب")  # logout stays last
    assert "روی گوشی اندروید باز کنید" in html and "data-apk-hint hidden" in html
    assert "/Android/i.test(navigator.userAgent)" in html
    # side menu on every logged-in page
    assert "data-apk-download" in client.get("/dashboard").text


def test_download_row_not_for_anonymous_and_hidden_without_apk(client, monkeypatch):
    _fake_size(monkeypatch)
    for path in ("/", "/login"):
        assert "data-apk-download" not in client.get(path).text
    _fake_size(monkeypatch, None)
    _register(client)
    assert "data-apk-download" not in client.get("/profile").text  # no file on the server: no dead link


def test_hidden_inside_android_app_css():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".in-android-app [data-apk-download] { display: none !important; }" in css
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "android-bridge.js").read_text(encoding="utf-8")
    assert 'classList.add("in-android-app")' in js


def test_size_label_comes_from_the_real_file(tmp_path, monkeypatch, client):
    import app.web as web
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "my-inventory.apk").write_bytes(b"x" * 4057232)
    monkeypatch.setattr(web, "BASE_DIR", tmp_path)
    assert web.apk_size_label() == "۴ مگابایت"
    (tmp_path / "static" / "my-inventory.apk").write_bytes(b"x" * 300 * 1024)
    assert web.apk_size_label() == "۰٫۳ مگابایت"
    (tmp_path / "static" / "my-inventory.apk").unlink()
    assert web.apk_size_label() is None
