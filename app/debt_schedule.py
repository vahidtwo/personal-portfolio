"""Debts v2 schedule rules: next due, end month, badges, sorting and totals (no schema change).

Manual-only countdown: `months_left` is the stored source of truth. It changes only through
«پرداخت شد» (and its undo) or an edit; nothing here derives it from the calendar.
A debt with months_left == 0 is "done": it stays listed (last) but is out of every total.

Stored date: (due_year, due_month) is the OLDEST unpaid instalment month, due_day the instalment day.
A stored date before today is overdue and stays put until «پرداخت شد»; nothing rolls it forward.
«پرداخت شد» moves the stored month on by exactly one and keeps due_day, so a day-31 loan stays day 31; a stored
triple like 1405/08/31 is therefore allowed and every reader goes through `clamp`.
"""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal

import jdatetime

from app.daily_spend import JALALI_MONTHS
from app.formatting import TEHRAN, format_toman, persian_digits, tehran_today


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
    """Oldest unpaid instalment date (the stored month, clamped). It may be in the past: that is overdue.

    Only a row whose stored date cannot be read falls back to the next occurrence of due_day.
    """
    if not is_active(debt):
        return None
    try:
        return clamp(debt.due_year, debt.due_month, debt.due_day)
    except (TypeError, ValueError):
        pass
    today = today or tehran_today()
    year, month = today.year, today.month
    candidate = clamp(year, month, debt.due_day)
    if candidate < today:
        year, month = add_months(year, month, 1)
        candidate = clamp(year, month, debt.due_day)
    return candidate


def overdue_days(debt, today: jdatetime.date | None = None) -> int:
    """Days since the oldest unpaid instalment was due; 0 when it is today or ahead."""
    nxt = next_due(debt, today)
    if nxt is None:
        return 0
    today = today or tehran_today()
    return max(0, (today.togregorian() - nxt.togregorian()).days)


def missed_count(debt, today: jdatetime.date | None = None) -> int:
    """Unpaid instalments whose date has passed (capped at months_left)."""
    nxt = next_due(debt, today)
    if nxt is None:
        return 0
    today = today or tehran_today()
    count = 0
    y, m = nxt.year, nxt.month
    while count < int(debt.months_left) and clamp(y, m, debt.due_day) < today:
        count += 1
        y, m = add_months(y, m, 1)
    return count


def after_payment(debt, today: jdatetime.date | None = None) -> tuple[int, int]:
    """(year, month) of the next unpaid instalment once the oldest one is paid: exactly one month on."""
    nxt = next_due(debt, today)
    return add_months(nxt.year, nxt.month, 1)


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
    if days < 0:
        return f"{persian_digits(str(-days))} روز گذشته"
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


def month_due(debts, today: jdatetime.date | None = None) -> tuple[Decimal, Decimal]:
    """(due by the end of today's Jalali month, overdue part of it).

    Every unpaid instalment dated in the current Jalali month or earlier counts once; the overdue part
    is the ones dated before today. Instalments after this month are not included.
    """
    today = today or tehran_today()
    total = overdue = Decimal("0")
    for debt in debts:
        nxt = next_due(debt, today)
        if nxt is None:
            continue
        amount = Decimal(debt.monthly_toman)
        y, m = nxt.year, nxt.month
        for _ in range(int(debt.months_left)):
            if (y, m) > (today.year, today.month):
                break
            total += amount
            if clamp(y, m, debt.due_day) < today:
                overdue += amount
            y, m = add_months(y, m, 1)
    return total, overdue


def _entered_on(debt) -> jdatetime.date | None:
    created = getattr(debt, "created_at", None)
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return jdatetime.date.fromgregorian(date=created.astimezone(TEHRAN).date())


def this_month_installments(debts, today: jdatetime.date | None = None) -> Decimal:
    """Instalments dated in today's Jalali month for active loans, paid or not; older overdue months are left out.

    An unpaid one is the stored month itself. A paid one shows as a stored month exactly one month ahead,
    unless the loan was entered after this month's due date (its first instalment is then next month).
    """
    today = today or tehran_today()
    following = add_months(today.year, today.month, 1)
    total = Decimal("0")
    for debt in debts:
        nxt = next_due(debt, today)
        if nxt is None:
            continue
        stored = (nxt.year, nxt.month)
        if stored <= (today.year, today.month):
            due_now = int(debt.months_left) > _months_between(stored, today)
        elif stored == following:
            entered = _entered_on(debt)
            due_now = entered is None or entered <= clamp(today.year, today.month, debt.due_day)
        else:
            due_now = False
        if due_now:
            total += Decimal(debt.monthly_toman)
    return total


def _months_between(start: tuple[int, int], today: jdatetime.date) -> int:
    return (today.year * 12 + today.month) - (start[0] * 12 + start[1])


def salary_left(salary, debts, fixed_monthly, today: jdatetime.date | None = None) -> Decimal:
    """«مانده از حقوق»: salary − this month's instalments of active loans − fixed monthly costs."""
    return Decimal(salary or 0) - this_month_installments(debts, today) - Decimal(fixed_monthly or 0)


def overdue_count(debts, today: jdatetime.date | None = None) -> int:
    """Active debts whose oldest unpaid instalment is before today."""
    today = today or tehran_today()
    return sum(1 for d in debts if (n := next_due(d, today)) is not None and n < today)


def overdue_loans_label(count: int) -> str | None:
    return f"{persian_digits(str(count))} وام عقب‌افتاده" if count > 0 else None


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
    late = overdue_count(debts, today)
    return {"date": best, "days": days, "chip": days_chip(days), "amount": amount, "amount_label": format_toman(amount),
            "title": title, "date_label": day_month(best), "overdue_count": late, "overdue_label": overdue_loans_label(late)}
