"""Persian digits, toman amounts, and Jalali dates."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import jdatetime

TEHRAN = ZoneInfo("Asia/Tehran")
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def persian_digits(text: str) -> str:
    return str(text).translate(_PERSIAN_DIGITS)


def format_toman(value: Decimal | None) -> str:
    if value is None:
        return "—"
    quantized = Decimal(value).quantize(Decimal("1"))
    sign = "−" if quantized < 0 else ""
    formatted = f"{abs(int(quantized)):,}".replace(",", "٬")
    return sign + persian_digits(formatted)


def format_qty(value: Decimal, places: int) -> str:
    quantized = Decimal(value).quantize(Decimal("1") if places == 0 else Decimal("0." + "0" * (places - 1) + "1"))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return persian_digits(text or "0")


def format_share_label(share: Decimal) -> str:
    text = format(share, "f").rstrip("0").rstrip(".")
    return persian_digits(text)


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
