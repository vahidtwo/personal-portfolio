"""Per-field validation for the spend form (mirrored in static/spending-page.js; same normaliser as number_input)."""

from __future__ import annotations

from decimal import Decimal

import jdatetime

from app.formatting import persian_digits
from app.number_input import normalize_number_text

AMOUNT_FORMAT = "مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰"
AMOUNT_POSITIVE = "مبلغ باید بیشتر از صفر باشد"
YEAR_MSG = "سال را چهاررقمی بنویسید"
MONTH_MSG = "ماه بین ۱ تا ۱۲ است"
CATEGORY_MSG = "زیردسته را انتخاب کنید"
FIELD_ORDER = ("amount_toman", "category_id", "year", "month", "day")
FIELD_SHORT = {"amount_toman": "مبلغ", "category_id": "زیردسته", "year": "سال", "month": "ماه", "day": "روز"}


def day_msg(n: int) -> str:
    return f"این ماه {persian_digits(str(n))} روز دارد"


def _int(raw: str) -> int | None:
    try:
        text = normalize_number_text(raw)
    except ValueError:
        return None
    return int(text) if text.isdigit() else None


def month_length(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if jdatetime.date(year, 1, 1).isleap() else 29


def validate_spend(amount: str, year: str, month: str, day: str) -> tuple[dict[str, str], Decimal | None, jdatetime.date | None]:
    """({field: message} for every bad field, amount, date). Empty dict means valid."""
    errors: dict[str, str] = {}
    value: Decimal | None = None
    try:
        text = normalize_number_text(amount)
    except ValueError:
        errors["amount_toman"] = AMOUNT_FORMAT
    else:
        if text.startswith("-") and text.lstrip("-").replace(".", "").strip("0") != "":
            errors["amount_toman"] = AMOUNT_POSITIVE
        elif "." in text:
            errors["amount_toman"] = AMOUNT_FORMAT
        else:
            value = Decimal(text) if text else Decimal("0")
            if value <= 0:
                errors["amount_toman"] = AMOUNT_POSITIVE
                value = None
    y, m, d = _int(year), _int(month), _int(day)
    if y is None or not 1000 <= y <= 9999:
        errors["year"] = YEAR_MSG
    if m is None or not 1 <= m <= 12:
        errors["month"] = MONTH_MSG
    spent = None
    if "year" not in errors and "month" not in errors:
        n = month_length(y, m)
        if d is None or not 1 <= d <= n:
            errors["day"] = day_msg(n)
        else:
            spent = jdatetime.date(y, m, d)
    elif d is None or not 1 <= d <= 31:
        errors["day"] = day_msg(31)
    return errors, value, spent


def summary_fa(count: int) -> str:
    return f"{persian_digits(str(count))} مورد نیاز به اصلاح دارد"
