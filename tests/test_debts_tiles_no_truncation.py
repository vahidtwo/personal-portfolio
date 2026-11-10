"""Debts «این ماه» tiles: amounts are never cut off (an RTL ellipsis hides the largest digits)."""
from pathlib import Path
import re

CSS = (Path(__file__).resolve().parent.parent / "app/static/style.css").read_text(encoding="utf-8")
CLAMP = "clamp(15px,4.4vw,19px)"


def _rules(selector_re: str) -> list[str]:
    return [m.group(1) for m in re.finditer(selector_re + r"\s*\{([^{}]*)\}", CSS)]


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_tile_amount_has_no_ellipsis_and_fluid_size():
    rules = _rules(r"(?<![\w-])\.dv-tile b")
    assert rules, "missing .dv-tile b rule"
    for body in rules:
        body = _compact(body)
        assert "ellipsis" not in body and "overflow:hidden" not in body
    main = _compact(rules[0])
    assert "overflow:visible" in main and "text-overflow:clip" in main and f"font-size:{CLAMP}" in main
    assert not any(re.search(r"font-size:\d", _compact(b)) for b in rules)  # no fixed size override below 600px


def test_revealed_amount_keeps_the_fluid_size():
    reveal = _rules(r'html\[data-show-portfolio="1"\] \.dv-tile b\[data-mask="portfolio"\]')
    assert reveal and f"font-size:{CLAMP}!important" in _compact(reveal[0])
    generic = CSS.index('html[data-show-portfolio="1"] [data-mask="portfolio"]')
    assert CSS.index('html[data-show-portfolio="1"] .dv-tile b[data-mask="portfolio"]') > generic  # wins on order too


def test_mobile_tiles_wrap_and_total_takes_a_full_row():
    blocks = re.findall(r"@media\s*\(max-width:899px\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", CSS)
    mobile = _compact("\n".join(blocks))
    assert ".dv-tiles{display:flex;flex-wrap:wrap}" in mobile
    assert "min-width:min-content" in mobile
    assert ".dv-tiles>.dv-tile:not(.dv-left):nth-child(odd):nth-last-child(2),.dv-tile.dv-left{flex-basis:100%}" in mobile
