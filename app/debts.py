"""Installment debts on the profile debts tab."""

from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_jalali_date, format_toman, format_when, next_jalali_due, parse_jalali_parts, persian_digits
from app.models import Debt, User
from app.security import get_current_user, parse_decimal, require_csrf
from app.web import flash, render

router = APIRouter()


def _holdings_form(user):
    from app.profile import holdings_form

    return holdings_form(user)


def _monthly_view(db, user, **kwargs):
    from app.expenses import monthly_view

    return monthly_view(db, user, **kwargs)


def debt_rows(debts: list[Debt]) -> tuple[list[dict], Decimal, str]:
    rows = []
    total = Decimal("0")
    soonest: jdatetime.date | None = None
    for debt in debts:
        amount = Decimal(debt.monthly_toman) * Decimal(debt.months_left)
        total += amount
        nxt = next_jalali_due(debt.due_day)
        if nxt is not None and (soonest is None or nxt < soonest):
            soonest = nxt
        rows.append(
            {
                "id": debt.id,
                "title": (debt.title or "").strip(),
                "monthly_raw": format(Decimal(debt.monthly_toman), "f").rstrip("0").rstrip("."),
                "months_raw": str(debt.months_left),
                "due_year": str(debt.due_year),
                "due_month": str(debt.due_month),
                "due_day": str(debt.due_day),
                "monthly_label": format_toman(debt.monthly_toman),
                "months_label": persian_digits(str(debt.months_left)),
                "entered_label": format_jalali_date(
                    jdatetime.date(debt.due_year, debt.due_month, debt.due_day)
                ),
                "total_label": format_toman(amount),
                "next_label": format_jalali_date(nxt) if nxt else "—",
            }
        )
    return rows, total, format_jalali_date(soonest) if soonest else "—"
def _parse_months_left(raw: str) -> tuple[int | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    try:
        value = int(text)
    except ValueError:
        return None, "تعداد ماه مانده باید عدد باشد"
    if value < 1:
        return None, "تعداد ماه مانده باید حداقل ۱ باشد"
    return value, None


def parse_jalali_parts(year: str, month: str, day: str) -> tuple[jdatetime.date | None, str | None]:
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    try:
        parsed = jdatetime.date(int(year.strip().translate(trans)), int(month.strip().translate(trans)), int(day.strip().translate(trans)))
    except (TypeError, ValueError):
        return None, "تاریخ جلالی نامعتبر است"
    return parsed, None


@router.post("/profile/debts")
async def profile_add_debt(
    request: Request,
    title: str = Form(""),
    monthly_toman: str = Form(""),
    months_left: str = Form(""),
    due_year: str = Form(""),
    due_month: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = {
        "title": title.strip()[:64],
        "monthly_toman": monthly_toman,
        "months_left": months_left,
        "due_year": due_year,
        "due_month": due_month,
        "due_day": due_day,
    }
    try:
        monthly = parse_decimal(monthly_toman, field="مبلغ ماهانه")
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
        monthly = None
    else:
        error = "مبلغ ماهانه باید بیشتر از صفر باشد" if monthly <= 0 else None
    months, months_error = _parse_months_left(months_left)
    due, due_error = parse_jalali_parts(due_year, due_month, due_day)
    error = error or months_error or due_error
    if error or monthly is None or months is None or due is None:
        debts, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
    )
        return render(
            request,
            "profile.html",
            db,
            error=error,
            flash=None,
            form=_holdings_form(user),
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            tab="debts",
            debts=debts,
            debt_total_label=format_toman(debt_total),
            next_debt_label=next_debt_label,
            editing_id=None,
            debt_form=form,
            **_monthly_view(db, user),
        )
    db.add(
        Debt(
            user_id=user.id,
            title=form["title"],
            monthly_toman=monthly,
            months_left=months,
            due_year=due.year,
            due_month=due.month,
            due_day=due.day,
        )
    )
    db.commit()
    flash(request, "بدهی ذخیره شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@router.post("/profile/debts/{debt_id}")
async def profile_update_debt(
    debt_id: int,
    request: Request,
    title: str = Form(""),
    monthly_toman: str = Form(""),
    months_left: str = Form(""),
    due_year: str = Form(""),
    due_month: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    debt = db.get(Debt, debt_id)
    if debt is None or debt.user_id != user.id:
        flash(request, "بدهی پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    form = {
        "title": title.strip()[:64],
        "monthly_toman": monthly_toman,
        "months_left": months_left,
        "due_year": due_year,
        "due_month": due_month,
        "due_day": due_day,
    }
    try:
        monthly = parse_decimal(monthly_toman, field="مبلغ ماهانه")
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
        monthly = None
    else:
        error = "مبلغ ماهانه باید بیشتر از صفر باشد" if monthly <= 0 else None
    months, months_error = _parse_months_left(months_left)
    due, due_error = parse_jalali_parts(due_year, due_month, due_day)
    error = error or months_error or due_error
    if error or monthly is None or months is None or due is None:
        debts, debt_total, next_debt_label = debt_rows(
            db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
        )
        return render(
            request,
            "profile.html",
            db,
            error=error,
            flash=None,
            form=_holdings_form(user),
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            tab="debts",
            debts=debts,
            debt_total_label=format_toman(debt_total),
            next_debt_label=next_debt_label,
            editing_id=debt_id,
            debt_form=form,
            **_monthly_view(db, user),
        )
    debt.title = form["title"]
    debt.monthly_toman = monthly
    debt.months_left = months
    debt.due_year = due.year
    debt.due_month = due.month
    debt.due_day = due.day
    db.commit()
    flash(request, "بدهی به‌روز شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@router.post("/profile/debts/{debt_id}/delete")
async def profile_delete_debt(
    debt_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    debt = db.get(Debt, debt_id)
    if debt is None or debt.user_id != user.id:
        flash(request, "بدهی پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    db.delete(debt)
    db.commit()
    flash(request, "بدهی حذف شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)
