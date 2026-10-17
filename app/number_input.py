"""ONE input parser for numbers typed into forms (mirrored by NumberFa.normalize in static/number-format.js).

Rules (identical in Python and JS, cross-checked by tests/test_number_format.py):
- Persian (۰-۹) and Arabic-Indic (٠-٩) digits become Latin.
- Whitespace and invisible direction marks are removed; "−" (U+2212) is a minus sign.
- Decimal point: "." or "٫" (U+066B). More than one decimal point is rejected.
- Thousands separators: ",", "٬" (U+066C) and "،" (U+060C) are dropped; one after the decimal point
  (e.g. "1.234,5") is ambiguous and rejected.
- Exponents, NaN/Infinity and any other characters are rejected.
"""

from __future__ import annotations

import re
from decimal import Decimal

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_INVISIBLE = re.compile(r"[\s\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_GROUP = re.compile(r"[,٬،]")
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)")
_INTEGER = re.compile(r"[+-]?\d+")


def to_latin_digits(raw: str | None) -> str:
    return str(raw or "").translate(_DIGITS)


def normalize_number_text(raw: str | None) -> str:
    """Canonical Latin form ('' when nothing was typed). Raises ValueError for garbage/ambiguous input."""
    text = _INVISIBLE.sub("", to_latin_digits(raw)).replace("−", "-").replace("٫", ".")
    if text == "":
        return ""
    if text.count(".") > 1:
        raise ValueError("more than one decimal point")
    if "." in text and _GROUP.search(text.split(".", 1)[1]):
        raise ValueError("thousands separator after the decimal point")
    text = _GROUP.sub("", text)
    if not _NUMBER.fullmatch(text):
        raise ValueError("not a number")
    return text


def parse_decimal_text(raw: str | None) -> Decimal | None:
    """Decimal, or None when empty. ValueError when invalid."""
    text = normalize_number_text(raw)
    return None if text == "" else Decimal(text)


def parse_int_text(raw: str | None) -> int | None:
    """Whole number, or None when empty. ValueError when invalid or has a fraction."""
    text = normalize_number_text(raw)
    if text == "":
        return None
    if not _INTEGER.fullmatch(text):
        raise ValueError("not a whole number")
    return int(text)


def parse_int_required(raw: str | None) -> int:
    """Like int(): empty is an error too."""
    value = parse_int_text(raw)
    if value is None:
        raise ValueError("empty")
    return value
