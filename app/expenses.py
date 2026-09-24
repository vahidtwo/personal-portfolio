"""Recurring monthly expenses on the profile debts tab."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.debts import debt_rows
from app.formatting import format_jalali_date, format_toman, format_when, next_jalali_due, persian_digits
from app.models import Debt, MonthlyExpense, User
from app.security import get_current_user, parse_decimal, require_csrf
from app.web import flash, render

router = APIRouter()


def _holdings_form(user):
    from app.profile import holdings_form

    return holdings_form(user)


def monthly_view(
    db: Session,
    user: User,
    expense_form: dict | None = None,
    editing_expense_id: int | None = None,
) -> dict:
    """Monthly cash report. Salary comes only from the profile account field."""
    loans = db.query(Debt).filter(Debt.user_id == user.id).all()
    installment = sum((Decimal(row.monthly_toman) for row in loans), Decimal("0"))
    income_total = Decimal(user.salary_toman or 0)
    items = (
        db.query(MonthlyExpense)
        .filter(MonthlyExpense.user_id == user.id)
        .order_by(MonthlyExpense.id.asc())
        .all()
    )
    rows = []
    expense_total = Decimal("0")
    for item in items:
        amount = Decimal(item.amount_toman)
        expense_total += amount
        nxt = next_jalali_due(item.due_day)
        rows.append(
            {
                "id": item.id,
                "title": (item.title or "").strip(),
                "amount_raw": format(amount, "f").rstrip("0").rstrip("."),
                "due_day": str(item.due_day),
                "amount_label": format_toman(amount),
                "day_label": persian_digits(str(item.due_day)),
                "next_label": format_jalali_date(nxt) if nxt else "—",
            }
        )
    outflow = installment + expense_total
    return {
        "expenses": rows,
        "installment_month_label": format_toman(installment),
        "expense_month_label": format_toman(expense_total),
        "income_month_label": format_toman(income_total),
        "monthly_pay_label": format_toman(outflow),
        "monthly_left_label": format_toman(income_total - outflow),
        "expense_form": expense_form or {"title": "", "amount_toman": "", "due_day": ""},
        "editing_expense_id": editing_expense_id,
    }


def expense_form_for_request(db: Session, user: User, request: Request) -> dict:
    view = monthly_view(db, user)
    spend = request.query_params.get("spend", "")
    editing = next((row for row in view["expenses"] if spend.isdigit() and row["id"] == int(spend)), None)
    if editing is not None:
        view["editing_expense_id"] = editing["id"]
        view["expense_form"] = {
            "title": editing["title"],
            "amount_toman": editing["amount_raw"],
            "due_day": editing["due_day"],
        }
    return view
def _parse_due_day(raw: str) -> tuple[int | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    try:
        day = int(text)
    except ValueError:
        return None, "روز ماه باید عدد باشد"
    if day < 1 or day > 31:
        return None, "روز ماه باید بین ۱ و ۳۱ باشد"
    return day, None


def _read_expense_fields(title: str, amount_toman: str, due_day: str):
    form = {"title": title.strip()[:64], "amount_toman": amount_toman, "due_day": due_day}
    try:
        amount = parse_decimal(amount_toman, field="مبلغ ماهانه")
    except Exception as exc:
        return form, None, None, str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
    if amount <= 0:
        return form, None, None, "مبلغ ماهانه باید بیشتر از صفر باشد"
    day, day_error = _parse_due_day(due_day)
    return form, amount, day, day_error


def _render_expense_error(request, db, user, error, form, editing_expense_id):
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
        debt_form={"title": "", "monthly_toman": "", "months_left": "", "due_year": "", "due_month": "", "due_day": ""},
        **monthly_view(db, user, expense_form=form, editing_expense_id=editing_expense_id),
    )


@router.post("/profile/expenses")
async def profile_add_expense(
    request: Request,
    title: str = Form(""),
    amount_toman: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form, amount, day, error = _read_expense_fields(title, amount_toman, due_day)
    if error or amount is None or day is None:
        return _render_expense_error(request, db, user, error or "مقادیر نامعتبر است", form, None)
    db.add(MonthlyExpense(user_id=user.id, title=form["title"], amount_toman=amount, due_day=day))
    db.commit()
    flash(request, "خرج ماهانه ذخیره شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@router.post("/profile/expenses/{expense_id}")
async def profile_update_expense(
    expense_id: int,
    request: Request,
    title: str = Form(""),
    amount_toman: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        flash(request, "خرج ماهانه پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    form, amount, day, error = _read_expense_fields(title, amount_toman, due_day)
    if error or amount is None or day is None:
        return _render_expense_error(request, db, user, error or "مقادیر نامعتبر است", form, expense_id)
    item.title = form["title"]
    item.amount_toman = amount
    item.due_day = day
    db.commit()
    flash(request, "خرج ماهانه به‌روز شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@router.post("/profile/expenses/{expense_id}/delete")
async def profile_delete_expense(
    expense_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        flash(request, "خرج ماهانه پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    db.delete(item)
    db.commit()
    flash(request, "خرج ماهانه حذف شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)
