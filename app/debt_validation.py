"""Per-field validation for the debt and monthly-expense forms (mirrored in static/debts-page.js).

Same normaliser as number_input. Amounts are whole toman for NEW input; an edit may keep a legacy
fractional amount unchanged (`existing`), so old rows never get stuck.
"""

from __future__ import annotations

from decimal import Decimal

from app.debt_schedule import month_length
from app.formatting import persian_digits
from app.number_input import normalize_number_text

AMOUNT_FORMAT = "مبلغ را بدون ممیز بنویسید؛ مثلاً ۲٬۵۰۰٬۰۰۰"
AMOUNT_POSITIVE = "مبلغ باید بیشتر از صفر باشد"
MONTHS_MSG = "دست‌کم ۱ قسط باید مانده باشد"
YEAR_MSG = "سال را چهاررقمی بنویسید"
MONTH_MSG = "ماه بین ۱ تا ۱۲ است"
EXP_DAY_MSG = "روز بین ۱ تا ۳۱ است"
DEBT_FIELDS = ("monthly_toman", "months_left", "due_year", "due_month", "due_day")
EXPENSE_FIELDS = ("amount_toman", "due_day")
FIELD_SHORT = {"monthly_toman": "مبلغ هر قسط", "months_left": "تعداد قسط مانده", "due_year": "سال", "due_month": "ماه",
               "due_day": "روز", "amount_toman": "مبلغ"}


def day_msg(n: int) -> str:
    return f"این ماه {persian_digits(str(n))} روز دارد"


def summary_fa(count: int) -> str:
    return f"{persian_digits(str(count))} مورد نیاز به اصلاح دارد"


def _int(raw: str) -> int | None:
    try:
        text = normalize_number_text(raw)
    except ValueError:
        return None
    return int(text) if text.isdigit() else None


def amount_error(raw: str, existing: Decimal | None = None) -> tuple[str | None, Decimal | None]:
    try:
        text = normalize_number_text(raw)
    except ValueError:
        return AMOUNT_FORMAT, None
    if text.startswith("-") and text.lstrip("-").replace(".", "").strip("0") != "":
        return AMOUNT_POSITIVE, None
    if "." in text and not (existing is not None and Decimal(text) == Decimal(existing)):
        return AMOUNT_FORMAT, None
    value = Decimal(text) if text else Decimal("0")
    if value <= 0:
        return AMOUNT_POSITIVE, None
    return None, value


def validate_debt(monthly: str, months: str, year: str, month: str, day: str, existing: Decimal | None = None):
    """({field: message}, values dict). Every bad field at once; empty dict means valid."""
    errors: dict[str, str] = {}
    err, amount = amount_error(monthly, existing)
    if err:
        errors["monthly_toman"] = err
    n = _int(months)
    if n is None or n < 1:
        errors["months_left"] = MONTHS_MSG
    y, m, d = _int(year), _int(month), _int(day)
    if y is None or not 1000 <= y <= 9999:
        errors["due_year"] = YEAR_MSG
    if m is None or not 1 <= m <= 12:
        errors["due_month"] = MONTH_MSG
    if "due_year" not in errors and "due_month" not in errors:
        length = month_length(y, m)
        if d is None or not 1 <= d <= length:
            errors["due_day"] = day_msg(length)
    elif d is None or not 1 <= d <= 31:
        errors["due_day"] = day_msg(31)
    ordered = {f: errors[f] for f in DEBT_FIELDS if f in errors}
    return ordered, {"monthly": amount, "months": n, "year": y, "month": m, "day": d}


def validate_expense(amount_raw: str, day_raw: str, existing: Decimal | None = None):
    errors: dict[str, str] = {}
    err, amount = amount_error(amount_raw, existing)
    if err:
        errors["amount_toman"] = err
    d = _int(day_raw)
    if d is None or not 1 <= d <= 31:
        errors["due_day"] = EXP_DAY_MSG
    return errors, {"amount": amount, "day": d}
