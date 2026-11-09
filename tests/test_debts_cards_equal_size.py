"""Desktop debts grid: equal-width/height list cards; totals pinned to bottom (≥900px only)."""
from pathlib import Path
import re

CSS = (Path(__file__).resolve().parent.parent / "app/static/style.css").read_text(encoding="utf-8")


def _min_width_900_blocks() -> list[str]:
    return re.findall(r"@media\s*\(min-width:900px\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", CSS)


def test_desktop_dv_grid_equal_columns_and_stretch():
    blocks = _min_width_900_blocks()
    grid_blocks = [b for b in blocks if ".dv-grid{" in b]
    assert grid_blocks, "missing ≥900px .dv-grid rule"
    block = grid_blocks[0]
    inner = re.search(r"\.dv-grid\{([^}]*)\}", block).group(1)
    assert "1.25fr" not in inner
    assert re.search(r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)", inner)
    assert re.search(r"align-items:\s*stretch", inner)
    assert "align-items:start" not in inner.replace(" ", "")


def test_list_cards_flex_pin_sumrow_only_desktop():
    blocks = _min_width_900_blocks()
    desktop = "\n".join(blocks)
    compact_desktop = re.sub(r"\s+", "", desktop)
    assert ".dv-card:not(.dv-sum){display:flex;flex-direction:column}" in compact_desktop
    assert ".dv-card:not(.dv-sum).dv-sumrow{margin-top:auto}" in compact_desktop
    assert re.search(
        r"\.dv-card:not\(\.dv-sum\)\s*>\s*\[data-dv-swap\]\s*\{[^}]*flex:\s*1\s+1\s+auto",
        desktop,
    )
    # Must not appear as a top-level (mobile-affecting) rule outside any @media
    outside = re.sub(r"@media[^{]+\{(?:[^{}]|\{[^{}]*\})*\}", "", CSS)
    compact_out = re.sub(r"\s+", "", outside)
    assert ".dv-card:not(.dv-sum){display:flex;flex-direction:column}" not in compact_out
    assert ".dv-card:not(.dv-sum).dv-sumrow{margin-top:auto}" not in compact_out
