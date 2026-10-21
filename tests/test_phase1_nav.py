"""Phase 1 step 1: five-section main navigation in the shared layout (template/CSS only, no DB changes)."""
import re
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

NAV_ORDER = [
    ("home", "خانه", "/dashboard"),
    ("assets", "دارایی‌ها", "/assets"),
    ("spending", "خرج‌ها", "/dashboard?tab=daily"),
    ("debts", "بدهی‌ها", "/profile?tab=debts"),
    ("settings", "تنظیمات", "/profile?section=settings#account-settings"),
]
CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"


def _nav(html):
    m = re.search(r'<nav class="main-nav".*?</nav>', html, re.S)
    assert m, "main nav missing"
    return m.group(0)


def _items(nav_html):
    return re.findall(r'<a class="main-nav-item( is-active)?" href="([^"]+)" data-nav="(\w+)"', nav_html)


def test_nav_renders_for_logged_in_user_with_five_links_in_rtl_order(client, no_network):
    _register(client)
    html = client.get("/dashboard").text
    assert html.count('class="main-nav"') == 1
    nav = _nav(html)
    items = _items(nav)
    assert [(k, h) for _, h, k in items] == [(k, h.replace("&", "&amp;")) for k, _, h in NAV_ORDER]
    labels = re.findall(r'<span class="main-nav-label">([^<]+)</span>', nav)
    assert labels == [label for _, label, _ in NAV_ORDER]
    # full section name kept for assistive tech / tooltip
    assert 'aria-label="بدهی‌ها و هزینهٔ ماهانه"' in nav
    assert 'class="app-body has-main-nav"' in html
    # every link target is a real page today
    for _, _, href in NAV_ORDER:
        assert client.get(href.split("#")[0]).status_code == 200


def test_nav_not_rendered_for_anonymous(client):
    for path in ("/", "/login", "/register"):
        html = client.get(path).text
        assert 'class="main-nav"' not in html
        assert "has-main-nav" not in html
        assert "is-typing" not in html


def test_nav_highlights_exactly_one_active_section(client, no_network):
    _register(client)
    cases = {
        "/dashboard": "home",
        "/dashboard?tab=daily": "spending",
        "/assets": "assets",
        "/profile": "settings",
        "/profile?tab=debts": "debts",
        "/profile?section=settings": "settings",
    }
    for path, key in cases.items():
        nav = _nav(client.get(path).text)
        active = [k for a, _, k in _items(nav) if a]
        assert active == [key], (path, active)
        assert nav.count('aria-current="page"') == 1
        assert nav.count("is-filled") == 1  # filled icon only on the active tab


def test_settings_anchor_exists_and_profile_features_unchanged(client, no_network):
    _register(client)
    html = client.get("/profile?section=settings").text
    assert 'id="account-settings"' in html
    assert 'name="new_password"' in html  # account form is shown under settings
    assert 'name="gold_grams"' not in html  # Phase 1 piece 2: assets moved to /assets
    # privacy toggle and the collapsed «پیشرفته» MCP section are untouched
    # Debts v2: the «مانده از حقوق» tile (with the eye button) shows once there is a debt or a monthly expense.
    client.post("/profile/expenses", data={"title": "اجاره", "amount_toman": "1000", "due_day": "1", "csrf": _csrf(client, "/profile?tab=debts")})
    assert 'data-salary-reveal' in client.get("/profile?tab=debts").text
    assert 'id="advanced"' in html and 'id="mcp-heading"' in html
    assert 'localStorage.getItem("privacy-portfolio") !== "1"' in html


def test_admin_link_and_logout_still_in_side_menu(client, no_network):
    _register(client)
    html = client.get("/dashboard").text
    assert 'action="/logout"' in html and 'id="menu-toggle"' in html
    assert 'href="/profile">پروفایل</a>' in html


def _make_admin(monkeypatch, name="boss"):
    import app.security as sec
    monkeypatch.setattr(sec, "ADMIN_USERNAMES", frozenset({name}))


def test_settings_has_logout_row_and_no_admin_link_for_regular_user(client, no_network):
    _register(client, "regular")
    html = client.get("/profile?section=settings").text
    rows = html[html.index('id="settings-account-actions"'):]
    rows = rows[:rows.index("</section>")]
    assert "خروج از حساب" in rows and 'action="/logout"' in rows and 'name="csrf"' in rows
    # admin entry is decided on the server: not in the HTML at all for non-admins
    assert 'href="/admin"' not in html
    assert "مدیریت" not in html
    # desktop avatar menu (side panel) also offers logout
    assert html.count("خروج از حساب") == 2
    assert 'class="avatar"' in html


def test_admin_sees_admin_row_in_settings_and_menu(client, no_network, monkeypatch):
    _make_admin(monkeypatch)
    _register(client, "boss")
    html = client.get("/profile?section=settings").text
    rows = html[html.index('id="settings-account-actions"'):]
    rows = rows[:rows.index("</section>")]
    assert 'href="/admin"' in rows and "مدیریت" in rows
    assert rows.index("مدیریت") < rows.index("خروج از حساب")  # logout is the last row
    assert html.count('href="/admin"') == 2  # settings row + avatar/side menu
    assert client.get("/admin").status_code == 200


def test_logout_row_logs_out(client, no_network):
    _register(client, "leaver")
    t = _csrf(client, "/profile?section=settings")
    r = client.post("/logout", data={"csrf": t}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert 'class="main-nav"' not in client.get("/").text


def test_bottom_bar_css_contract():
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index("Main navigation (Phase 1"):]
    mobile = block[block.index("@media (max-width: 899px) {"):]
    desktop = block[block.index("@media (min-width: 900px) {"):]
    assert "--main-nav-h: 56px" in block
    assert "position: fixed" in mobile and "bottom: 0" in mobile
    assert "height: calc(var(--main-nav-h) + env(safe-area-inset-bottom));" in mobile  # bar + home indicator
    assert "body.has-main-nav { padding-bottom: calc(var(--main-nav-h) + env(safe-area-inset-bottom) + var(--page-extra-bottom)); }" in mobile
    assert "minmax(var(--main-nav-item-min), 1fr)" in mobile and "--main-nav-item-min: 44px" in block
    assert "html.is-typing .main-nav" in mobile  # keyboard open -> bar hidden
    # desktop: the nav (after <main> in the HTML) is placed in the top bar with fixed positioning
    assert "position: fixed" in desktop[:desktop.index("@media (max-width: 899px)")]
    assert ".top-tabs" not in css and "#6b7287" not in css.lower()
    assert "::placeholder { color: var(--text-muted)" in css
