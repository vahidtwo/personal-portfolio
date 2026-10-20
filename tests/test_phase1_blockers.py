"""Phase 1 assets: Gorg's blocker, accessibility and minor fixes (Matin's QA round at f30677e)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
TEMPLATES = ROOT / "app" / "templates"
SW_HARNESS = ROOT / "tests" / "js" / "sw_harness.js"


# ---- 1. Back/Forward keeps typed input ---------------------------------------------------------

def test_form_pages_send_no_cache_not_no_store(client, no_network):
    _register(client)
    for path in ("/assets", "/profile?tab=debts", "/profile", "/dashboard?tab=daily"):
        cc = client.get(path).headers["cache-control"]
        assert cc == "no-cache, private", (path, cc)
    assert client.get("/dashboard").headers["cache-control"] == "no-store"  # no form: unchanged


@pytest.mark.parametrize("path", ["/assets", "/profile", "/profile?tab=debts", "/dashboard?tab=daily"])
def test_user_forms_have_no_autocomplete_off(client, no_network, path):
    _register(client)
    html = client.get(path).text
    for tag in re.findall(r"<(?:input|form|textarea|select)\b[^>]*>", html):
        if 'type="password"' in tag:  # the Sanjeh token field: browsers never restore passwords anyway
            continue
        if 'name="salary_toman"' in tag:  # #7 salary privacy: the empty edit box must never be refilled
            continue
        assert 'autocomplete="off"' not in tag, (path, tag)


def test_spend_form_has_leave_warning(client, no_network):
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    assert re.search(r'<form[^>]*id="daily-spend-form"[^>]*data-leave-warn', html)
    assert "/static/leave-guard.js" in html
    js = (STATIC / "leave-guard.js").read_text(encoding="utf-8")
    assert 'addEventListener("beforeunload"' in js and "defaultValue" in js
    assert "if (submitting) return;" in js  # submitting never warns
    assert '"/static/leave-guard.js"' in (STATIC / "sw.js").read_text(encoding="utf-8")


def test_leave_guard_dirty_logic_in_node():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    js = (STATIC / "leave-guard.js").read_text(encoding="utf-8")
    code = """
const listeners = {};
function input(name, value, def) { return { name, type: "text", tagName: "INPUT", value, defaultValue: def }; }
const form = { elements: [], addEventListener(t, f) { listeners["form:" + t] = f; } };
global.document = { querySelectorAll: () => [form] };
global.window = { addEventListener(t, f) { listeners[t] = f; } };
eval(process.argv[1]);
const res = [];
function leave() { const e = { returnValue: undefined, preventDefault() { this.p = true; } }; listeners.beforeunload(e); return !!e.p; }
form.elements = [input("amount_toman", "", ""), input("year", "1405", "1405"), { name: "csrf", type: "hidden", value: "x", defaultValue: "y" }];
res.push(leave());                       // untouched (prefilled date, hidden fields ignored) -> no warning
form.elements[0].value = "150000";
res.push(leave());                       // typed -> warning
listeners["form:submit"]({ defaultPrevented: false });
res.push(leave());                       // submitting -> no warning
listeners.pageshow({});
listeners["form:submit"]({ defaultPrevented: true });
res.push(leave());                       // submit cancelled (offline) -> still warns
console.log(JSON.stringify(res));
"""
    out = subprocess.run(["node", "-e", code, js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [False, True, False, True]


# ---- 2. Offline dashboard copy never outlives the session ------------------------------------

def _sw(steps, max_age=1000):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    scenario = json.dumps({"maxAgeMs": max_age, "steps": steps})
    out = subprocess.run(["node", str(SW_HARNESS), str(STATIC / "sw.js"), scenario],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_sw_is_served_with_the_session_max_age(client):
    from app.config import SESSION_MAX_AGE_SECONDS
    body = client.get("/sw.js").text
    assert "__SESSION_MAX_AGE_MS__" not in body
    assert f'Number("{SESSION_MAX_AGE_SECONDS * 1000}")' in body
    assert SESSION_MAX_AGE_SECONDS == 60 * 60 * 24 * 30
    from app.main import app
    mw = next(m for m in app.user_middleware if m.cls.__name__ == "SessionMiddleware")
    assert mw.kwargs["max_age"] == SESSION_MAX_AGE_SECONDS  # one value for cookie and offline copy


def test_sw_offline_copy_expires_at_session_max_age():
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},  # cached with a timestamp
        {"online": False, "advance": 500, "go": "/dashboard"},        # still inside the session
        {"online": False, "advance": 600, "go": "/dashboard"},        # 1100 ms > 1000 ms: expired
    ])
    assert r[0]["pages"] == ["https://app.test/dashboard"]
    assert "dashboard private" in r[1]["body"]
    assert "dashboard private" not in r[2]["body"] and "offline page" in r[2]["body"]
    assert r[2]["pages"] == []  # the expired copy was deleted, not just skipped


def test_sw_fallback_to_other_dashboard_tab_also_checks_expiry():
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard?tab=daily"},
        {"online": False, "advance": 200, "go": "/dashboard"},
        {"online": False, "advance": 2000, "go": "/dashboard"},
    ])
    assert "dashboard private" in r[1]["body"]
    assert "offline page" in r[2]["body"]


@pytest.mark.parametrize("status", [401, 403])
def test_sw_clears_offline_copy_on_401_403(status):
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "status", "status": status, "go": "/dashboard"},
        {"online": False, "go": "/dashboard"},
    ])
    assert r[1]["pages"] == []
    assert "offline page" in r[2]["body"]


def test_sw_clears_offline_copy_on_401_from_an_api_call():
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "status", "status": 401, "go": "/api/anything", "opts": {"mode": "cors"}},
    ])
    assert r[1]["handled"] and r[1]["pages"] == []


@pytest.mark.parametrize("kind", ["redirect-login", "opaqueredirect"])
def test_sw_clears_offline_copy_on_redirect_to_login(kind):
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": kind, "go": "/dashboard"},
        {"online": False, "go": "/dashboard"},
    ])
    assert r[1]["pages"] == []
    assert "offline page" in r[2]["body"]


def test_sw_clears_offline_copy_when_login_page_is_opened():
    # e.g. the session expired and a form POST was redirected to /login by the server
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "login-page", "go": "/login"},
        {"online": False, "go": "/dashboard"},
    ])
    assert r[1]["pages"] == [] and "login" in r[1]["body"]
    assert "offline page" in r[2]["body"]


def test_sw_clears_offline_copy_on_logout():
    r = _sw([
        {"online": "ok", "offline_html": True, "go": "/dashboard"},
        {"online": "opaqueredirect", "go": "/logout", "opts": {"method": "POST"}},
        {"online": False, "go": "/dashboard"},
    ])
    assert r[1]["pages"] == []
    assert "offline page" in r[2]["body"]


def test_logout_clears_browser_cache_and_marks_bfcache(client, no_network):
    _register(client)
    r = client.post("/logout", data={"csrf": _csrf(client, "/dashboard")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/auth"
    assert r.headers["clear-site-data"] == '"cache"'
    js = (STATIC / "pwa.js").read_text(encoding="utf-8")
    assert "inventory-logged-out-at" in js and "event.persisted" in js


# ---- 3. Accessibility --------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/login", "/assets", "/profile?tab=debts", "/dashboard?tab=daily"])
def test_skip_link_is_first_focusable(client, no_network, path):
    if path not in ("/", "/login"):
        _register(client)
    html = client.get(path).text
    body = html[html.index("<body"):]
    first = re.search(r"<(a|button|input|select|textarea)\b[^>]*>", body[body.index(">") + 1:]).group(0)
    assert 'class="skip-link"' in first and 'href="#main"' in first, first
    assert "رفتن به محتوا" in body[:400]
    assert '<main id="main"' in html
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.skip-link:focus\s*\{[^}]*top:", css)  # moved on screen when focused


def _luminance(hex_color):
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_asset_chip_contrast_at_least_4_5_in_both_themes():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    dark = css[: css.index('[data-theme="light"] {')]
    light = css[css.index('[data-theme="light"] {'):]
    light = light[: light.index("}")]
    chip = re.search(r"\.asset-chip \{[^}]*\}", css).group(0)
    assert "var(--chip-text, var(--accent))" in chip
    light_fg = re.search(r"--chip-text:\s*(#[0-9a-fA-F]{6})", light).group(1)
    dark_fg = re.search(r"--accent:\s*(#[0-9a-fA-F]{6})", dark).group(1)
    assert "--chip-text" not in dark  # dark theme uses the accent
    # light card is white (#fefefe measured), hover tint ~#e2f2ee; dark card ~#0c0e14, hover ~#13302b
    for bg in ("#fefefe", "#eef1f8", "#e2f2ee"):
        assert _contrast(light_fg, bg) >= 4.5, (light_fg, bg)
    for bg in ("#0c0e14", "#1a1e28", "#13302b"):
        assert _contrast(dark_fg, bg) >= 4.5, (dark_fg, bg)


def test_edit_delete_spacing_and_delete_at_far_end(client, no_network):
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    base = re.search(r"\n\.row-actions \{[^}]*\}", css).group(0)
    assert "gap: 12px" in base
    assert re.search(r"\.row-actions \.inline-form \{\s*margin-inline-start: auto;", css)
    mobile = css[css.index("@media (max-width: 720px)"):]
    rule = re.search(r"\.data-table \.row-actions \{[^}]*\}", mobile).group(0)
    assert "flex-direction: row" in rule and "gap: 12px" in rule and "space-between" in rule
    # DOM: «ویرایش» first, «حذف» (the form) last in each actions cell
    _register(client)
    for path in ("/profile?tab=debts", "/dashboard?tab=daily"):
        for cell in re.findall(r'<td class="row-actions">(.*?)</td>', client.get(path).text, re.S):
            assert cell.index("ویرایش") < cell.index("حذف")


# ---- 4. Minor ----------------------------------------------------------------------------------

def test_debts_heading_is_not_edit_inventory(client, no_network):
    _register(client)
    html = client.get("/profile?tab=debts").text
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1).strip()
    assert h1 == "بدهی‌ها و هزینهٔ ماهانه"
    assert "ویرایش موجودی" not in h1


def _replace_state(html):
    m = re.search(r'history\.replaceState\(history\.state, "", "([^"]*)"\)', html)
    return m.group(1).replace("\\u0026", "&") if m else None


def test_invalid_asset_save_shows_assets_url(client, no_network):
    _register(client)
    r = client.post("/profile", data={"gold_grams": "abc", "next": "/assets", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 200 and "نامعتبر" in r.text
    assert _replace_state(r.text) == "/assets"


def test_invalid_debt_save_shows_debts_url(client, no_network):
    _register(client)
    t = _csrf(client, "/profile?tab=debts")
    r = client.post("/profile/debts", data={"csrf": t, "title": "x", "monthly_toman": "abc", "months_left": "3",
                                            "due_year": "1405", "due_month": "8", "due_day": "1"})
    assert r.status_code == 200 and 'role="alert"' in r.text
    assert _replace_state(r.text) == "/profile?tab=debts"
    assert "بدهی‌ها و هزینهٔ ماهانه" in r.text


def test_invalid_expense_and_account_saves_show_their_tab_url(client, no_network):
    _register(client)
    t = _csrf(client, "/profile?tab=debts")
    r = client.post("/profile/expenses", data={"csrf": t, "title": "x", "amount_toman": "abc", "due_day": "1"})
    assert r.status_code == 200 and _replace_state(r.text) == "/profile?tab=debts"
    r = client.post("/profile/account", data={"csrf": t, "username": "a", "full_name": "", "mobile": "",
                                              "salary_toman": "0"})
    assert r.status_code == 200 and _replace_state(r.text) == "/profile"


def test_invalid_spend_save_shows_daily_url(client, no_network):
    _register(client)
    t = _csrf(client, "/dashboard?tab=daily")
    r = client.post("/profile/spends", data={"csrf": t, "amount_toman": "abc", "year": "1405", "month": "7",
                                             "day": "20", "note": "", "category_id": "", "parent_id": "",
                                             "jy": "1405", "jm": "7"})
    assert r.status_code == 200 and 'role="alert"' in r.text
    assert _replace_state(r.text) == "/dashboard?tab=daily&jy=1405&jm=7"


def test_plain_get_pages_do_not_rewrite_the_address_bar(client, no_network):
    _register(client)
    for path in ("/assets", "/profile?tab=debts", "/dashboard?tab=daily"):
        assert "history.replaceState(history.state" not in client.get(path).text


# ---- 5. Static version bump --------------------------------------------------------------------

def test_static_asset_version_bumped():
    from app.config import STATIC_ASSET_VERSION
    assert STATIC_ASSET_VERSION >= "20261017s"  # bumped on every static change
