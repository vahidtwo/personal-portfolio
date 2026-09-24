"""Profile holdings, account, and MCP token."""

from __future__ import annotations

import json
import logging
import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.debts import debt_rows
from app.expenses import expense_form_for_request
from app.formatting import format_qty, format_toman, format_when
from app.jobs import refresh_prices_and_snapshot_user, refresh_user_sanjeh_car
from app.mcp_http import hash_mcp_token
from app.models import Debt, User, utcnow
from app.sanjeh import SanjehAuthError
from app.security import (
    get_current_user,
    hash_password,
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
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    tab = request.query_params.get("tab", "assets")
    if tab not in ("assets", "debts"):
        tab = "assets"
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
    if mcp_token:
        mcp_url = str(request.base_url).rstrip("/") + "/mcp"
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
        error=None,
        flash=flash_message,
        flash_error=flash_error,
        form=holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab=tab,
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
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    raw = secrets.token_urlsafe(32)
    user.mcp_token_hash = hash_mcp_token(raw)
    db.commit()
    request.session["mcp_token_once"] = raw
    flash(request, "توکن MCP ساخته شد. همین حالا کپی کنید.")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/mcp-token/revoke")
async def revoke_mcp_token(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    user.mcp_token_hash = None
    db.commit()
    flash(request, "توکن MCP حذف شد.")
    return RedirectResponse("/profile", status_code=303)
def _account_form(user: User, **overrides: str) -> dict[str, str]:
    salary = Decimal(getattr(user, "salary_toman", 0) or 0)
    text = format(salary, "f").rstrip("0").rstrip(".")
    data = {
        "full_name": user.full_name or "",
        "username": user.username,
        "mobile": user.mobile or "",
        "salary_toman": text,
    }
    data.update(overrides)
    return data


def _parse_mobile(raw: str) -> tuple[str | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
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
        tab="assets",
        account=account,
        account_error=message,
    )


@router.post("/profile/account")
async def profile_account(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    mobile: str = Form(""),
    salary_toman: str = Form("0"),
    current_password: str = Form(""),
    new_password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    account = {
        "full_name": full_name.strip()[:80],
        "username": username,
        "mobile": mobile,
        "salary_toman": salary_toman,
    }
    name = normalize_username(username)
    name_error = validate_username(name)
    if name_error:
        return _render_account_error(request, db, user, name_error, account)
    taken = db.query(User).filter(User.username == name, User.id != user.id).first()
    if taken is not None:
        return _render_account_error(request, db, user, "این نام کاربری قبلاً ثبت شده", account)
    phone, phone_error = _parse_mobile(mobile)
    if phone_error:
        return _render_account_error(request, db, user, phone_error, account)
    try:
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
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
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
    try:
        user.gold_grams = parse_decimal(gold_grams, field="gold")
        user.coin_emami = parse_decimal(coin_emami, field="coin_emami")
        user.coin_bahar = parse_decimal(coin_bahar, field="coin_bahar")
        user.coin_half = parse_decimal(coin_half, field="coin_half")
        user.coin_quarter = parse_decimal(coin_quarter, field="coin_quarter")
        user.coin_gram = parse_decimal(coin_gram, field="coin_gram")
        user.silver_grams = parse_decimal(silver_grams, field="silver")
        user.btc = parse_decimal(btc, field="btc")
        user.ada = parse_decimal(ada, field="ada")
        user.eth = parse_decimal(eth, field="eth")
        user.sol = parse_decimal(sol, field="sol")
        user.doge = parse_decimal(doge, field="doge")
        user.matic = parse_decimal(matic, field="matic")
        user.usd = parse_decimal(usd, field="usd")
        user.cash_toman = parse_decimal(cash_toman, field="cash")
    except Exception:
        return render(
            request,
            "profile.html",
            db,
            error="یکی از مقادیر وارد شده نامعتبر است",
            flash=None,
            form=form,
            account=_account_form(user),
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        )
    if clear_sanjeh == "1":
        user.sanjeh_token = None
        user.car_toman = Decimal("0")
        user.car_count = 0
        user.car_fetched_at = None
    elif sanjeh_token.strip():
        user.sanjeh_token = sanjeh_token.strip()
    if user.sanjeh_token:
        try:
            await refresh_user_sanjeh_car(user)
        except SanjehAuthError:
            return render(
                request,
                "profile.html",
                db,
                error="توکن سنجه نامعتبر است. در sanjeh.app پروفایل را تکمیل کنید و توکن درست را وارد کنید.",
                flash=None,
                form=form,
            account=_account_form(user),
                has_sanjeh_token=bool(user.sanjeh_token),
                car_fetched_label=format_when(user.car_fetched_at),
                car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            )
        except Exception:
            logger.exception("Sanjeh fetch failed on profile save")
            return render(
                request,
                "profile.html",
                db,
                error="دریافت قیمت خودرو از سنجه ممکن نشد. بعداً دوباره تلاش کنید.",
                flash=None,
                form=form,
            account=_account_form(user),
                has_sanjeh_token=bool(user.sanjeh_token),
                car_fetched_label=format_when(user.car_fetched_at),
                car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            )
    db.commit()
    await refresh_prices_and_snapshot_user(user.id)
    flash(request, "موجودی ذخیره شد")
    return RedirectResponse("/dashboard", status_code=303)


def holdings_form(user: User) -> dict[str, str]:
    return {
        "gold_grams": format_qty(Decimal(user.gold_grams or 0), 4),
        "coin_emami": format_qty(Decimal(user.coin_emami or 0), 2),
        "coin_bahar": format_qty(Decimal(user.coin_bahar or 0), 2),
        "coin_half": format_qty(Decimal(user.coin_half or 0), 2),
        "coin_quarter": format_qty(Decimal(user.coin_quarter or 0), 2),
        "coin_gram": format_qty(Decimal(user.coin_gram or 0), 2),
        "silver_grams": format_qty(Decimal(user.silver_grams or 0), 4),
        "btc": format_qty(Decimal(user.btc or 0), 8),
        "ada": format_qty(Decimal(user.ada or 0), 4),
        "eth": format_qty(Decimal(user.eth or 0), 8),
        "sol": format_qty(Decimal(user.sol or 0), 4),
        "doge": format_qty(Decimal(user.doge or 0), 4),
        "matic": format_qty(Decimal(user.matic or 0), 4),
        "usd": format_qty(Decimal(user.usd or 0), 2),
        "cash_toman": format_qty(Decimal(user.cash_toman or 0), 0),
    }
