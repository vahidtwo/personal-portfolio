"""Debts v2 schedule rules: next due, end month, badges, sorting and totals (no schema change).

Manual-only countdown: `months_left` is the stored source of truth. It changes only through
«پرداخت شد» (and its undo) or an edit; nothing here derives it from the calendar.
A debt with months_left == 0 is "done": it stays listed (last) but is out of every total.

Stored date: (due_year, due_month) is the next instalment month, due_day the instalment day.
«پرداخت شد» moves the month on and keeps due_day, so a day-31 loan stays day 31; a stored
triple like 1405/08/31 is therefore allowed and every reader goes through `clamp`.
"""

from __future__ import annotations

from decimal import Decimal

import jdatetime

from app.daily_spend import JALALI_MONTHS
from app.formatting import format_toman, persian_digits, tehran_today


def month_length(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if jdatetime.date(year, 1, 1).isleap() else 29


def clamp(year: int, month: int, day: int) -> jdatetime.date:
    """Jalali date; a day past the month's end becomes its last day."""
    return jdatetime.date(year, month, max(1, min(int(day), month_length(year, month))))


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + n
    return index // 12, index % 12 + 1


def is_active(debt) -> bool:
    return int(debt.months_left or 0) > 0


def next_due(debt, today: jdatetime.date | None = None) -> jdatetime.date | None:
    """Next instalment date: the stored month if still ahead, otherwise the next occurrence of due_day.

    The second branch keeps legacy rows (whose stored date is in the past) behaving as before;
    it only moves the date shown, never the count.
    """
    if not is_active(debt):
        return None
    today = today or tehran_today()
    try:
        stored = clamp(debt.due_year, debt.due_month, debt.due_day)
    except (TypeError, ValueError):
        stored = None
    if stored is not None and stored >= today:
        return stored
    year, month = today.year, today.month
    candidate = clamp(year, month, debt.due_day)
    if candidate < today:
        year, month = add_months(year, month, 1)
        candidate = clamp(year, month, debt.due_day)
    return candidate


def end_due(debt, today: jdatetime.date | None = None) -> jdatetime.date | None:
    nxt = next_due(debt, today)
    if nxt is None:
        return None
    y, m = add_months(nxt.year, nxt.month, int(debt.months_left) - 1)
    return clamp(y, m, debt.due_day)


def day_month(value: jdatetime.date) -> str:
    return persian_digits(f"{value.day} {JALALI_MONTHS[value.month - 1]}")


def day_month_year(value: jdatetime.date) -> str:
    return persian_digits(f"{value.day} {JALALI_MONTHS[value.month - 1]} {value.year}")


def month_year(value: jdatetime.date) -> str:
    return persian_digits(f"{JALALI_MONTHS[value.month - 1]} {value.year}")


def days_chip(days: int) -> str:
    if days == 0:
        return "امروز"
    if days == 1:
        return "فردا"
    return f"{persian_digits(str(days))} روز دیگر"


def remaining(debt) -> Decimal:
    return Decimal(debt.monthly_toman) * Decimal(max(int(debt.months_left or 0), 0))


def active_total(debts) -> Decimal:
    return sum((remaining(d) for d in debts if is_active(d)), Decimal("0"))


def active_installment(debts) -> Decimal:
    return sum((Decimal(d.monthly_toman) for d in debts if is_active(d)), Decimal("0"))


def badge(months_left: int) -> tuple[str | None, str | None]:
    if months_left == 1:
        return "end", "آخرین قسط"
    if 2 <= months_left <= 3:
        return "soon", f"{persian_digits(str(months_left))} قسط مانده"
    return None, None


def sort_key(debt, today):
    nxt = next_due(debt, today)
    if nxt is None:
        return (1, 0, debt.id)
    return (0, (nxt.togregorian() - today.togregorian()).days, debt.id)


def soonest(debts, today: jdatetime.date | None = None) -> dict | None:
    """The next instalment over all active debts; debts due the same day are added together."""
    today = today or tehran_today()
    best, group = None, []
    for debt in debts:
        nxt = next_due(debt, today)
        if nxt is None:
            continue
        if best is None or nxt < best:
            best, group = nxt, [debt]
        elif nxt == best:
            group.append(debt)
    if best is None:
        return None
    days = (best.togregorian() - today.togregorian()).days
    amount = sum((Decimal(d.monthly_toman) for d in group), Decimal("0"))
    title = f"{persian_digits(str(len(group)))} قسط" if len(group) > 1 else ((group[0].title or "").strip() or "قسط")
    return {"date": best, "days": days, "chip": days_chip(days), "amount": amount, "amount_label": format_toman(amount),
            "title": title, "date_label": day_month(best)}
