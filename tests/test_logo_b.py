"""Logo B (web): new files exist, no live <text>, no glow/radius on the header logo, asset version bumped."""
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def test_logo_svgs_have_no_live_text():
    for p in [STATIC / "logo.svg", *(STATIC / "brand").glob("*.svg")]:
        assert "<text" not in p.read_text(encoding="utf-8"), p


def test_new_icon_files_exist():
    for name in ["favicon.ico", "icons/favicon-16.png", "icons/favicon-32.png", "icons/apple-touch-icon.png",
                 "icons/icon-192.png", "icons/icon-512.png", "icons/icon-maskable-512.png",
                 "brand/daraiito-symbol-dark.svg", "brand/daraiito-symbol-light.svg"]:
        assert (STATIC / name).is_file(), name


def test_retired_colours_gone_from_logo():
    svg = (STATIC / "logo.svg").read_text(encoding="utf-8").lower()
    assert "#3ee0b8" in svg and "#04120e" in svg
    assert "lineargradient" not in svg and "blur" not in svg


def test_header_logo_has_no_glow_or_radius():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    block = css.split(".brand-logo {", 1)[1].split("}", 1)[0]
    assert "box-shadow" not in block and "border-radius" not in block
    pub = (STATIC / "public.css").read_text(encoding="utf-8")
    assert "border-radius:9px;box-shadow:0 8px 22px var(--accent-glow)" not in pub


def test_asset_version_bumped_and_precached():
    from app.config import STATIC_ASSET_VERSION
    assert STATIC_ASSET_VERSION >= "20261028e"
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    for p in ["/static/favicon.ico", "/static/brand/daraiito-symbol-dark.svg", "/static/brand/daraiito-symbol-light.svg"]:
        assert f'"{p}"' in sw


def test_pages_link_favicon_and_theme_logos(client):
    html = client.get("/auth").text
    assert '/static/favicon.ico' in html and 'daraiito-symbol-light.svg' in html
    assert client.get("/static/favicon.ico").status_code == 200


def test_png_favicons_linked_and_avatar_flat(client):
    for path in ("/", "/auth"):
        html = client.get(path).text
        assert "/static/icons/favicon-16.png" in html and "/static/icons/favicon-32.png" in html
    pub = (STATIC / "public.css").read_text(encoding="utf-8")
    assert ".avatar{" in pub and "background:#3ee0b8}" in pub.split(".avatar{", 1)[1].split("\n", 1)[0]
