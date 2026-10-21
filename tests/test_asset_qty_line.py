from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    start = CSS.index(selector + " {")
    return CSS[start:CSS.index("}", start)]


def test_home_asset_quantity_line_is_never_truncated():
    # Arabi spec: the name and quantity keep their full width, no «…» at 360px.
    rule = _rule(".acard .nm > span")
    assert "text-overflow" not in rule and "nowrap" not in rule and "overflow: hidden" not in rule
    assert "overflow-wrap: anywhere" in rule
    assert ".acard .nm > span bdi { white-space: nowrap; }" in CSS  # numbers never split mid-value
