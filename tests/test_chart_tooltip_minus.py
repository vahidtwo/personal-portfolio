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


def test_tooltip_isolates_the_signed_change_in_an_ltr_run():
    # On main the tooltip is only rtl: true, so canvas bidi paints «٪۲۰−»
    # and can jump the colon. The change value is wrapped in LRI…PDI and
    # the tooltip sets textDirection to rtl, so the pixels read «−۲۰٪»
    # with the minus before the digits and the colon after «قبل».
    fn = _fn("changeLabelForPoint")
    assert "isolateLtr" in fn
    assert _fn("isolateLtr")
    assert "LTR_ISOLATE" in JS and "\\u2066" in JS
    assert "POP_ISOLATE" in JS and "\\u2069" in JS
    assert "isolateLtr(change)" in fn
    assert 'textDirection: "rtl"' in JS
    assert "rtl: true" in JS
    assert "attachSignedChangeDraw" not in JS


def test_change_prefix_is_the_fixed_label():
    assert 'const CHANGE_LABEL_PREFIX = "تغییر نسبت به قبل: "' in JS


def test_hidden_page_html_has_no_chart_amounts(client, no_network):
    _register(client)
    client.post("/profile", data={"cash_toman": "800000", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    slot = re.search(r'<script id="chart-data"[^>]*data-amt-json="chart"[^>]*>null</script>', html)
    assert slot
    assert not re.search(r"−[۰-۹]", html)
