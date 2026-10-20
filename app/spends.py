"""Daily spend list, form, and save routes."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.daily_spend import (
    JALALI_MONTHS,
    _color_for,
    categories_for_user,
    ensure_spend_categories,
    jalali_month_bounds,
    month_chart,
    shift_jalali_month,
)
from app.db import get_db
from app.formatting import tehran_today, format_amount_input, format_jalali_date, format_toman, parse_jalali_parts, persian_digits
from app.models import DailySpend, SpendCategory, User
from app.number_input import parse_int_required
from app.spend_validation import CATEGORY_MSG, FIELD_ORDER, FIELD_SHORT, summary_fa, validate_spend
from app.security import get_authenticated_user, parse_decimal, redirect_to_login, require_csrf
from app.web import flash, render

import re as _re

# A spend saved by the Android app from an SMS: category «بانک» (slug sms_bank) and the note starts with
# the app's idempotency key «[<64 hex>]» (see api_sms_spend). No DB column needed; manual spends never
# get this prefix from the web form.
_SMS_KEY_PREFIX = _re.compile(r"^\[[0-9a-f]{64}\]\s*")


def sms_spend_parts(note: str | None, category_slug: str | None) -> tuple[bool, str]:
    """(from_sms, note without the internal key) for one spend."""
    note = note or ""
    m = _SMS_KEY_PREFIX.match(note)
    if m and category_slug == "sms_bank":
        return True, note[m.end():]
    return False, note

router = APIRouter()


def _day_label(spent, today, yesterday) -> str:
    base = f"{persian_digits(str(spent.day))} {JALALI_MONTHS[spent.month - 1]}"
    if spent == today:
        return f"امروز، {base}"
    if spent == yesterday:
        return f"دیروز، {base}"
    return base


def _rel_label(spent, today, yesterday) -> str:
    if spent == today:
        return "امروز"
    if spent == yesterday:
        return "دیروز"
    return f"{persian_digits(str(spent.day))} {JALALI_MONTHS[spent.month - 1]}"

def _viewed_jalali_month(request: Request, jy: str | None = None, jm: str | None = None) -> tuple[int, int]:
    today = tehran_today()
    year_raw = jy if jy is not None else request.query_params.get("jy", "")
    month_raw = jm if jm is not None else request.query_params.get("jm", "")
    try:
        year = parse_int_required(str(year_raw))
        month = parse_int_required(str(month_raw))
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
    spend_errors: dict | None = None,
) -> dict:
    ensure_spend_categories(db, user)
    has_any = db.query(DailySpend.id).filter(DailySpend.user_id == user.id).first() is not None
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
    today_g = tehran_today().togregorian()
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
    parent_index = {row.id: i for i, row in enumerate(parents)}
    today_j = tehran_today()
    yesterday_j = today_j - timedelta(days=1)
    day_totals: dict = {}
    for row in spends:
        day_totals[row.spent_on] = day_totals.get(row.spent_on, Decimal("0")) + Decimal(row.amount_toman)
    rows = []
    for row in spends:
        child = child_by_id.get(row.category_id)
        parent = parent_by_id.get(child.parent_id) if child and child.parent_id else None
        if child is None and row.category_id in parent_by_id:
            parent = parent_by_id[row.category_id]  # stored on the parent itself: show the parent, never «—»
        spent = jdatetime.date.fromgregorian(date=row.spent_on)
        name = child.name if child else (parent.name if parent else "سایر")
        parent_name = parent.name if parent else name
        rows.append(
            {
                "id": row.id,
                "date_label": format_jalali_date(spent),
                "spent_on": row.spent_on,
                "day_label": _day_label(spent, today_j, yesterday_j),
                "rel_label": _rel_label(spent, today_j, yesterday_j),
                "parent_name": parent_name,
                "child_name": name,
                "name": name,
                "color": _color_for(parent, parent_index.get(parent.id, 0)) if parent else "#475569",
                "initial": parent_name[:1],
                "amount_label": format_toman(Decimal(row.amount_toman)),
                "note": row.note or "",
                "from_sms": sms_spend_parts(row.note, child.slug if child else None)[0],
                "note_display": sms_spend_parts(row.note, child.slug if child else None)[1],
                "year": spent.year,
                "month": spent.month,
                "day": spent.day,
                "parent_id": parent.id if parent else "",
                "category_id": row.category_id,
                "amount_raw": format_amount_input(Decimal(row.amount_toman)),
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
        page = parse_int_required(str(page_raw))
    except ValueError:
        page = 1
    page = min(max(page, 1), page_count)
    visible = rows[: page * page_size]  # «نمایش ۱۵ خرج بیشتر» grows the list instead of replacing it
    groups: list[dict] = []
    for row in visible:
        if not groups or groups[-1]["date"] != row["spent_on"]:
            groups.append({"date": row["spent_on"], "label": row["day_label"],
                           "total_label": format_toman(day_totals[row["spent_on"]]), "rows": []})
        groups[-1]["rows"].append(row)
    month_name = JALALI_MONTHS[month - 1]
    sorted_slices = sorted(slices, key=lambda x: -x["amount"])
    for item in sorted_slices:
        item["share"] = round(item["amount"] * 100 / float(month_total)) if month_total else 0
        item["share_label"] = persian_digits(str(item["share"])) + "٪"
        item["amount_label"] = format_toman(Decimal(str(item["amount"])))
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
        today = tehran_today()
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
        "daily_parents": [
            {"id": row.id, "name": row.name, "color": _color_for(row, i), "slug": row.slug or ""}
            for i, row in enumerate(parents)
        ],
        "daily_children": [
            {"id": row.id, "name": row.name, "parent_id": row.parent_id} for row in children
        ],
        "daily_today_label": format_toman(today_total),
        "daily_month_label": format_toman(month_total),
        "daily_month_title": f"{JALALI_MONTHS[month - 1]} {persian_digits(str(year))}",
        "daily_slices": slices,
        "daily_top": sorted_slices[:4],
        "daily_rest": sorted_slices[4:],
        "daily_rest_label": persian_digits(str(len(sorted_slices) - 4)),
        "daily_groups": groups,
        "daily_total_count": len(rows),
        "daily_count_label": f"{persian_digits(str(len(visible)))} از {persian_digits(str(len(rows)))} خرج در {month_name}",
        "daily_more_label": f"نمایش {persian_digits(str(min(page_size, len(rows) - len(visible))))} خرج بیشتر",
        "daily_has_more": len(visible) < len(rows),
        "daily_month_name": month_name,
        "daily_is_current_month": (year, month) == (today_j.year, today_j.month),
        "daily_today_chip": f"امروز، {persian_digits(str(today_j.day))} {JALALI_MONTHS[today_j.month - 1]}",
        "daily_today_parts": [today_j.year, today_j.month, today_j.day],
        "daily_yesterday_parts": [yesterday_j.year, yesterday_j.month, yesterday_j.day],
        "daily_has_any": has_any,
        "spend_errors": spend_errors or {},
        "spend_error_summary": summary_fa(len(spend_errors)) if spend_errors else "",
        "spend_error_links": [(f, FIELD_SHORT[f]) for f in FIELD_ORDER if spend_errors and f in spend_errors],
        "daily_prev_year": prev_year,
        "daily_prev_month": prev_month,
        "daily_next_year": next_year,
        "daily_next_month": next_month,
        "daily_year": year,
        "daily_month": month,
        "spend_form": spend_form,
        "editing_spend_id": editing["id"] if editing else editing_spend_id,
        "spend_orig_amount": _orig_amount(db, user, editing["id"] if editing else editing_spend_id),
    }


def _orig_amount(db: Session, user: User, spend_id: int | None) -> str:
    """Stored amount (Latin, no grouping) of the row being edited; lets an unchanged legacy fraction save again."""
    if not spend_id:
        return ""
    row = db.get(DailySpend, spend_id)
    if row is None or row.user_id != user.id:
        return ""
    return format(Decimal(row.amount_toman).normalize(), "f")


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
    # Every bad field at once ({field: message}); the old single `error` stays for old clients.
    existing_amount = None
    if spend_id is not None:
        current = db.get(DailySpend, spend_id)
        if current is not None and current.user_id == user.id:
            existing_amount = Decimal(current.amount_toman)
    errors, amount, spent = validate_spend(amount_toman, year, month, day, existing_amount)
    child = None
    if category_id.isdigit():
        child = db.get(SpendCategory, int(category_id))
    if child is None or child.user_id != user.id or child.parent_id is None:
        errors["category_id"] = CATEGORY_MSG
        child = None
    wants_json = "application/json" in request.headers.get("accept", "")
    if errors or amount is None or spent is None or child is None:
        ordered = {f: errors[f] for f in FIELD_ORDER if f in errors}
        first = next(iter(ordered.values()), "خرج ذخیره نشد")
        if wants_json:
            return JSONResponse({"ok": False, "error": first, "fields": ordered}, status_code=422)
        return _render_daily_error(
            request,
            db,
            user,
            None,
            form,
            jy=jy,
            jm=jm,
            editing_spend_id=spend_id,
            spend_errors=ordered,
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
            if wants_json:
                return JSONResponse({"ok": False, "error": "خرج پیدا نشد.", "redirect": "/dashboard?tab=daily"}, status_code=404)
            return RedirectResponse("/dashboard?tab=daily", status_code=303)
        item.category_id = child.id
        item.amount_toman = amount
        item.spent_on = spent.togregorian()
        item.note = form["note"]
        flash(request, "خرج روزانه به‌روز شد.")
    db.commit()
    target = f"/dashboard?tab=daily&jy={spent.year}&jm={spent.month}"
    if wants_json:
        return JSONResponse({"ok": True, "redirect": target})
    return RedirectResponse(target, status_code=303)


def _render_daily_error(
    request: Request,
    db: Session,
    user: User,
    error: str | None,
    spend_form: dict,
    *,
    jy: str,
    jm: str,
    editing_spend_id: int | None,
    spend_errors: dict | None = None,
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
            spend_errors=spend_errors,
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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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
    user = get_authenticated_user(request, db)
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
    today = tehran_today()
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
