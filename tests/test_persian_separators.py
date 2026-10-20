"""Arabi: thousands must be «٬» (U+066C) and the decimal point «٫» (U+066B), never ASCII «,» / «.» / «/».

The shared display formatters (Python format_number / Jinja |num, JS NumberFa.format) already emit these
code points. In Vazirmatn the U+066C glyph looks almost like a comma and U+066B like a short slash, so
these tests check the characters themselves. Parsing of typed input is unchanged.
"""
import json
import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "number-format.js"
THOUSANDS, DECIMAL = "\u066C", "\u066B"


def test_python_formatter_uses_persian_separators():
    from app.formatting import format_number, format_toman, format_usd
    assert format_number(889088357, 0) == "۸۸۹٬۰۸۸٬۳۵۷"
    assert format_toman(Decimal("889088357")) == "۸۸۹٬۰۸۸٬۳۵۷"
    assert format_number(3383.14) == "۳٬۳۸۳٫۱۴"
    assert format_usd(Decimal("3383.14")) == "۳٬۳۸۳٫۱۴"
    assert format_number(889088357, 0) == f"۸۸۹{THOUSANDS}۰۸۸{THOUSANDS}۳۵۷"
    assert format_number(3383.14) == f"۳{THOUSANDS}۳۸۳{DECIMAL}۱۴"
    for out in (format_number(889088357, 0), format_number(3383.14)):
        assert not set(out) & set(",./"), out


def test_js_formatter_uses_persian_separators():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    code = (f"const m=require({json.dumps(str(JS))});"
            "console.log(JSON.stringify([m.format(889088357,0), m.format(3383.14,2)]));")
    out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert out == ["۸۸۹٬۰۸۸٬۳۵۷", "۳٬۳۸۳٫۱۴"]


def test_typed_input_still_accepts_ascii_commas_and_persian_digits():
    from app.number_input import normalize_number_text
    from app.security import parse_decimal
    for raw in ("889088357", "889,088,357", "۸۸۹٬۰۸۸٬۳۵۷", "۸۸۹,۰۸۸,۳۵۷", "٨٨٩٠٨٨٣٥٧"):
        assert normalize_number_text(raw) == "889088357", raw
        assert parse_decimal(raw, field="x") == Decimal("889088357")
    for raw in ("3383.14", "3,383.14", "۳٬۳۸۳٫۱۴", "۳۳۸۳.۱۴", "۳,۳۸۳٫۱۴"):
        assert normalize_number_text(raw) == "3383.14", raw
    if shutil.which("node") is None:
        return
    code = (f"const m=require({json.dumps(str(JS))});"
            "console.log(JSON.stringify(['889,088,357','۸۸۹٬۰۸۸٬۳۵۷','3,383.14','۳٬۳۸۳٫۱۴'].map(m.normalize)));")
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == ["889088357", "889088357", "3383.14", "3383.14"]


def test_rendered_pages_have_no_ascii_separator_between_persian_digits(client, no_network):
    _register(client)
    client.post("/profile", data={"cash_toman": "889088357", "usd": "3383.14", "next": "/assets",
                                  "csrf": _csrf(client, "/assets")})
    for path in ("/dashboard", "/assets", "/profile?tab=debts", "/dashboard?tab=daily"):
        text = re.sub(r"<[^>]+>", " ", client.get(path).text)
        assert not re.search(r"[۰-۹][,.][۰-۹]", text), (path, re.findall(r"[۰-۹]+[,.][۰-۹]+", text)[:5])
    assert "۸۸۹٬۰۸۸٬۳۵۷" in client.get("/assets").text
