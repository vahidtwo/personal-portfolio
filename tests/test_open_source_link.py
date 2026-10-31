"""The public source link: landing footer + Settings, new tab on the web, external browser in the app."""
import re
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/vahidtwo/personal-portfolio"
COPY = "دارایی\u200cتو متن\u200cباز است"


def _links(html):
    return [m.group(0) for m in re.finditer(r"<a\b[^>]*>", html) if "github.com" in m.group(0)]


def _assert_one_safe_link(html):
    links = _links(html)
    assert len(links) == 1, links
    a = links[0]
    assert f'href="{URL}"' in a
    assert 'target="_blank"' in a
    assert 'rel="noopener noreferrer"' in a
    assert COPY in html and "clone" in html


def test_landing_footer_has_source_link(client, no_network):
    html = client.get("/").text
    footer = html[html.index("<footer"):html.index("</footer>")]
    _assert_one_safe_link(footer)


def test_settings_page_has_source_link(client, no_network):
    _register(client)
    r = client.get("/profile?section=settings")
    assert r.status_code == 200
    section = r.text[r.text.index('id="open-source"'):]
    section = section[:section.index("</section>")]
    _assert_one_safe_link(section)


def test_every_github_link_in_templates_is_the_exact_url_and_safe():
    for p in (ROOT / "app/templates").rglob("*.html"):
        for a in _links(p.read_text(encoding="utf-8")):
            assert f'href="{URL}"' in a and 'target="_blank"' in a and 'rel="noopener noreferrer"' in a, (p, a)


def test_android_opens_github_in_external_browser():
    sa = (ROOT / "android/app/src/main/java/app/myinventory/ServerAddress.kt").read_text(encoding="utf-8")
    assert 'val EXTERNAL_HOSTS = setOf("github.com")' in sa
    assert '"github.com"' not in sa[sa.index("KNOWN_HOSTS"):sa.index("\n", sa.index("KNOWN_HOSTS"))]
    main = (ROOT / "android/app/src/main/java/app/myinventory/MainActivity.kt").read_text(encoding="utf-8")
    body = main[main.index("override fun shouldOverrideUrlLoading"):]
    ext = body.index("ServerAddress.opensExternally(target.scheme, target.host)")
    assert ext < body.index("if (isAllowedRemoteUrl(target)) return false")
    assert "Intent.ACTION_VIEW, target" in body[ext:ext + 300]
