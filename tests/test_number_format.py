"""One display formatter in Python (format_number) and its JS twin (number-format.js) must agree."""
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "app" / "static" / "number-format.js"

SAMPLES = [
    (0, 2), (1, 2), (12.5, 2), (1234567.891, 2), ("18500000", 0), (3249.455, 2), (3249.45, 2),
    (0.00000001, 8), ("0.123456789", 8), (-1234.5, 2), (999.995, 2), (1e15, 0), ("۱۲٬۳۴۵٫۶", 2),
    (150000, 0), (1500000.0, 2), (2.0, 2), ("-0.001", 2), (99.999, 1), (7200000000, 0), ("0.5", 0),
]


def test_python_and_js_formatters_match():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    from app.formatting import format_number
    py = [format_number(v, d) for v, d in SAMPLES]
    code = (f"const m=require({json.dumps(str(JS))});const s={json.dumps(SAMPLES)};"
            "console.log(JSON.stringify(s.map(([v,d])=>m.format(v,d))));")
    js = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert js == py, list(zip(SAMPLES, py, js))


def test_display_rules():
    from app.formatting import format_number, format_qty, format_toman, format_usd
    assert format_usd(Decimal("3249.45")) == "۳٬۲۴۹٫۴۵"
    assert format_usd(Decimal("3249.40")) == "۳٬۲۴۹٫۴"
    assert format_qty(Decimal("12.5000"), 4) == "۱۲٫۵"
    assert format_qty(Decimal("18500000"), 0) == "۱۸٬۵۰۰٬۰۰۰"
    assert format_qty(Decimal("0.123456789"), 10) == "۰٫۱۲۳۴۵۶۷۹"  # max 8 decimals
    assert format_qty(Decimal("0"), 4) == "۰"
    assert format_toman(Decimal("1234567.6")) == "۱٬۲۳۴٬۵۶۸"
    assert format_toman(None) == "—"
    assert format_number(Decimal("-12.5")) == "−۱۲٫۵"
    assert "." not in format_number(1234.56) and "," not in format_number(1234567)


def test_growth_and_share_labels_use_persian_decimal():
    from app.dashboard import format_percent_label
    from app.formatting import format_share_label
    assert format_percent_label(12.345) == "+۱۲٫۳۵٪"
    assert format_percent_label(-0.5) == "−۰٫۵٪"
    assert format_percent_label(150.0) == "+۱۵۰٪"
    assert format_share_label(Decimal("33.3")) == "۳۳٫۳"


def test_input_values_stay_parseable():
    """Inputs never get ٫/٬ from the server: Persian digits, '.' decimal, '' for zero."""
    from app.formatting import format_qty_input
    from app.security import parse_decimal
    assert format_qty_input(Decimal("0"), 4) == ""
    assert format_qty_input(Decimal("12.5"), 4) == "۱۲.۵"
    for v in ("۱۲.۵", "12.5", "", "۱۸٬۵۰۰٬۰۰۰"):
        parse_decimal(v, field="x")
    assert parse_decimal("", field="x") == 0
