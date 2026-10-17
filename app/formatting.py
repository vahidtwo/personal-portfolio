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


def format_number(value, max_decimals: int = MONEY_DECIMALS, min_decimals: int = 0) -> str:
    """THE display formatter (mirrored by app/static/number-format.js).

    Persian digits, ٬ thousands, ٫ decimals, round half-up to max_decimals, no trailing
    zeros beyond min_decimals, "−" for negatives. Display only: never use for <input>
    values, JSON or APIs.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        d = Decimal(repr(value))
    elif isinstance(value, str):
        from app.number_input import normalize_number_text

        text = normalize_number_text(value)
        if text == "":
            return ""
        d = Decimal(text)
    else:
        d = Decimal(value)
    q = d.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_UP)
    negative = q < 0
    q = abs(q)
    whole, _, frac = format(q, "f").partition(".")
    frac = frac.rstrip("0")
    if len(frac) < min_decimals:
        frac = frac.ljust(min_decimals, "0")
    out = f"{int(whole):,}".replace(",", "٬") + (f"٫{frac}" if frac else "")
    if negative and q != 0:
        out = "−" + out
    return persian_digits(out)


def format_toman(value: Decimal | None) -> str:
    """Toman amount for display (whole toman; «تومان» is written after it in templates)."""
    if value is None:
        return "—"
    return format_number(value, 0)


def format_usd(value: Decimal | None, *, fixed: bool = False) -> str:
    """Dollar amount. fixed=True always shows exactly 2 decimals (dashboard: 9٬102٫30)."""
    if value is None:
        return "—"
    return format_number(value, MONEY_DECIMALS, MONEY_DECIMALS if fixed else 0)


MILLION = Decimal("1000000")


def format_millions(value: Decimal | None, decimals: int = 1) -> tuple[str, bool]:
    """Toman amount in millions for big-number tiles («۱٬۱۱۳» + «میلیون تومان»).

    Returns (label, approx); approx is True when rounding dropped digits, so the template
    can prefix «≈». The exact amount stays available via format_toman.
    """
    if value is None:
        return "—", False
    millions = Decimal(value) / MILLION
    label = format_number(millions, decimals)
    exact = millions == millions.quantize(Decimal(1).scaleb(-decimals))
    return label, not exact


def format_qty(value: Decimal, places: int) -> str:
    """Asset quantity for display (max 8 decimals)."""
    return format_number(Decimal(value or 0), min(places, QTY_DECIMALS)) or "۰"


def _input_text(value) -> str:
    """Exact stored value as plain Latin text ('' for zero): never rounded, no trailing zeros."""
    d = Decimal(value or 0)
    if d == 0:
        return ""
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_qty_input(value: Decimal, places: int | None = None) -> str:
    """Quantity <input> value: full stored precision (no rounding), Persian digits, ٫ decimal,
    no grouping; '' when zero. app.number_input parses it back exactly. `places` is ignored."""
    return persian_digits(_input_text(value).replace(".", "٫"))


def format_amount_input(value: Decimal) -> str:
    """Toman <input> value: like format_qty_input but with ٬ thousands grouping."""
    text = _input_text(value)
    if text == "":
        return ""
    negative = text.startswith("-")
    whole, _, frac = text.lstrip("-").partition(".")
    out = f"{int(whole):,}".replace(",", "٬") + (f"٫{frac}" if frac else "")
    return persian_digits(("-" if negative else "") + out)


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tehran_today() -> jdatetime.date:
    """Today's Jalali date in Tehran, whatever the server's own timezone (prod runs in UTC).

    THE "today" for due dates, monthly costs and daily spends, so every page agrees.
    """
    return jdatetime.date.fromgregorian(date=_utcnow().astimezone(TEHRAN).date())


def next_jalali_due(day: int, today: jdatetime.date | None = None) -> jdatetime.date | None:
    """First Jalali date on or after today (Tehran) whose day-of-month is `day`."""
    today = today or tehran_today()
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
        from app.number_input import parse_int_required

        parsed = jdatetime.date(parse_int_required(year), parse_int_required(month), parse_int_required(day))
    except (TypeError, ValueError):
        return None, "تاریخ جلالی نامعتبر است"
    return parsed, None
