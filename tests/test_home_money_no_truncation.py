"""Home dashboard: hero stats and tiles never cut money (an RTL ellipsis hides the largest digits); no unit leaks."""
from pathlib import Path
import re

CSS = (Path(__file__).resolve().parent.parent / "app/static/style.css").read_text(encoding="utf-8")


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _rules(selector_re: str) -> list[str]:
    return [_compact(m.group(1)) for m in re.finditer(r"(?:^|[}\s])" + selector_re + r"\s*\{([^{}]*)\}", CSS, re.M)]


def _media(query: str) -> str:
    return _compact("\n".join(re.findall(r"@media\s*\(" + query + r"\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", CSS)))


def test_stat_and_tile_amounts_have_no_ellipsis():
    for sel in (r"\.stat dd", r"\.tile \.v"):
        rules = _rules(sel)
        assert rules, sel
        for body in rules:
            assert "ellipsis" not in body and "overflow:hidden" not in body, sel
    assert "font-size:clamp(15px,4.4vw,17px)" in _rules(r"\.tile \.v")[0]


def test_hidden_stats_show_no_unit():
    rules = _rules(r'html:not\(\[data-show-portfolio="1"\]\) \.stat dd\[data-mask\] > small')
    assert rules and "display:none" in rules[0]


def test_phones_wrap_boxes_that_cannot_fit():
    mobile = _media("max-width: ?899px")
    assert ".stats,.dash-tiles{display:flex;flex-wrap:wrap;}" in mobile
    assert ".stat{flex:110;min-width:min-content;}" in mobile
    assert ".tile{flex:11calc(50%-5px);min-width:min-content;}" in mobile
    assert ".dash-hero.total-num{white-space:normal;overflow-wrap:anywhere;}" in mobile
    assert CSS.index("@media (max-width: 899px) {\n  .stats, .dash-tiles") > CSS.index(".tiles { display: grid;")


REVEALED_HERO = 'html[data-show-portfolio="1"].dash-hero[data-mask="portfolio"].total-num{'


def test_revealed_hero_scales_with_its_card_on_phones():
    assert any("container-type:inline-size" in body for body in _rules(r"\.dash-hero"))
    mobile = _media("max-width: ?899px")
    assert REVEALED_HERO + "font-size:clamp(22px,11cqi,40px)!important;}" in mobile
    assert REVEALED_HERO not in _media("max-width: ?380px")  # a later phone rule would override the card-based size
    assert mobile.index(REVEALED_HERO) < mobile.index(".dash-hero.total-num{white-space:normal;overflow-wrap:anywhere;}")


def test_report_amount_drops_under_its_label_instead_of_spilling():
    assert any("display:flex" in b for b in _rules(r"\.net-line div"))
    shown = _rules(r'html\[data-show-portfolio="1"\] \.net-line div')
    assert shown and "flex-wrap:wrap" in shown[0]
    base = re.search(r"^\.net-line div \{([^{}]*)\}", CSS, re.M)
    assert base and "flex-wrap" not in base.group(1)  # hidden rows keep their old layout
    body = "".join(_rules(r"\.net-line dd\.num"))
    assert "min-width:min-content" in body and "margin-inline-start:auto" in body
    assert any(r.startswith(".net-line dd.num") and "white-space: nowrap" in r for r in re.findall(r"^[^{}\n]*\{[^{}]*\}", CSS, re.M))
