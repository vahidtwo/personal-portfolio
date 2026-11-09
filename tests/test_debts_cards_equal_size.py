"""Desktop debts grid: equal-width/height list cards; totals pinned to bottom."""
from pathlib import Path
import re

CSS = (Path(__file__).resolve().parent.parent / "app/static/style.css").read_text(encoding="utf-8")


def test_desktop_dv_grid_equal_columns_and_stretch():
    m = re.search(
        r"@media\s*\(min-width:900px\)\s*\{[^}]*\.dv-grid\{([^}]*)\}",
        CSS,
    )
    assert m, "missing ≥900px .dv-grid rule"
    block = m.group(1)
    assert "1.25fr" not in block
    assert re.search(r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)", block)
    assert re.search(r"align-items:\s*stretch", block)
    assert "align-items:start" not in block.replace(" ", "")


def test_list_cards_flex_pin_sumrow():
    compact = re.sub(r"\s+", "", CSS)
    assert ".dv-card:not(.dv-sum){display:flex;flex-direction:column}" in compact
    assert ".dv-card:not(.dv-sum).dv-sumrow{margin-top:auto}" in compact or \
           ".dv-card:not(.dv-sum) .dv-sumrow{margin-top:auto}".replace(" ", "") in compact
    assert re.search(
        r"\.dv-card:not\(\.dv-sum\)\s*>\s*\[data-dv-swap\]\s*\{[^}]*flex:\s*1\s+1\s+auto",
        CSS,
    )
    assert re.search(
        r"\.dv-card:not\(\.dv-sum\)\s+\.dv-sumrow\s*\{[^}]*margin-top:\s*auto",
        CSS,
    )
