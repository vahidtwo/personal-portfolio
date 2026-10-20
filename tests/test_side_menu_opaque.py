"""Mobile side menu: opaque panel, 60% black backdrop that closes the menu on tap (Arabi spec)."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text(encoding="utf-8")
BASE = (Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html").read_text(encoding="utf-8")


def _rule(sel):
    return re.search(r"(?m)^" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS).group(1)


def _hex_bg(theme_block_start):
    return re.search(r"--bg:\s*(#[0-9a-fA-F]{6})\s*;", CSS[theme_block_start:]).group(1)


def test_side_panel_uses_opaque_page_background():
    body = _rule(".side-panel")
    assert re.search(r"background:\s*var\(--bg\)\s*;", body)
    # --bg is a solid hex colour in both themes (not rgba)
    assert _hex_bg(0)
    assert _hex_bg(CSS.index('[data-theme="light"]'))


def test_side_backdrop_is_60_percent_black_and_closes_menu():
    body = _rule(".side-backdrop")
    assert re.search(r"background:\s*rgba\(0,\s*0,\s*0,\s*0?\.6\)", body)
    assert 'backdrop.addEventListener("click", function () { setOpen(false); });' in BASE
