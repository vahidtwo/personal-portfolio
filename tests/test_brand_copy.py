"""Brand copy: «موجودی من» -> «دارایی‌تو» (ZWNJ U+200C), daraiito / Daraiito in Latin. Text only."""
import json
import re
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
NAME = "دارایی\u200cتو"
OLD = "موجودی من"


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()


def test_name_has_zwnj_not_space_or_plain_join():
    assert "\u200c" in NAME and NAME != "دارایی تو" and NAME != "داراییتو"
    assert len(NAME) == 9  # 8 letters + 1 ZWNJ


def test_public_pages_use_new_name(client, no_network):
    landing = client.get("/").text
    assert _title(landing) == f"{NAME} — همهٔ دارایی‌هایتان، یک‌جا"
    assert f"32\">{NAME}</a>" in landing
    assert OLD not in landing
    auth = client.get("/auth").text
    assert _title(auth) == f"ورود یا ساخت حساب، {NAME}"
    assert f"28\">{NAME}</a>" in auth and OLD not in auth


def test_logged_in_pages_titles_and_header(client, no_network):
    _register(client)
    expect = {
        "/dashboard": f"داشبورد، {NAME}",
        "/assets": f"دارایی‌ها، {NAME}",
        "/profile": f"تنظیمات، {NAME}",
    }
    for path, title in expect.items():
        r = client.get(path)
        assert r.status_code == 200
        assert _title(r.text) == title, path
        assert f'<span class="brand-name">{NAME}</span>' in r.text
        assert f'name="apple-mobile-web-app-title" content="{NAME}"' in r.text
        assert OLD not in r.text


def test_manifest_offline_and_push_defaults():
    m = json.loads((ROOT / "app/static/manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["name"] == NAME and m["short_name"] == NAME
    assert len(m["short_name"]) <= 12
    assert _title((ROOT / "app/static/offline.html").read_text(encoding="utf-8")) == f"بدون اتصال، {NAME}"
    assert f'|| "{NAME}"' in (ROOT / "app/static/push.js").read_text(encoding="utf-8")
    assert f'|| "{NAME}"' in (ROOT / "app/firebase_push.py").read_text(encoding="utf-8")


def test_api_docs_title_and_mcp_sample_key(client):
    from app.main import app
    assert app.title == "Daraiito"
    src = (ROOT / "app/profile.py").read_text(encoding="utf-8")
    assert '"daraiito": {' in src and f'title="{NAME}"' in src


def test_old_name_gone_from_app_templates_and_static():
    for base in ("app/templates", "app/static"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in {".html", ".js", ".css", ".webmanifest", ".py"}:
                assert OLD not in p.read_text(encoding="utf-8"), p


def test_protected_items_unchanged():
    # privacy toggle key: renaming it would un-hide hidden amounts
    assert 'portfolio: "privacy-portfolio"' in (ROOT / "app/static/privacy.js").read_text(encoding="utf-8")
    assert 'getItem("privacy-portfolio")' in (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    # Android: host + package id; APK file name / URL
    assert 'DEFAULT = "https://portfolio.vahidtwo.ir"' in (
        ROOT / "android/app/src/main/java/app/myinventory/ServerAddress.kt"
    ).read_text(encoding="utf-8")
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'applicationId = "app.myinventory"' in gradle and 'namespace = "app.myinventory"' in gradle
    assert 'href="/download/my-inventory.apk"' in (ROOT / "app/templates/landing.html").read_text(encoding="utf-8")
    assert (ROOT / "app/static/my-inventory.apk").exists()


def test_session_cookie_name_unchanged():
    from app.config import SESSION_COOKIE_NAME
    assert SESSION_COOKIE_NAME == "inventory_session"


def test_lock_button_label_is_one_text_node_without_double_space():
    """The lock label used to be text + <bdi> + text inside a flex button (gap 10px), so the number floated
    away from «دوباره امتحان کنید،». One text node, single spaces, same as what auth.js writes."""
    html = (ROOT / "app/templates/auth.html").read_text(encoding="utf-8")
    for label in ("دوباره امتحان کنید،", "ساخت حساب،"):
        assert f"{label} {{{{ minutes_fa }}}} دقیقهٔ دیگر</button>" in html
    assert "،  " not in html and "، <bdi" not in html
    js = (ROOT / "app/static/auth.js").read_text(encoding="utf-8")
    assert 'replace("{n}"' in js and "،  " not in js


def test_welcome_heading_does_not_orphan_last_word_and_update_sheet_copy_keeps_it_together():
    css = (ROOT / "app/static/style.css").read_text(encoding="utf-8")
    assert re.search(r"\.v2-welcome h1\{[^}]*text-wrap:balance", css)
    xml = (ROOT / "android/app/src/main/res/values/update_strings.xml").read_text(encoding="utf-8")
    assert "دوباره\u00a0یادآوری\u00a0می‌کنیم." in xml
    layout = (ROOT / "android/app/src/main/res/layout/update_sheet.xml").read_text(encoding="utf-8")
    assert 'android:breakStrategy="balanced"' in layout
    sms = (ROOT / "android/app/src/main/java/app/myinventory/SmsSettingsActivity.kt").read_text(encoding="utf-8")
    assert "ثبت\u00a0کنیم؟" in sms


def test_update_notice_is_dashboard_only_in_the_app_source():
    src = (ROOT / "android/app/src/main/java/app/myinventory/UpdateCheck.kt").read_text(encoding="utf-8")
    assert 'path == "/dashboard"' in src and '"/profile"' not in src
