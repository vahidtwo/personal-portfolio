"""Push reminders before an instalment is due, plus one notice when it becomes overdue.

Runs from the hourly job (only while ENABLE_INTERNAL_SCHEDULER is on). Sent through Firebase to the user's
registered devices (Android app / web push). Upcoming and overdue notices go out only in the evening, Asia/Tehran:
the run in the 20:00 hour sends them and the run in the 21:00 hour catches up on anything still unsent that day
(window 20:00-21:59). Runs at any other hour send nothing, so with the default of 1 day the reminder arrives at
about 20:00 the evening before the due date. Each (loan, due date, kind) is sent at most once: a row in
due_reminders records it, so restarts and hourly runs never repeat it. Paying an instalment moves the due
date, so the next instalment gets its own reminder. Finished loans (no instalments left) are skipped.
Each loan picks how early its upcoming reminder goes out (debts.reminder_days_before): NULL = the default
(DUE_REMINDER_DAYS, else 1 day), 0 = on the due day, -1 = off (the overdue notice still goes out).
A loan added or changed inside its window still gets that one reminder at the next evening window.
Push text never contains amounts (masking); dates are Jalali.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import jdatetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import debt_schedule as ds
from app.formatting import TEHRAN, format_jalali_date, persian_digits
from app.models import Debt, DueReminder

logger = logging.getLogger(__name__)

DEFAULT_DAYS_BEFORE = 1
KIND_UPCOMING = "upcoming"
KIND_OVERDUE = "overdue"
# Tehran hours whose hourly run may send: 20 is the send hour, 21 the same-day catch-up.
SEND_FROM_HOUR, SEND_UNTIL_HOUR = 20, 22


def in_send_window(now: datetime) -> bool:
    """True when `now` (any timezone; naive means UTC) falls in 20:00-21:59 Asia/Tehran."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return SEND_FROM_HOUR <= now.astimezone(TEHRAN).hour < SEND_UNTIL_HOUR


def days_before() -> int:
    try:
        return max(0, int(os.environ.get("DUE_REMINDER_DAYS", DEFAULT_DAYS_BEFORE)))
    except ValueError:
        return DEFAULT_DAYS_BEFORE


def loan_days_before(debt: Debt, default: int) -> int | None:
    """Days before the due date this loan's upcoming reminder starts; None when it is off."""
    value = getattr(debt, "reminder_days_before", None)
    if value is None:
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return None
    return value


def _title(debt: Debt) -> str:
    return (debt.title or "").strip() or "قسط"


def upcoming_text(debt: Debt, due: jdatetime.date, days: int) -> tuple[str, str]:
    when = "امروز" if days == 0 else ("فردا" if days == 1 else f"{persian_digits(str(days))} روز دیگر")
    return "یادآوری قسط", f"قسط «{_title(debt)}» {when}، {format_jalali_date(due)} سررسید می‌شود."


def overdue_text(debt: Debt, due: jdatetime.date) -> tuple[str, str]:
    return "قسط عقب افتاد", f"قسط «{_title(debt)}» از {format_jalali_date(due)} پرداخت نشده است."


def pending(debts, today: jdatetime.date, n_days: int):
    """(debt, kind, due) that should be notified today, before checking what was already sent.

    `n_days` is the default for loans without their own setting.
    """
    out = []
    for debt in debts:
        if not ds.is_active(debt):  # finished («تسویه شد») or paid off
            continue
        due = ds.next_due(debt, today)
        if due is None:
            continue
        days = (due.togregorian() - today.togregorian()).days
        if days < 0:
            out.append((debt, KIND_OVERDUE, due, days))
        else:
            window = loan_days_before(debt, n_days)
            if window is not None and days <= window:
                out.append((debt, KIND_UPCOMING, due, days))
    return out


def send_due_reminders(db: Session, *, now: datetime | None = None, push=None) -> int:
    """Send what is due now; returns how many notices were sent. `push` defaults to send_push_to_user."""
    if push is None:
        from app.firebase_push import firebase_admin_ready, send_push_to_user

        if not firebase_admin_ready():
            return 0
        push = send_push_to_user
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if not in_send_window(now):
        return 0
    local = now.astimezone(TEHRAN)
    today = jdatetime.date.fromgregorian(date=local.date())
    sent_keys = {(r.debt_id, r.kind, r.due_date) for r in db.query(DueReminder).all()}
    count = 0
    for debt, kind, due, days in pending(db.query(Debt).all(), today, days_before()):
        key = (debt.id, kind, due.strftime("%Y-%m-%d"))
        if key in sent_keys:
            continue
        title, body = upcoming_text(debt, due, days) if kind == KIND_UPCOMING else overdue_text(debt, due)
        try:
            delivered = push(db, debt.user_id, title=title, body=body,
                             data={"type": f"debt_{kind}", "url": "/dashboard?tab=debts"})
        except Exception:
            logger.exception("Due reminder push failed for debt %s", debt.id)
            continue
        if not delivered:
            continue  # no device or not delivered: try again next hour
        db.add(DueReminder(user_id=debt.user_id, debt_id=debt.id, kind=kind, due_date=key[2]))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        sent_keys.add(key)
        count += 1
    return count
