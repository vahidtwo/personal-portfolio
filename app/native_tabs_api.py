"""Read-only JSON mirrors of the signed-in tabs for the native Android screens.

Each endpoint reads the same functions the HTML pages use, so web and app show the same numbers.
No endpoint here writes user data, and none carries the salary or the salary-derived «مانده»:
those stay behind GET /api/salary, fetched on tap.
"""
from __future__ import annotations

from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import debt_schedule as ds
from app.assets_page import assets_context
from app.category_style import group_badge
from app.daily_spend import _color_for, categories_for_user, ensure_spend_categories, picker_categories
from app.db import get_db
from app.debts import debt_rows, expense_rows, expense_unpaid_total
from app.firebase_push import device_counts, firebase_admin_ready
from app.formatting import format_toman, format_when, tehran_today
from app.models import Debt, MonthlyExpense
from app.number_input import to_latin_digits
from app.security import get_authenticated_user

router = APIRouter(prefix="/api")

NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Cookie"}


def _json(data: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code, headers=NO_STORE)


def _login_required() -> JSONResponse:
    return _json({"error": "login required"}, status_code=401)


def _plain(value) -> str:
    """Exact stored value as plain Latin text for edit fields ('0' for zero)."""
    text = format(Decimal(value or 0), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _input_to_plain(text: str) -> str:
    """A form input value («۲٬۵۰۰٬۰۰۰», «۱٫۵») back to plain Latin text."""
    latin = to_latin_digits(text).replace("٬", "").replace("٫", ".")
    return latin or "0"


def _stored_quantities(user) -> dict[str, str]:
    from app.profile import HOLDING_FORM_FIELDS, holdings_form

    form = holdings_form(user)
    return {name: form[name] for name in HOLDING_FORM_FIELDS}


@router.get("/assets")
async def api_assets(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    form = _stored_quantities(user)
    ctx = assets_context(user, db, form)
    groups = []
    for group in ctx["asset_groups"]:
        rows = []
        for row in group["rows"]:
            rows.append({
                "key": row["key"],
                "field": row["field"],
                "name": row["name"],
                "symbol": row["symbol"],
                "unit": row["unit"],
                "held": row["held"],
                "quantity": _plain(getattr(user, row["field"])),
                "quantity_label": row["value"],
                "unit_price": row["price_plain"] or None,
                "has_price": row["value_label"] is not None,
                "value": row["value_plain"] or "0",
                "value_label": row["value_label"],
                "manual": row["manual"],
            })
        held = [r for r in rows if r["held"]]
        groups.append({
            "key": group["key"],
            "title": group["title"],
            "count": len(held),
            "subtotal": group["subtotal_plain"] or "0",
            "subtotal_label": group["subtotal_label"],
            "rows": rows,
        })
    car_value = Decimal(user.car_toman or 0)
    return _json({
        "total": ctx["assets_total_plain"] or "0",
        "total_label": ctx["assets_total_label"],
        "groups": groups,
        "car": {
            "state": ctx["car_state"],
            "value": _plain(car_value) if user.sanjeh_token else None,
            "value_label": ctx["car_value_label"],
            "count_label": ctx["car_count_label"],
            "ago": ctx["car_ago"],
        },
        "missing": ctx["missing_names"],
        "empty": not any(g["count"] for g in groups) and not user.sanjeh_token,
    })


def _category_rows(db: Session, user, keep_id: int | None = None) -> list[dict]:
    parents, children = categories_for_user(db, user)
    index = {row.id: i for i, row in enumerate(parents)}
    shown_parents, shown_children = picker_categories(parents, children, keep_id)
    out = []
    for parent in shown_parents:
        out.append({
            "id": parent.id,
            "name": parent.name,
            "slug": parent.slug or "",
            "icon": group_badge(parent.icon, parent.name),
            "color": _color_for(parent, index[parent.id]),
            "children": [{"id": c.id, "name": c.name, "slug": c.slug or ""}
                         for c in shown_children if c.parent_id == parent.id],
        })
    return out


@router.get("/categories")
async def api_categories(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    ensure_spend_categories(db, user)
    return _json({"categories": _category_rows(db, user)})


def _month_param(request: Request) -> tuple[str | None, str | None]:
    """?month=YYYY-MM (Jalali), or the web's ?jy=&jm=; anything else means this month."""
    raw = (request.query_params.get("month") or "").strip()
    if raw:
        year, _, month = raw.partition("-")
        return year, month
    return request.query_params.get("jy"), request.query_params.get("jm")


@router.get("/spends")
async def api_spends(request: Request, db: Session = Depends(get_db)):
    from app.spends import daily_view

    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    jy, jm = _month_param(request)
    view = daily_view(db, user, request, jy=jy or "", jm=jm or "")
    groups = []
    for group in view["daily_groups"]:
        groups.append({
            "date": group["date"].isoformat(),
            "label": group["label"],
            "total_label": group["total_label"],
            "rows": [{
                "id": row["id"],
                "date": row["spent_on"].isoformat(),
                "jalali": [row["year"], row["month"], row["day"]],
                "day_label": row["rel_label"],
                "category_id": row["category_id"],
                "parent_id": row["parent_id"] or None,
                "parent_name": row["parent_name"],
                "name": row["name"],
                "icon": row["initial"],
                "color": row["color"],
                "amount": _input_to_plain(row["amount_raw"]),
                "amount_label": row["amount_label"],
                "note": row["note_display"],
                "from_sms": bool(row["from_sms"]),
                "is_sms_bank": bool(row["is_sms_bank"]),
                "category_source": row["category_source"],
            } for row in group["rows"]],
        })
    top = [{"name": s["label"], "parent_id": s["parent_id"], "color": s.get("color"), "share": s["share"], "share_label": s["share_label"],
            "amount_label": s["amount_label"]} for s in view["daily_top"]]
    return _json({
        "year": view["daily_year"],
        "month": view["daily_month"],
        "month_title": view["daily_month_title"],
        "is_current_month": view["daily_is_current_month"],
        "prev": {"year": view["daily_prev_year"], "month": view["daily_prev_month"]},
        "next": {"year": view["daily_next_year"], "month": view["daily_next_month"]},
        "today_label": view["daily_today_label"],
        "month_label": view["daily_month_label"],
        "top": top,
        "rest_count": len(view["daily_rest"]),
        "groups": groups,
        "count_label": view["daily_count_label"],
        "total_count": view["daily_total_count"],
        "page": view["daily_page"],
        "page_count": view["daily_page_count"],
        "has_more": view["daily_has_more"],
        "has_any": view["daily_has_any"],
        "today": view["daily_today_parts"],
        "yesterday": view["daily_yesterday_parts"],
    })


def _next_strip(nearest: dict | None) -> dict | None:
    if not nearest:
        return None
    return {
        "date": nearest["date"].togregorian().isoformat(),
        "date_label": nearest["date_label"],
        "days": nearest["days"],
        "chip": nearest["chip"],
        "title": nearest["title"],
        "amount_label": nearest["amount_label"],
        "overdue_count": nearest["overdue_count"],
        "overdue_label": nearest["overdue_label"],
    }


def _debt_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["display_title"],
        "active": row["active"],
        "months_left": row["months_left"],
        "months_label": row["months_label"],
        "monthly": row["monthly_orig"],
        "monthly_label": row["monthly_label"],
        "remaining_label": row["total_label"],
        "due": [int(row["due_year"]), int(row["due_month"]), int(row["due_day"])],
        "next_label": row["next_label"],
        "next_short": row["next_short"],
        "days": row["days"],
        "end_label": row["end_label"],
        "overdue": row["overdue"],
        "overdue_label": row["overdue_label"],
        "missed": row["missed"],
        "badge": row["badge"],
        "badge_label": row["badge_label"],
        "reminder_days_before": int(row["reminder_days_before"]),
    }


def _expense_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["display_title"],
        "amount": row["amount_orig"],
        "amount_label": row["amount_label"],
        "due_day": int(row["due_day"]),
        "day_label": row["day_label"],
        "next_label": row["next_label"],
        "paid_this_month": row["paid_this_month"],
        "overdue": row["overdue"],
    }


@router.get("/debts")
async def api_debts(request: Request, db: Session = Depends(get_db)):
    """Summary «این ماه» and the loans. The salary «مانده» tile is not here: it comes from /api/salary."""
    from app.formatting import tehran_today

    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    today = tehran_today()
    debts = db.query(Debt).filter(Debt.user_id == user.id, Debt.deleted_at.is_(None)).all()
    items = db.query(MonthlyExpense).filter(MonthlyExpense.user_id == user.id).all()
    rows, total, _ = debt_rows(debts, today)
    installment, installment_overdue = ds.month_due(debts, today)
    expense_total = sum((Decimal(i.amount_toman) for i in items), Decimal("0"))
    return _json({
        "summary": {
            "installments_label": format_toman(installment),
            "installments_overdue_label": format_toman(installment_overdue) if installment_overdue else None,
            "month_installments_label": format_toman(ds.this_month_installments(debts, today)),
            "expenses_label": format_toman(expense_total),
            "total_label": format_toman(total),
        },
        "next": _next_strip(ds.soonest(debts, today)),
        "active_count": sum(1 for r in rows if r["active"]),
        "debts": [_debt_json(r) for r in rows],
        "empty": not rows and not items,
    })


@router.get("/expenses")
async def api_expenses(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    today = tehran_today()
    items = db.query(MonthlyExpense).filter(MonthlyExpense.user_id == user.id).all()
    total = sum((Decimal(i.amount_toman) for i in items), Decimal("0"))
    unpaid = expense_unpaid_total(items, today)
    rows = expense_rows(items, today)
    return _json({
        "total_label": format_toman(total),
        "unpaid_this_month_label": format_toman(unpaid),
        "all_paid": bool(rows) and all(r["paid_this_month"] for r in rows),
        "expenses": [_expense_json(r) for r in rows],
    })


@router.get("/settings")
async def api_settings(request: Request, db: Session = Depends(get_db)):
    """Account fields and switches. Never the salary itself, only whether one is saved."""
    user = get_authenticated_user(request, db)
    if user is None:
        return _login_required()
    return _json({
        "account": {"full_name": user.full_name or "", "username": user.username, "mobile": user.mobile or ""},
        "has_salary": Decimal(user.salary_toman or 0) > 0,
        "has_mcp_token": bool(user.mcp_token_hash),
        "car_connected": bool(user.sanjeh_token),
        "car_fetched_label": format_when(user.car_fetched_at) if user.sanjeh_token else None,
        "push": {"server": firebase_admin_ready(), "devices": device_counts(db, user.id)},
    })
