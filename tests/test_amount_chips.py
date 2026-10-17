"""Daily-spend amount chips (amount-input.js) are client-side; test the pure helpers with node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "amount-input.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(expr: str):
    code = f"const m = require({json.dumps(str(JS))}); console.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_no_chip_above_100x_the_typed_value_from_1000_up():
    for typed in ("150000", "1000", "1234.5", "1500000000"):
        opts = _run(f"m.chipOptions({json.dumps(typed)})")
        for o in opts:
            assert float(o["plain"]) <= float(typed) * 100, (typed, o)


def test_typed_150000_never_offers_150_million_or_more():
    opts = _run('m.chipOptions("150000")')
    assert all(float(o["plain"]) < 150_000_000 for o in opts)
    assert [o["label"] for o in opts] == ["۱٫۵ میلیون تومان", "۱۵ میلیون تومان"]


def test_amount_in_words_labels():
    assert _run("m.amountInWords(150000)") == "۱۵۰ هزار تومان"
    assert _run("m.amountInWords(1500000)") == "۱٫۵ میلیون تومان"
    assert _run("m.amountInWords(2000000000)") == "۲ میلیارد تومان"
    assert _run("m.amountInWords(950)") == "۹۵۰ تومان"
    assert _run("m.amountInWords(0)") == ""


def test_zero_or_empty_has_no_chips_and_persian_input_parses():
    assert _run('m.chipOptions("")') == []
    assert _run('m.chipOptions("0")') == []
    assert _run('m.plainNumber("۱۵۰٬۰۰۰")') == "150000"


def test_under_1000_offers_exactly_one_thousand_times_chip():
    assert _run('m.chipOptions("150")') == [{"plain": "150000", "label": "۱۵۰ هزار تومان"}]
    assert _run('m.chipOptions("999")') == [{"plain": "999000", "label": "۹۹۹ هزار تومان"}]
    assert _run('m.chipOptions("2.5")') == [{"plain": "2500", "label": "۲٫۵ هزار تومان"}]
    assert len(_run('m.chipOptions("1000")')) == 2 and all(
        float(o["plain"]) <= 100_000 for o in _run('m.chipOptions("1000")'))


def test_words_line_uses_approx_sign_only_when_rounded():
    assert _run("m.amountWordsLine(1234567)") == "≈ ۱٫۲۳ میلیون تومان"
    assert _run("m.amountWordsLine(1234)") == "≈ ۱٫۲۳ هزار تومان"
    assert _run("m.amountWordsLine(150000)") == "= ۱۵۰ هزار تومان"
    assert _run("m.amountWordsLine(1500000)") == "= ۱٫۵ میلیون تومان"
    assert _run("m.amountWordsLine(1230000)") == "= ۱٫۲۳ میلیون تومان"
    assert _run("m.amountWordsLine(950)") == "= ۹۵۰ تومان"
    assert _run("m.amountWordsLine(0)") == ""
