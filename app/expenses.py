"""Recurring monthly expenses on the profile debts tab."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_amount_input, format_jalali_date, format_toman, format_when, next_jalali_due, persian_digits
from app.models import Debt, MonthlyExpense, User
from app.number_input import parse_int_required
from app.security import get_authenticated_user, parse_decimal, redirect_to_login, require_csrf
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
    from app.debt_schedule import active_installment

    # Debts with 0 instalments left are paid off: out of «اقساط این ماه» (and so of مانده / /api/salary).
    installment = active_installment(db.query(Debt).filter(Debt.user_id == user.id).all())
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
                "amount_raw": format_amount_input(amount),
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
def _expense_form(title: str, amount_toman: str, due_day: str) -> dict:
    return {"title": title.strip()[:64], "amount_toman": amount_toman, "due_day": due_day}


@router.post("/profile/expenses")
async def profile_add_expense(
    request: Request,
    title: str = Form(""),
    amount_toman: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.debts import invalid_response, saved_response
    from app.debt_validation import validate_expense

    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    form = _expense_form(title, amount_toman, due_day)
    errors, v = validate_expense(amount_toman, due_day)
    if errors:
        return invalid_response(request, db, user, errors, expense_form=form, expense_errors=errors)
    db.add(MonthlyExpense(user_id=user.id, title=form["title"], amount_toman=v["amount"], due_day=v["day"]))
    db.commit()
    return saved_response(request, "هزینهٔ ماهانه اضافه شد")


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
    from app.debts import _not_found, invalid_response, saved_response
    from app.debt_validation import validate_expense

    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        return _not_found(request, "هزینهٔ ماهانه پیدا نشد.")
    form = _expense_form(title, amount_toman, due_day)
    errors, v = validate_expense(amount_toman, due_day, Decimal(item.amount_toman))
    if errors:
        return invalid_response(request, db, user, errors, expense_form=form, expense_errors=errors,
                                editing_expense_id=expense_id)
    item.title = form["title"]
    item.amount_toman = v["amount"]
    item.due_day = v["day"]
    db.commit()
    return saved_response(request, "تغییرات ذخیره شد")


@router.post("/profile/expenses/{expense_id}/delete")
async def profile_delete_expense(
    expense_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        flash(request, "هزینهٔ ماهانه پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    db.delete(item)
    db.commit()
    from app.debts import saved_response

    return saved_response(request, "هزینهٔ ماهانه حذف شد")
