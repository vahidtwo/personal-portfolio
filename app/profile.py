"""Profile holdings, account, and MCP token."""

from __future__ import annotations

import json
import logging
import secrets
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import PUBLIC_BASE_URL
from app.db import get_db
from app.debts import debt_rows, page_context_for_get
from app.expenses import expense_form_for_request
from app.formatting import format_amount_input, format_qty_input, format_toman, format_when
from app.jobs import refresh_prices_and_snapshot_user, refresh_user_sanjeh_car
from app.firebase_push import firebase_admin_ready, send_push_to_user
from app.mcp_http import hash_mcp_token
from app.models import Debt, User, utcnow
from app.sanjeh import SanjehAuthError
from app.number_input import FIELD_ERROR_SHORT_FA, field_error_message, quantity_error, to_latin_digits
from app.security import (
    get_authenticated_user,
    redirect_to_login,
    hash_password,
    admin_name_change_error,
    normalize_username,
    parse_decimal,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)
from app.web import flash, pop_flash, render

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/profile", response_class=HTMLResponse)
async def profile_form(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get("tab", "settings")
    if tab == "assets":
        # Phase 1: assets moved to their own page. Old links keep working (session cookie untouched).
        return RedirectResponse("/assets", status_code=303)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    if tab != "debts":
        tab = "settings"
    debts, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
    )
    edit_raw = request.query_params.get("edit", "")
    editing = next((row for row in debts if edit_raw.isdigit() and row["id"] == int(edit_raw)), None)
    debt_form = (
        {
            "title": editing["title"],
            "monthly_toman": editing["monthly_raw"],
            "months_left": editing["months_raw"],
            "due_year": editing["due_year"],
            "due_month": editing["due_month"],
            "due_day": editing["due_day"],
        }
        if editing
        else {"title": "", "monthly_toman": "", "months_left": "", "due_year": "", "due_month": "", "due_day": ""}
    )
    flash_message, flash_error = pop_flash(request)
    mcp_token = request.session.pop("mcp_token_once", None)
    mcp_cursor_config = None
    # Display only: /mcp is served by this same app (public at <site>/mcp).
    mcp_url = (PUBLIC_BASE_URL or str(request.base_url).rstrip("/")) + "/mcp"
    if mcp_token:
        mcp_cursor_config = json.dumps(
            {
                "mcpServers": {
                    "my-inventory": {
                        "url": mcp_url,
                        "headers": {"Authorization": f"Bearer {mcp_token}"},
                    }
                }
            },
            indent=2,
            ensure_ascii=False,
        )
    return render(
        request,
        "profile.html",
        db,
        mcp_token=mcp_token,
        mcp_cursor_config=mcp_cursor_config,
        mcp_url=mcp_url,
        error=None,
        flash=flash_message,
        flash_error=flash_error,
        form=holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab=tab,
        dv=page_context_for_get(db, user, request) if tab == "debts" else None,
        debts=debts,
        debt_total_label=format_toman(debt_total),
        next_debt_label=next_debt_label,
        editing_id=editing["id"] if editing else None,
        debt_form=debt_form,
        account=_account_form(user),
        account_error=None,
        **expense_form_for_request(db, user, request),
    )


@router.post("/profile/mcp-token")
async def issue_mcp_token(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    raw = secrets.token_urlsafe(32)
    user.mcp_token_hash = hash_mcp_token(raw)
    db.commit()
    request.session["mcp_token_once"] = raw
    flash(request, "توکن MCP ساخته شد. همین حالا کپی کنید.")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/push-test")
async def push_test_notification(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    if not firebase_admin_ready():
        flash(request, "Firebase پیکربندی نشده است.", error=True)
        return RedirectResponse("/profile", status_code=303)
    sent = send_push_to_user(
        db,
        user.id,
        title="موجودی من",
        body="اعلان آزمایشی",
        data={"type": "test"},
    )
    if sent:
        flash(request, f"اعلان به {sent} دستگاه ارسال شد.")
    else:
        flash(request, "توکن push ثبت نشده یا ارسال ناموفق بود.", error=True)
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/mcp-token/revoke")
async def revoke_mcp_token(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    user.mcp_token_hash = None
    db.commit()
    flash(request, "توکن MCP حذف شد.")
    return RedirectResponse("/profile", status_code=303)
def _account_form(user: User, **overrides: str) -> dict[str, str]:
    # Privacy mode: the stored salary is never put in the form; the input starts empty.
    data = {
        "full_name": user.full_name or "",
        "username": user.username,
        "mobile": user.mobile or "",
        "salary_toman": "",
    }
    data.update(overrides)
    return data


def _parse_mobile(raw: str) -> tuple[str | None, str | None]:
    text = to_latin_digits(raw).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits == "":
        return "", None
    if not 10 <= len(digits) <= 15:
        return None, "شماره موبایل باید ۱۰ تا ۱۵ رقم باشد"
    return digits, None


def _render_account_error(request, db, user, message: str, account: dict):
    return render(
        request,
        "profile.html",
        db,
        error=None,
        flash=None,
        form=holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab="settings",
        account=account,
        account_error=message,
    )


@router.post("/profile/account")
async def profile_account(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    mobile: str = Form(""),
    salary_toman: str = Form(""),
    current_password: str = Form(""),
    new_password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    account = {
        "full_name": full_name.strip()[:80],
        "username": username,
        "mobile": mobile,
        "salary_toman": "",  # never echoed back into the page
    }
    name = normalize_username(username)
    name_error = validate_username(name) or admin_name_change_error(user.username, name)
    if name_error:
        return _render_account_error(request, db, user, name_error, account)
    taken = db.query(User).filter(User.username == name, User.id != user.id).first()
    if taken is not None:
        return _render_account_error(request, db, user, "این نام کاربری قبلاً ثبت شده", account)
    phone, phone_error = _parse_mobile(mobile)
    if phone_error:
        return _render_account_error(request, db, user, phone_error, account)
    try:
        # Empty input = keep the stored salary (the form never shows it).
        if to_latin_digits(salary_toman or "").strip() == "":
            salary = Decimal(user.salary_toman or 0)
        else:
            salary = parse_decimal(salary_toman, field="حقوق ماهانه")
    except Exception as exc:
        return _render_account_error(
            request,
            db,
            user,
            str(getattr(exc, "detail", None) or "حقوق ماهانه نامعتبر است"),
            account,
        )
    password_change = new_password != ""
    username_change = name != user.username
    if password_change or username_change:
        if not verify_password(current_password, user.password_hash):
            return _render_account_error(request, db, user, "رمز فعلی نادرست است", account)
    if password_change:
        password_error = validate_password(new_password)
        if password_error:
            return _render_account_error(request, db, user, password_error, account)
        user.password_hash = hash_password(new_password)
    user.full_name = account["full_name"]
    user.username = name
    user.mobile = phone or ""
    user.salary_toman = salary
    db.commit()
    flash(request, "حساب ذخیره شد")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile")
async def profile_save(
    request: Request,
    background_tasks: BackgroundTasks,
    gold_grams: str = Form("0"),
    coin_emami: str = Form("0"),
    coin_bahar: str = Form("0"),
    coin_half: str = Form("0"),
    coin_quarter: str = Form("0"),
    coin_gram: str = Form("0"),
    silver_grams: str = Form("0"),
    btc: str = Form("0"),
    ada: str = Form("0"),
    eth: str = Form("0"),
    sol: str = Form("0"),
    doge: str = Form("0"),
    matic: str = Form("0"),
    usd: str = Form("0"),
    cash_toman: str = Form("0"),
    sanjeh_token: str = Form(""),
    clear_sanjeh: str = Form(""),
    next_url: str = Form("", alias="next"),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    form = {
        "gold_grams": gold_grams,
        "coin_emami": coin_emami,
        "coin_bahar": coin_bahar,
        "coin_half": coin_half,
        "coin_quarter": coin_quarter,
        "coin_gram": coin_gram,
        "silver_grams": silver_grams,
        "btc": btc,
        "ada": ada,
        "eth": eth,
        "sol": sol,
        "doge": doge,
        "matic": matic,
        "usd": usd,
        "cash_toman": cash_toman,
        "sanjeh_token": "",
    }
    # Assets v2: validate every field first and collect {field: message}; nothing is assigned or committed
    # unless all of them are valid. A form post still gets the HTML page (now with inline errors);
    # a fetch() with Accept: application/json gets 422 {"ok": false, "error", "fields", "reasons"}.
    wants_json = "application/json" in (request.headers.get("accept") or "")
    reasons: dict[str, str] = {}
    for name in HOLDING_FORM_FIELDS:
        reason = quantity_error(form[name], 2 if name == "cash_toman" else 8)
        if reason:
            reasons[name] = reason
    if reasons:
        from app.assets_page import render_assets

        summary = "یکی از مقادیر وارد شده نامعتبر است"
        fields = {k: field_error_message(r, 2 if k == "cash_toman" else 8) for k, r in reasons.items()}
        if wants_json:
            return JSONResponse({"ok": False, "error": summary, "fields": fields, "reasons": reasons}, status_code=422)
        return render_assets(request, db, user, form=form, error=summary, field_errors=fields,
                             field_short={k: FIELD_ERROR_SHORT_FA[r] for k, r in reasons.items()})
    for name in HOLDING_FORM_FIELDS:
        setattr(user, name, parse_decimal(form[name], field=name))
    if clear_sanjeh == "1":
        user.sanjeh_token = None
        user.car_toman = Decimal("0")
        user.car_count = 0
        user.car_fetched_at = None
    elif sanjeh_token.strip():
        user.sanjeh_token = sanjeh_token.strip()
    sanjeh_warning = None
    if user.sanjeh_token:
        try:
            await refresh_user_sanjeh_car(user)
        except SanjehAuthError:
            sanjeh_warning = "دارایی‌ها ذخیره شد، ولی توکن سنجه نامعتبر است و قیمت خودرو به‌روز نشد."
        except Exception:
            logger.exception("Sanjeh fetch failed on profile save")
            sanjeh_warning = "دارایی‌ها ذخیره شد، ولی قیمت خودرو از سنجه گرفته نشد. بعداً دوباره تلاش کنید."
    db.commit()
    # Don't hold the redirect on chande.net (up to 20s): the next page renders with stored prices
    # (home v2 shows the stale/waiting line) and the fetch + snapshot run after the response is sent.
    background_tasks.add_task(refresh_prices_and_snapshot_user, user.id)
    # Only where we go next differs: the Assets page asks to come back to itself (exact internal path only).
    if next_url == "/assets":
        flash(request, sanjeh_warning or "ذخیره شد")
        if wants_json:
            return JSONResponse({"ok": True, "redirect": "/assets"})
        return RedirectResponse("/assets", status_code=303)
    flash(request, sanjeh_warning or "موجودی ذخیره شد")
    return RedirectResponse("/dashboard", status_code=303)


HOLDING_FORM_FIELDS = (
    "gold_grams", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram", "silver_grams",
    "btc", "ada", "eth", "sol", "doge", "matic", "usd", "cash_toman",
)


def holdings_form(user: User) -> dict[str, str]:
    return {
        "gold_grams": format_qty_input(Decimal(user.gold_grams or 0), 4),
        "coin_emami": format_qty_input(Decimal(user.coin_emami or 0), 2),
        "coin_bahar": format_qty_input(Decimal(user.coin_bahar or 0), 2),
        "coin_half": format_qty_input(Decimal(user.coin_half or 0), 2),
        "coin_quarter": format_qty_input(Decimal(user.coin_quarter or 0), 2),
        "coin_gram": format_qty_input(Decimal(user.coin_gram or 0), 2),
        "silver_grams": format_qty_input(Decimal(user.silver_grams or 0), 4),
        "btc": format_qty_input(Decimal(user.btc or 0), 8),
        "ada": format_qty_input(Decimal(user.ada or 0), 4),
        "eth": format_qty_input(Decimal(user.eth or 0), 8),
        "sol": format_qty_input(Decimal(user.sol or 0), 4),
        "doge": format_qty_input(Decimal(user.doge or 0), 4),
        "matic": format_qty_input(Decimal(user.matic or 0), 4),
        "usd": format_qty_input(Decimal(user.usd or 0), 2),
        "cash_toman": format_amount_input(Decimal(user.cash_toman or 0)),
    }


@router.get("/api/salary")
def salary_reveal(request: Request, db: Session = Depends(get_db)):
    """Salary and مانده for the signed-in user only, fetched when the eye button is tapped."""
    no_store = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Cookie"}
    user = get_authenticated_user(request, db)
    if user is None:
        return JSONResponse({"error": "login"}, status_code=401, headers=no_store)
    from app.expenses import monthly_view

    monthly = monthly_view(db, user)
    return JSONResponse(
        {"salary": monthly["income_month_label"], "left": monthly["monthly_left_label"]},
        headers=no_store,
    )
