"""The header menu is gone; its install and theme actions live in Settings and on the sign-in pages."""
import re
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_install_row_in_settings_hidden_until_prompt(client, no_network):
    _register(client)
    html = client.get("/profile?section=settings").text
    row = re.search(r'<button type="button" class="settings-row v2-row" id="pwa-install" hidden>.*?</button>', html, re.S)
    assert row and "نصب اپ" in row.group(0)
    assert html.count('id="pwa-install"') == 1 and "/static/pwa.js" in html
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".settings-row[hidden] { display: none; }" in css


def test_pwa_js_shows_on_prompt_and_hides_when_installed():
    js = (STATIC / "pwa.js").read_text(encoding="utf-8")
    assert 'getElementById("pwa-install")' in js and "pwa-install-landing" not in js
    prompt = js[js.index('addEventListener("beforeinstallprompt"'):]
    assert "if (standalone) return;" in prompt[:300] and "showInstallButtons(true)" in prompt[:300]
    installed = js[js.index('addEventListener("appinstalled"'):]
    assert "showInstallButtons(false)" in installed[:200]
    assert 'getElementById("pwa-install")' in (STATIC / "android-bridge.js").read_text(encoding="utf-8")


def test_header_has_no_menu_anywhere(client, no_network):
    for path in ("/", "/auth"):
        html = client.get(path).text
        assert 'id="menu-toggle"' not in html and 'id="side-panel"' not in html
    _register(client)
    for path in ("/dashboard", "/assets", "/profile"):
        html = client.get(path).text
        assert 'id="menu-toggle"' not in html and 'id="side-panel"' not in html
        assert 'id="theme-toggle"' not in html  # signed in: theme is in Settings


def test_theme_button_on_auth_page(client, no_network):
    html = client.get("/auth").text
    actions = html[html.index('<div class="top-actions">'):html.index("</header>")]
    assert 'class="btn-icon theme-btn" id="theme-toggle"' in actions
    assert actions.index('id="theme-toggle"') < actions.index('class="back-link"')
    assert 'aria-label="پوسته: تیره. تغییر به روشن"' in actions
    assert "/static/theme.js" in html
    pub = (STATIC / "public.css").read_text(encoding="utf-8")
    assert ".theme-btn{width:44px;height:44px" in pub
    assert "[data-theme=dark] .theme-icon-light,[data-theme=light] .theme-icon-dark{display:none}" in pub


def test_theme_button_on_login_and_register_error_pages(client, no_network):
    for path, data in (("/login", {"username": "nobody", "password": "x"}),
                       ("/register", {"username": "a", "password": "1", "password_confirm": "2"})):
        csrf = re.search(r'name="csrf" value="([^"]+)"', client.get("/auth").text).group(1)
        html = client.post(path, data=dict(data, csrf=csrf)).text
        header = html[html.index('<header class="top">'):html.index("</header>")]
        assert 'id="theme-toggle"' in header, path
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".top-inner > .theme-btn { margin-inline-start: auto; }" in css
    assert ".theme-btn { width: 44px; height: 44px; flex-shrink: 0; }" in css


def test_theme_js_toggle_still_wired():
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert 'getElementById("theme-toggle")' in js and "theme-toggle-label" not in js
