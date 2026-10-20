"""Debts v2 (/profile?tab=debts): instalment debts and monthly expenses.

Backend for the v2 page: sorted rows, per-field errors (JSON 422 for fetch), and the manual
«پرداخت شد» route with its undo. No schema change: months_left is decremented in place and
(due_year, due_month) moves a month on; nothing is derived from the calendar.
"""

from __future__ import annotations

from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import debt_schedule as ds
from app.db import get_db
from app.debt_validation import FIELD_SHORT, summary_fa, validate_debt, validate_expense
from app.formatting import format_amount_input, format_jalali_date, format_toman, format_when, persian_digits, tehran_today
from app.models import Debt, MonthlyExpense, User
from app.security import get_authenticated_user, redirect_to_login, require_csrf
from app.web import flash, pop_flash, render

router = APIRouter()
DEBTS_URL = "/profile?tab=debts"
EMPTY_DEBT_FORM = {"title": "", "monthly_toman": "", "months_left": "", "due_year": "", "due_month": "", "due_day": ""}
EMPTY_EXPENSE_FORM = {"title": "", "amount_toman": "", "due_day": ""}


def _holdings_form(user):
    from app.profile import holdings_form

    return holdings_form(user)


def _monthly_view(db, user, **kwargs):
    from app.expenses import monthly_view

    return monthly_view(db, user, **kwargs)


def _edit_date(debt) -> jdatetime.date | None:
    try:
        return ds.clamp(debt.due_year, debt.due_month, debt.due_day)
    except (TypeError, ValueError):
        return None


def debt_rows(debts: list[Debt], today: jdatetime.date | None = None) -> tuple[list[dict], Decimal, str]:
    """(rows sorted by nearest instalment, remaining total of ACTIVE debts, soonest date label).

    Debts with months_left == 0 are listed last and excluded from the total.
    """
    today = today or tehran_today()
    rows = []
    for debt in sorted(debts, key=lambda d: ds.sort_key(d, today)):
        months = int(debt.months_left or 0)
        active = months > 0
        nxt = ds.next_due(debt, today)
        end = ds.end_due(debt, today)
        amount = ds.remaining(debt)
        stored = _edit_date(debt)
        kind, badge_label = ds.badge(months)
        title = (debt.title or "").strip()
        rows.append(
            {
                "id": debt.id,
                "title": title,
                "display_title": title or "قسط",
                "active": active,
                "months_left": months,
                "monthly_raw": format_amount_input(Decimal(debt.monthly_toman)),
                "monthly_orig": format(Decimal(debt.monthly_toman).normalize(), "f"),
                "months_raw": str(months),
                "due_year": str(stored.year if stored else debt.due_year),
                "due_month": str(stored.month if stored else debt.due_month),
                "due_day": str(stored.day if stored else debt.due_day),
                "monthly_label": format_toman(debt.monthly_toman),
                "months_label": persian_digits(str(months)),
                "entered_label": format_jalali_date(stored) if stored else "—",
                "total_label": format_toman(amount),
                "next_label": format_jalali_date(nxt) if nxt else "—",
                "next_short": ds.day_month(nxt) if nxt else None,
                "days": (nxt.togregorian() - today.togregorian()).days if nxt else None,
                "end_label": ds.month_year(end) if end else None,
                "badge": kind,
                "badge_label": badge_label,
            }
        )
    nearest = ds.soonest(debts, today)
    return rows, ds.active_total(debts), format_jalali_date(nearest["date"]) if nearest else "—"


def expense_next(day: int, today: jdatetime.date) -> jdatetime.date:
    """Next date with that day of month; a short month counts its last day (form hint)."""
    candidate = ds.clamp(today.year, today.month, day)
    if candidate < today:
        y, m = ds.add_months(today.year, today.month, 1)
        candidate = ds.clamp(y, m, day)
    return candidate


def expense_rows(items: list[MonthlyExpense], today: jdatetime.date | None = None) -> list[dict]:
    today = today or tehran_today()
    rows = []
    for item in sorted(items, key=lambda e: (e.due_day, e.id)):
        amount = Decimal(item.amount_toman)
        rows.append(
            {
                "id": item.id,
                "title": (item.title or "").strip(),
                "display_title": (item.title or "").strip() or "هزینه",
                "amount_raw": format_amount_input(amount),
                "amount_orig": format(amount.normalize(), "f"),
                "due_day": str(item.due_day),
                "amount_label": format_toman(amount),
                "day_label": persian_digits(str(item.due_day)),
                "next_label": ds.day_month(expense_next(item.due_day, today)),
            }
        )
    return rows


def debts_page(
    db: Session,
    user: User,
    request: Request,
    *,
    debt_form: dict | None = None,
    debt_errors: dict | None = None,
    editing_id: int | None = None,
    expense_form: dict | None = None,
    expense_errors: dict | None = None,
    editing_expense_id: int | None = None,
) -> dict:
    """Context for the v2 debts partial (passed as `dv`)."""
    today = tehran_today()
    debts = db.query(Debt).filter(Debt.user_id == user.id).all()
    items = db.query(MonthlyExpense).filter(MonthlyExpense.user_id == user.id).all()
    rows, total, _ = debt_rows(debts, today)
    exp_rows = expense_rows(items, today)
    installment = ds.active_installment(debts)
    expense_total = sum((Decimal(i.amount_toman) for i in items), Decimal("0"))
    sheet = None
    if debt_errors or editing_id:
        sheet = "debt"
    elif expense_errors or editing_expense_id:
        sheet = "expense"
    undo = request.session.get("debt_undo") if hasattr(request, "session") else None
    banner = None
    if undo and undo.get("show"):
        banner = {"id": undo["id"], "title": undo.get("title") or "قسط", "expect": undo["after"][0]}
        undo["show"] = False
        request.session["debt_undo"] = undo
    nearest = ds.soonest(debts, today)
    errs = debt_errors or expense_errors or {}
    return {
        "rows": rows,
        "expenses": exp_rows,
        "has_debts": bool(rows),
        "has_expenses": bool(exp_rows),
        "active_count": sum(1 for r in rows if r["active"]),
        "total_label": format_toman(total),
        "installment_label": format_toman(installment),
        "expense_label": format_toman(expense_total),
        "next": nearest,
        "debt_form": debt_form or EMPTY_DEBT_FORM,
        "debt_errors": debt_errors or {},
        "editing_id": editing_id,
        "expense_form": expense_form or EMPTY_EXPENSE_FORM,
        "expense_errors": expense_errors or {},
        "editing_expense_id": editing_expense_id,
        "sheet": sheet,
        "summary": summary_fa(len(errs)) if errs else None,
        "summary_links": [(f, FIELD_SHORT.get(f, f)) for f in errs],
        "banner": banner,
        "today_year": today.year,
    }


def _edit_form_from_query(rows: list[dict], exp_rows: list[dict], request: Request):
    edit_raw = request.query_params.get("edit", "")
    spend_raw = request.query_params.get("spend", "")
    debt = next((r for r in rows if edit_raw.isdigit() and r["id"] == int(edit_raw)), None)
    exp = next((r for r in exp_rows if spend_raw.isdigit() and r["id"] == int(spend_raw)), None)
    return debt, exp


def page_context_for_get(db: Session, user: User, request: Request) -> dict:
    """GET /profile?tab=debts: honours ?edit=<debt id> and ?spend=<expense id> (no-JS edit links)."""
    base = debts_page(db, user, request)
    debt, exp = _edit_form_from_query(base["rows"], base["expenses"], request)
    if debt:
        base.update(sheet="debt", editing_id=debt["id"], debt_form={
            "title": debt["title"], "monthly_toman": debt["monthly_raw"], "months_left": debt["months_raw"],
            "due_year": debt["due_year"], "due_month": debt["due_month"], "due_day": debt["due_day"]})
        base["debt_orig"] = debt["monthly_orig"]
    elif exp:
        base.update(sheet="expense", editing_expense_id=exp["id"], expense_form={
            "title": exp["title"], "amount_toman": exp["amount_raw"], "due_day": exp["due_day"]})
        base["expense_orig"] = exp["amount_orig"]
    return base


def render_debts(request: Request, db: Session, user: User, *, status_code: int = 200, **kwargs):
    """Server-rendered debts page with errors at their fields (the no-JS path)."""
    debts_rows, debt_total, next_debt_label = debt_rows(db.query(Debt).filter(Debt.user_id == user.id).all())
    dv = debts_page(db, user, request, **kwargs)
    response = render(
        request,
        "profile.html",
        db,
        error=None,
        flash=None,
        form=_holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab="debts",
        debts=debts_rows,
        debt_total_label=format_toman(debt_total),
        next_debt_label=next_debt_label,
        editing_id=kwargs.get("editing_id"),
        debt_form=dv["debt_form"],
        dv=dv,
        **_monthly_view(db, user),
    )
    response.status_code = status_code
    return response


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def invalid_response(request, db, user, errors: dict, **kwargs):
    first = next(iter(errors.values()), "ذخیره نشد")
    if wants_json(request):
        return JSONResponse({"ok": False, "error": first, "fields": errors}, status_code=422)
    return render_debts(request, db, user, **kwargs)


def saved_response(request, message: str):
    flash(request, message)
    if wants_json(request):
        return JSONResponse({"ok": True, "redirect": DEBTS_URL})
    return RedirectResponse(DEBTS_URL, status_code=303)


def _debt_form(title, monthly_toman, months_left, due_year, due_month, due_day) -> dict:
    return {"title": title.strip()[:64], "monthly_toman": monthly_toman, "months_left": months_left,
            "due_year": due_year, "due_month": due_month, "due_day": due_day}


def _owned_debt(db, user, debt_id) -> Debt | None:
    debt = db.get(Debt, debt_id)
    return debt if debt is not None and debt.user_id == user.id else None


def _not_found(request, message="بدهی پیدا نشد."):
    if wants_json(request):
        return JSONResponse({"ok": False, "error": message, "fields": {}}, status_code=404)
    flash(request, message, error=True)
    return RedirectResponse(DEBTS_URL, status_code=303)


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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    form = _debt_form(title, monthly_toman, months_left, due_year, due_month, due_day)
    errors, v = validate_debt(monthly_toman, months_left, due_year, due_month, due_day)
    if errors:
        return invalid_response(request, db, user, errors, debt_form=form, debt_errors=errors)
    db.add(Debt(user_id=user.id, title=form["title"], monthly_toman=v["monthly"], months_left=v["months"],
                due_year=v["year"], due_month=v["month"], due_day=v["day"]))
    db.commit()
    return saved_response(request, "قسط اضافه شد")


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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    debt = _owned_debt(db, user, debt_id)
    if debt is None:
        return _not_found(request)
    form = _debt_form(title, monthly_toman, months_left, due_year, due_month, due_day)
    errors, v = validate_debt(monthly_toman, months_left, due_year, due_month, due_day, Decimal(debt.monthly_toman))
    if errors:
        return invalid_response(request, db, user, errors, debt_form=form, debt_errors=errors, editing_id=debt_id)
    debt.title = form["title"]
    debt.monthly_toman = v["monthly"]
    debt.months_left = v["months"]
    debt.due_year, debt.due_month, debt.due_day = v["year"], v["month"], v["day"]
    db.commit()
    request.session.pop("debt_undo", None)  # an edit replaces whatever «برگردان» would restore
    return saved_response(request, "تغییرات ذخیره شد")


def _state(debt) -> list[int]:
    return [int(debt.months_left), int(debt.due_year), int(debt.due_month), int(debt.due_day)]


@router.post("/profile/debts/{debt_id}/paid")
async def profile_debt_paid(
    debt_id: int,
    request: Request,
    expect: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    """«پرداخت شد، یک قسط کم کن»: months_left − 1 and the next due a month on.

    Idempotent-safe: `expect` is the count the user saw; a repeated or stale POST (double tap,
    back button, second tab) no longer matches and changes nothing.
    """
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    debt = _owned_debt(db, user, debt_id)
    if debt is None:
        return _not_found(request)
    months = int(debt.months_left or 0)
    if not expect.strip().isdigit() or int(expect) != months or months <= 0:
        message = "این پرداخت قبلاً ثبت شده بود؛ چیزی تغییر نکرد."
        if wants_json(request):
            return JSONResponse({"ok": False, "error": message, "fields": {}}, status_code=409)
        flash(request, message, error=True)
        return RedirectResponse(DEBTS_URL, status_code=303)
    before = _state(debt)
    nxt = ds.next_due(debt)
    y, m = ds.add_months(nxt.year, nxt.month, 1)
    debt.months_left = months - 1
    debt.due_year, debt.due_month = y, m  # due_day kept: a day-31 loan stays day 31 (readers clamp)
    db.commit()
    title = (debt.title or "").strip() or "قسط"
    request.session["debt_undo"] = {"id": debt.id, "title": title, "before": before, "after": _state(debt), "show": True}
    if wants_json(request):
        return JSONResponse({"ok": True, "redirect": DEBTS_URL})
    return RedirectResponse(DEBTS_URL, status_code=303)


@router.post("/profile/debts/{debt_id}/unpaid")
async def profile_debt_unpaid(
    debt_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    """«برگردان»: restores exactly the count and date from before the last «پرداخت شد».

    Only when the debt is still in the state that «پرداخت شد» left; otherwise nothing changes.
    """
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    debt = _owned_debt(db, user, debt_id)
    undo = request.session.get("debt_undo") or {}
    if debt is None or undo.get("id") != debt_id or _state(debt) != list(undo.get("after") or []):
        flash(request, "چیزی برای برگرداندن نیست.", error=True)
        return RedirectResponse(DEBTS_URL, status_code=303)
    debt.months_left, debt.due_year, debt.due_month, debt.due_day = undo["before"]
    db.commit()
    request.session.pop("debt_undo", None)
    flash(request, f"پرداخت «{undo.get('title') or 'قسط'}» برگردانده شد.")
    return RedirectResponse(DEBTS_URL, status_code=303)


@router.post("/profile/debts/{debt_id}/delete")
async def profile_delete_debt(
    debt_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    debt = _owned_debt(db, user, debt_id)
    if debt is None:
        return _not_found(request)
    db.delete(debt)
    db.commit()
    undo = request.session.get("debt_undo") or {}
    if undo.get("id") == debt_id:
        request.session.pop("debt_undo", None)
    flash(request, "قسط حذف شد")
    return RedirectResponse(DEBTS_URL, status_code=303)
