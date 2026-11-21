"""Keyboard order (section bar after the page content in the HTML) and skip-link contrast."""
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


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_skip_link_dark_text_on_teal():
    css = CSS.read_text(encoding="utf-8")
    rule = css[css.index(".skip-link {"):]
    rule = rule[:rule.index("}")]
    assert "background: var(--accent);" in rule and "color: #04120e;" in rule
    for teal in ("#3ee0b8", "#0d9f7a"):  # dark and light theme accent
        assert _ratio("#04120e", teal) >= 4.5
