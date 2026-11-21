"""Chart tooltips: a negative change reads «−۲۰٪», with the minus before the digits."""
from pathlib import Path
import re

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "app/static/dashboard.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    m = re.search(rf"function {name}\([^)]*\) \{{", JS)
    assert m, name
    start = m.start()
    i = JS.find("{", m.end() - 1)
    depth = 0
    for j in range(i, len(JS)):
        if JS[j] == "{":
            depth += 1
        elif JS[j] == "}":
            depth -= 1
            if depth == 0:
                return JS[start : j + 1]
    raise AssertionError("unclosed " + name)


def test_format_change_puts_the_minus_before_the_digits():
    fn = _fn("formatChangeFromPrevious")
    assert 'sign = "−"' in fn
    assert 'return sign + body + "٪"' in fn


def test_tooltip_draws_the_signed_change_left_to_right():
    # This is the test that fails on main: the signed change was one RTL fillText, so the
    # minus sat after the digits («۲۰٪−»). The number is now its own left-to-right run.
    fn = _fn("attachSignedChangeDraw")
    assert 'this.direction = "ltr"' in fn
    assert "CHANGE_LABEL_PREFIX" in fn
    assert "orig(change," in fn
    assert "attachSignedChangeDraw(chart.ctx)" in JS
    assert "rtl: true" in JS  # the tooltip itself stays RTL so the Persian label is unchanged
    # bidi isolates in the string made the canvas worse; do not put them in the change text
    assert "\u2066" not in fn and "\u2067" not in fn and "\u2068" not in fn


def test_change_prefix_is_the_fixed_label():
    assert 'const CHANGE_LABEL_PREFIX = "تغییر نسبت به قبل: "' in JS


def test_hidden_page_html_has_no_chart_amounts(client, no_network):
    _register(client)
    client.post("/profile", data={"cash_toman": "800000", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    slot = re.search(r'<script id="chart-data"[^>]*data-amt-json="chart"[^>]*>null</script>', html)
    assert slot
    assert not re.search(r"−[۰-۹]", html)
