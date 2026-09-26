"""Daily spend list, form, and save routes."""

from __future__ import annotations

from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.daily_spend import (
    JALALI_MONTHS,
    categories_for_user,
    ensure_spend_categories,
    jalali_month_bounds,
    month_chart,
    shift_jalali_month,
)
from app.db import get_db
from app.formatting import format_jalali_date, format_toman, parse_jalali_parts, persian_digits
from app.models import DailySpend, SpendCategory, User
from app.security import get_current_user, parse_decimal, require_csrf
from app.web import flash, render

router = APIRouter()

def _viewed_jalali_month(request: Request, jy: str | None = None, jm: str | None = None) -> tuple[int, int]:
    today = jdatetime.date.today()
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    year_raw = jy if jy is not None else request.query_params.get("jy", "")
    month_raw = jm if jm is not None else request.query_params.get("jm", "")
    try:
        year = int(str(year_raw).translate(trans))
        month = int(str(month_raw).translate(trans))
        jdatetime.date(year, month, 1)
    except (TypeError, ValueError):
        return today.year, today.month
    return year, month


def daily_view(
    db: Session,
    user: User,
    request: Request,
    *,
    spend_form: dict | None = None,
    jy: str | None = None,
    jm: str | None = None,
    editing_spend_id: int | None = None,
) -> dict:
    ensure_spend_categories(db, user)
    year, month = _viewed_jalali_month(request, jy, jm)
    parents, children = categories_for_user(db, user)
    parent_by_id = {row.id: row for row in parents}
    child_by_id = {row.id: row for row in children}
    start, end = jalali_month_bounds(year, month)
    spends = (
        db.query(DailySpend)
        .filter(DailySpend.user_id == user.id, DailySpend.spent_on >= start, DailySpend.spent_on < end)
        .order_by(DailySpend.spent_on.desc(), DailySpend.id.desc())
        .all()
    )
    today_g = jdatetime.date.today().togregorian()
    today_total = sum(
        (
            Decimal(row.amount_toman)
            for row in db.query(DailySpend)
            .filter(DailySpend.user_id == user.id, DailySpend.spent_on == today_g)
            .all()
        ),
        Decimal("0"),
    )
    slices, month_total = month_chart(db, user, year, month)
    rows = []
    for row in spends:
        child = child_by_id.get(row.category_id)
        parent = parent_by_id.get(child.parent_id) if child and child.parent_id else None
        spent = jdatetime.date.fromgregorian(date=row.spent_on)
        rows.append(
            {
                "id": row.id,
                "date_label": format_jalali_date(spent),
                "parent_name": parent.name if parent else "—",
                "child_name": child.name if child else "—",
                "amount_label": format_toman(Decimal(row.amount_toman)),
                "note": row.note or "",
                "year": spent.year,
                "month": spent.month,
                "day": spent.day,
                "parent_id": parent.id if parent else "",
                "category_id": row.category_id,
                "amount_raw": format(Decimal(row.amount_toman), "f").rstrip("0").rstrip("."),
            }
        )
    edit_raw = request.query_params.get("edit_spend", "")
    if editing_spend_id is None and edit_raw.isdigit():
        editing_spend_id = int(edit_raw)
    editing = next((row for row in rows if editing_spend_id and row["id"] == editing_spend_id), None)
    page_size = 15
    page_count = max(1, (len(rows) + page_size - 1) // page_size)
    page_raw = request.query_params.get("page", "1")
    try:
        page = int(str(page_raw).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
    except ValueError:
        page = 1
    page = min(max(page, 1), page_count)
    visible = rows[(page - 1) * page_size : page * page_size]
    if spend_form is None and editing:
        spend_form = {
            "amount_toman": editing["amount_raw"],
            "year": str(editing["year"]),
            "month": str(editing["month"]),
            "day": str(editing["day"]),
            "parent_id": str(editing["parent_id"]),
            "category_id": str(editing["category_id"]),
            "note": editing["note"],
        }
    if spend_form is None:
        today = jdatetime.date.today()
        first_parent = parents[0].id if parents else ""
        first_child = next((child.id for child in children if child.parent_id == first_parent), "")
        spend_form = {
            "amount_toman": "",
            "year": str(today.year),
            "month": str(today.month),
            "day": str(today.day),
            "parent_id": str(first_parent),
            "category_id": str(first_child),
            "note": "",
        }
    prev_year, prev_month = shift_jalali_month(year, month, -1)
    next_year, next_month = shift_jalali_month(year, month, 1)
    return {
        "daily_rows": visible,
        "daily_page": page,
        "daily_page_count": page_count,
        "daily_page_label": persian_digits(str(page)),
        "daily_page_count_label": persian_digits(str(page_count)),
        "daily_parents": [{"id": row.id, "name": row.name} for row in parents],
        "daily_children": [
            {"id": row.id, "name": row.name, "parent_id": row.parent_id} for row in children
        ],
        "daily_today_label": format_toman(today_total),
        "daily_month_label": format_toman(month_total),
        "daily_month_title": f"{JALALI_MONTHS[month - 1]} {persian_digits(str(year))}",
        "daily_slices": slices,
        "daily_prev_year": prev_year,
        "daily_prev_month": prev_month,
        "daily_next_year": next_year,
        "daily_next_month": next_month,
        "daily_year": year,
        "daily_month": month,
        "spend_form": spend_form,
        "editing_spend_id": editing["id"] if editing else editing_spend_id,
    }


def _spend_form_dict(amount, year, month, day, category_id, note, parent_id: str = "") -> dict:
    return {
        "amount_toman": amount,
        "year": year,
        "month": month,
        "day": day,
        "parent_id": parent_id,
        "category_id": category_id,
        "note": (note or "").strip()[:120],
    }


def _save_daily_spend(
    request: Request,
    db: Session,
    user: User,
    spend_id: int | None,
    amount_toman: str,
    year: str,
    month: str,
    day: str,
    category_id: str,
    note: str,
    parent_id: str,
    jy: str,
    jm: str,
) -> HTMLResponse | RedirectResponse:
    ensure_spend_categories(db, user)
    form = _spend_form_dict(amount_toman, year, month, day, category_id, note, parent_id)
    try:
        amount = parse_decimal(amount_toman, field="مبلغ")
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or "مبلغ نامعتبر است")
        amount = None
    else:
        error = "مبلغ باید بیشتر از صفر باشد" if amount <= 0 else None
    spent, date_error = parse_jalali_parts(year, month, day)
    error = error or date_error
    child = None
    if category_id.isdigit():
        child = db.get(SpendCategory, int(category_id))
    if child is None or child.user_id != user.id or child.parent_id is None:
        error = error or "زیردسته را انتخاب کنید"
        child = None
    if error or amount is None or spent is None or child is None:
        return _render_daily_error(
            request,
            db,
            user,
            error or "خرج ذخیره نشد",
            form,
            jy=jy,
            jm=jm,
            editing_spend_id=spend_id,
        )
    if spend_id is None:
        db.add(
            DailySpend(
                user_id=user.id,
                category_id=child.id,
                amount_toman=amount,
                spent_on=spent.togregorian(),
                note=form["note"],
            )
        )
        flash(request, "خرج روزانه ذخیره شد.")
    else:
        item = db.get(DailySpend, spend_id)
        if item is None or item.user_id != user.id:
            flash(request, "خرج پیدا نشد.", error=True)
            return RedirectResponse("/dashboard?tab=daily", status_code=303)
        item.category_id = child.id
        item.amount_toman = amount
        item.spent_on = spent.togregorian()
        item.note = form["note"]
        flash(request, "خرج روزانه به‌روز شد.")
    db.commit()
    return RedirectResponse(
        f"/dashboard?tab=daily&jy={spent.year}&jm={spent.month}",
        status_code=303,
    )


def _render_daily_error(
    request: Request,
    db: Session,
    user: User,
    error: str,
    spend_form: dict,
    *,
    jy: str,
    jm: str,
    editing_spend_id: int | None,
):
    return render(
        request,
        "dashboard.html",
        db,
        error=error,
        flash=None,
        flash_error=False,
        tab="daily",
        **daily_view(
            db,
            user,
            request,
            spend_form=spend_form,
            jy=jy,
            jm=jm,
            editing_spend_id=editing_spend_id,
        ),
    )


@router.post("/profile/spends")
async def profile_add_spend(
    request: Request,
    amount_toman: str = Form(""),
    year: str = Form(""),
    month: str = Form(""),
    day: str = Form(""),
    parent_id: str = Form(""),
    category_id: str = Form(""),
    note: str = Form(""),
    jy: str = Form(""),
    jm: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _save_daily_spend(
        request, db, user, None, amount_toman, year, month, day, category_id, note, parent_id, jy, jm
    )


@router.post("/profile/spends/{spend_id}")
async def profile_edit_spend(
    spend_id: int,
    request: Request,
    amount_toman: str = Form(""),
    year: str = Form(""),
    month: str = Form(""),
    day: str = Form(""),
    parent_id: str = Form(""),
    category_id: str = Form(""),
    note: str = Form(""),
    jy: str = Form(""),
    jm: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _save_daily_spend(
        request, db, user, spend_id, amount_toman, year, month, day, category_id, note, parent_id, jy, jm
    )


@router.post("/profile/spends/{spend_id}/delete")
async def profile_delete_spend(
    spend_id: int,
    request: Request,
    jy: str = Form(""),
    jm: str = Form(""),
    page: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    item = db.get(DailySpend, spend_id)
    if item is None or item.user_id != user.id:
        flash(request, "خرج پیدا نشد.", error=True)
    else:
        db.delete(item)
        db.commit()
        flash(request, "خرج روزانه حذف شد.")
    target = f"/dashboard?tab=daily&jy={jy}&jm={jm}"
    if page.isdigit() and int(page) > 1:
        target += f"&page={int(page)}"
    return RedirectResponse(target, status_code=303)


@router.post("/api/sms-spend")
async def api_sms_spend(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return JSONResponse({"ok": False, "error": "login"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    try:
        amount = parse_decimal(str(payload.get("amount_toman", "")), field="مبلغ")
    except Exception:
        return JSONResponse({"ok": False, "error": "amount"}, status_code=400)
    if amount <= 0:
        return JSONResponse({"ok": False, "error": "amount"}, status_code=400)
    raw_note = str(payload.get("note") or "").strip()
    idem = str(payload.get("idempotency_key") or "").strip()[:64]
    note = raw_note[:120]
    if idem:
        note = f"[{idem}] {note}".strip()[:120]
    ensure_spend_categories(db, user)
    child = (
        db.query(SpendCategory)
        .filter(SpendCategory.user_id == user.id, SpendCategory.slug == "sms_bank")
        .one_or_none()
    )
    if child is None:
        return JSONResponse({"ok": False, "error": "category"}, status_code=500)
    today = jdatetime.date.today()
    spent_on = today.togregorian()
    duplicate_query = db.query(DailySpend).filter(DailySpend.user_id == user.id)
    if idem:
        duplicate = duplicate_query.filter(DailySpend.note.like(f"[{idem}]%")).first()
    else:
        duplicate = duplicate_query.filter(
            DailySpend.category_id == child.id,
            DailySpend.amount_toman == amount,
            DailySpend.spent_on == spent_on,
            DailySpend.note == note,
        ).first()
    if duplicate is not None:
        return JSONResponse({"ok": True, "id": duplicate.id, "duplicate": True})
    item = DailySpend(
        user_id=user.id,
        category_id=child.id,
        amount_toman=amount,
        spent_on=spent_on,
        note=note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return JSONResponse({"ok": True, "id": item.id})
