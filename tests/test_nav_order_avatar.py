"""Keyboard order (section bar after the page content in the HTML) and avatar contents/contrast."""
import re
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"


def test_nav_comes_after_main_in_the_html_and_skip_link_targets_main(client, no_network):
    _register(client)
    for path in ("/dashboard", "/assets", "/profile"):
        html = client.get(path).text
        assert html.index('<a class="skip-link" href="#main">') < html.index('<header class="top">')
        assert '<main id="main"' in html
        main_end = html.index("</main>")
        nav = html.index('<nav class="main-nav"')
        assert nav > main_end, path  # Tab reaches the page before the bottom/top section bar
        assert nav < html.index('<footer class="foot">')
        header = html[html.index('<header class="top">'):html.index("</header>")]
        assert "main-nav" not in header
    # side menu open: the section bar is made inert with the rest of the page
    assert '["main", "top", "foot", "main-nav"]' in html


def _set_name(client, full_name):
    t = _csrf(client, "/profile")
    client.post("/profile/account", data={"full_name": full_name, "username": "alice", "mobile": "",
                                          "salary_toman": "", "current_password": "", "new_password": "", "csrf": t})


def _avatar(html):
    return re.search(r'<span class="avatar" aria-hidden="true">(.*?)</span>', html, re.S).group(1)


def test_avatar_shows_person_icon_without_full_name_and_initial_with_it(client, no_network):
    _register(client)
    av = _avatar(client.get("/dashboard").text)
    assert 'class="avatar-icon"' in av and "A" not in av and "a" not in re.sub(r"<[^>]+>", "", av)
    _set_name(client, "  وحید")
    av = _avatar(client.get("/dashboard").text)
    assert av == "و"
    _set_name(client, "   ")
    assert 'class="avatar-icon"' in _avatar(client.get("/dashboard").text)


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_avatar_text_is_dark_on_teal_in_both_themes():
    css = CSS.read_text(encoding="utf-8")
    nav = css[css.index("Main navigation (Phase 1"):]
    dark = nav[:nav.index('[data-theme="light"]')]
    light = nav[nav.index('[data-theme="light"]'):nav.index("}", nav.index('[data-theme="light"]'))]
    assert "--avatar-fg: #04120e" in dark and "--avatar-fg: #04120e" in light and "#ffffff" not in light
    # the letter sits on the teal part of the gradient: >= 4.5:1 against both themes' teal and the middle stop
    for teal in ("#3ee0b8", "#0d9f7a", "#5ad4f0"):
        assert _ratio("#04120e", teal) >= 4.5, teal


def test_skip_link_dark_text_on_teal():
    css = CSS.read_text(encoding="utf-8")
    rule = css[css.index(".skip-link {"):]
    rule = rule[:rule.index("}")]
    assert "background: var(--accent);" in rule and "color: #04120e;" in rule
    for teal in ("#3ee0b8", "#0d9f7a"):  # dark and light theme accent
        assert _ratio("#04120e", teal) >= 4.5
