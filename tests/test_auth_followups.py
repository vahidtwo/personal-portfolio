"""Follow-ups from the login v2 review (F2 button re-enable, F3 shared-IP lock copy, F4 theme-color). Fake users only."""
import re
from pathlib import Path

from tests.test_auth_v2 import _continue, _locked_client

ROOT = Path(__file__).resolve().parents[1]


def test_lock_copy_does_not_blame_only_the_username(client):
    _locked_client(client)
    r = _continue(client, "lockme", "password123")
    assert r.status_code == 429
    assert "ورود از این شبکه یا با این نام کاربری تا حدود ۱۵ دقیقهٔ دیگر بسته است." in r.text
    # same text for a different name: no hint about which bucket fired
    other = _continue(client, "somebodyelse", "password123")
    if other.status_code == 429:
        assert "ورود از این شبکه یا با این نام کاربری" in other.text


def test_auth_theme_color_meta_follows_theme(client):
    html = client.get("/auth").text
    meta = html.index('id="meta-theme-color"')
    script = html.index('localStorage.getItem("inventory-theme")')
    assert meta < script, "the meta tag must exist before the pre-paint script runs"
    assert 'content="#050608"' in html[meta - 60 : meta + 40]
    assert html.count('name="theme-color"') == 1
    assert 't==="light"?"#eef1f8":"#050608"' in html  # same values as theme.js


def test_theme_color_values_match_theme_js():
    js = (ROOT / "app" / "static" / "theme.js").read_text(encoding="utf-8")
    assert '"light" ? "#eef1f8" : "#050608"' in js


def test_locked_page_ships_the_unlock_on_username_edit_hook(client):
    _locked_client(client)
    r = _continue(client, "lockme", "password123")
    assert re.search(r'<input[^>]*id="username"[^>]*>', r.text) and "readonly" not in re.search(r'<input[^>]*id="username"[^>]*>', r.text).group(0)
    js = (ROOT / "app" / "static" / "auth.js").read_text(encoding="utf-8")
    assert 'getElementById("username")' in js and 'addEventListener("input"' in js and "unlock()" in js
