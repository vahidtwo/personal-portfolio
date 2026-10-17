"""Persian digits, toman amounts, and Jalali dates."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import jdatetime

TEHRAN = ZoneInfo("Asia/Tehran")
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def persian_digits(text: str) -> str:
    return str(text).translate(_PERSIAN_DIGITS)


MONEY_DECIMALS = 2
QTY_DECIMALS = 8


def format_number(value, max_decimals: int = MONEY_DECIMALS) -> str:
    """THE display formatter (mirrored by app/static/number-format.js).

    Persian digits, ٬ thousands, ٫ decimals, round half-up to max_decimals, no trailing
    zeros, "−" for negatives. Display only: never use for <input> values, JSON or APIs.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        d = Decimal(repr(value))
    else:
        text = str(value).strip().translate(_TO_ASCII).replace(",", "").replace("٬", "")
        d = Decimal(text.replace("٫", ".").replace("−", "-"))
    q = d.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_UP)
    negative = q < 0
    q = abs(q)
    whole, _, frac = format(q, "f").partition(".")
    frac = frac.rstrip("0")
    out = f"{int(whole):,}".replace(",", "٬") + (f"٫{frac}" if frac else "")
    if negative and q != 0:
        out = "−" + out
    return persian_digits(out)


def format_toman(value: Decimal | None) -> str:
    """Toman amount for display (whole toman; «تومان» is written after it in templates)."""
    if value is None:
        return "—"
    return format_number(value, 0)


def format_usd(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return format_number(value, MONEY_DECIMALS)


def format_qty(value: Decimal, places: int) -> str:
    """Asset quantity for display (max 8 decimals)."""
    return format_number(Decimal(value or 0), min(places, QTY_DECIMALS)) or "۰"


def format_qty_input(value: Decimal, places: int) -> str:
    """Value for an <input>: Persian digits, '.' decimal, no grouping; empty when zero.

    The server parser (security.parse_decimal) maps '' to 0 and accepts Persian/Latin digits.
    """
    d = Decimal(value or 0).quantize(Decimal(1).scaleb(-min(places, QTY_DECIMALS)), rounding=ROUND_HALF_UP)
    if d == 0:
        return ""
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return persian_digits(text)


def format_share_label(share: Decimal) -> str:
    return format_number(share, MONEY_DECIMALS)


def _to_tehran(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def format_chart_jalali(value: datetime) -> str:
    """Jalali date-time (Tehran) with Persian digits."""
    local = _to_tehran(value)
    j = jdatetime.datetime.fromgregorian(
        year=local.year,
        month=local.month,
        day=local.day,
        hour=local.hour,
        minute=local.minute,
    )
    return persian_digits(j.strftime("%Y/%m/%d %H:%M"))


def format_when(value: datetime | None) -> str:
    if value is None:
        return "—"
    return format_chart_jalali(value)


def next_jalali_due(day: int, today: jdatetime.date | None = None) -> jdatetime.date | None:
    """First Jalali date on or after today whose day-of-month is `day`."""
    today = today or jdatetime.date.today()
    year, month = today.year, today.month
    for _ in range(26):
        try:
            candidate = jdatetime.date(year, month, day)
        except ValueError:
            candidate = None
        if candidate is not None and candidate >= today:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return None


def format_jalali_date(value: jdatetime.date) -> str:
    return persian_digits(f"{value.year}/{value.month:02d}/{value.day:02d}")


def parse_jalali_parts(year: str, month: str, day: str) -> tuple[jdatetime.date | None, str | None]:
    try:
        parsed = jdatetime.date(
            int(year.strip().translate(_TO_ASCII)),
            int(month.strip().translate(_TO_ASCII)),
            int(day.strip().translate(_TO_ASCII)),
        )
    except (TypeError, ValueError):
        return None, "تاریخ جلالی نامعتبر است"
    return parsed, None
