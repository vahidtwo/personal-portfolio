"""JSON API for the native Android login and home screens (Phase 4).

Same rules as the HTML flow in unified_auth.py: one generic wrong-credentials answer, nothing created before
step b, the same in-memory lockout buckets and the same signed `inventory_session` cookie. CSRF is a token bound
to the session (`GET /api/auth/csrf`) sent back in the `X-CSRF-Token` header. `/api/home` never carries salary.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import rate_limit, security
from app import dashboard as dash
from app import unified_auth as ua
from app.db import get_db
from app.debts import debt_rows
from app.formatting import format_toman, format_usd, format_share_label, format_qty, tehran_today
from app.models import Debt, PortfolioSnapshot, User, utcnow
from app.portfolio import ASSET_LABEL_FA, ASSET_META, build_portfolio, load_prices
from app.security import (
    attach_session_cookie_deletion,
    csrf_token,
    get_authenticated_user,
    hash_password,
    invalidate_session,
    normalize_username,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)

router = APIRouter(prefix="/api")

NO_STORE = {"Cache-Control": "no-store"}


def _json(data: dict, status_code: int = 200, retry_after: int = 0) -> JSONResponse:
    headers = dict(NO_STORE)
    if retry_after:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(data, status_code=status_code, headers=headers)


def _result(result: str, *, username: str = "", focus: str = "", retry_after: int = 0, status_code: int = 200,
            message: str = "", sub: str = "") -> JSONResponse:
    body = {"result": result, "username": username, "focus": focus, "retry_after": retry_after,
            "message": message, "sub": sub}
    return _json(body, status_code=status_code, retry_after=retry_after)


def _check_csrf(request: Request) -> None:
    require_csrf(request, request.headers.get("x-csrf-token"))


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/auth/csrf")
async def api_csrf(request: Request):
    return _json({"csrf": csrf_token(request)})


@router.get("/auth/session")
async def api_session(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return _json({"signed_in": False}, status_code=401)
    return _json({"signed_in": True, "username": user.username})


@router.post("/auth/continue")
async def api_continue(request: Request, db: Session = Depends(get_db)):
    _check_csrf(request)
    data = await _body(request)
    request.session.pop(ua.PENDING_KEY, None)
    username = normalize_username(str(data.get("username") or ""))
    password = str(data.get("password") or "")
    ip = rate_limit.client_ip(request)
    user_key = f"login:user:{username}:{ip}"
    ip_key = f"login:ip:{ip}"
    window = rate_limit.LOGIN_WINDOW_SECONDS
    locked = max(
        rate_limit.retry_after(user_key, rate_limit.LOGIN_FAILS_PER_USER, window),
        rate_limit.retry_after(ip_key, rate_limit.LOGIN_FAILS_PER_IP, window),
    )
    if locked:
        return _result("locked", username=username, focus="alert", retry_after=locked, status_code=429,
                       message=ua.RATE_LIMIT_ERROR,
                       sub=ua.RATE_LIMIT_HELP.format(n=ua.persian_digits(str(ua._minutes(locked)))))
    if validate_username(username):
        verify_password(password or "x", ua._DUMMY_HASH)
        return _result("badname", username=username, focus="username", message=ua.USERNAME_ERROR)
    if not password:
        verify_password("x", ua._DUMMY_HASH)
        return _result("wrong", username=username, focus="password", message=ua.GENERIC_ERROR, sub=ua.GENERIC_HELP)
    user = db.query(User).filter(User.username == username).first()
    if user is not None:
        if not verify_password(password, user.password_hash):
            rate_limit.record(user_key, window, rate_limit.LOGIN_FAILS_PER_USER)
            rate_limit.record(ip_key, window, rate_limit.LOGIN_FAILS_PER_IP)
            return _result("wrong", username=username, focus="password", message=ua.GENERIC_ERROR,
                           sub=ua.GENERIC_HELP)
        rate_limit.clear(user_key)
        rate_limit.clear(ip_key)
        user.last_login_at = utcnow()
        db.commit()
        request.session["user_id"] = user.id
        return _result("ok", username=user.username)
    verify_password(password, ua._DUMMY_HASH)
    if validate_password(password):
        return _result("shortpw", username=username, focus="password", message=ua.SHORT_PASSWORD_ERROR)
    if username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        return _result("badname", username=username, focus="username", message=security.ADMIN_NAME_ERROR)
    request.session[ua.PENDING_KEY] = {"u": username, "h": hash_password(password), "t": ua._now()}
    return _result("stepb", username=username, focus="confirm")


@router.post("/auth/create")
async def api_create(request: Request, db: Session = Depends(get_db)):
    _check_csrf(request)
    data = await _body(request)
    confirm = str(data.get("password_confirm") or "")
    stale = request.session.get(ua.PENDING_KEY)
    pending = ua._pending(request)
    if pending is None:
        name = stale.get("u", "") if isinstance(stale, dict) else ""
        request.session.pop(ua.PENDING_KEY, None)
        return _result("expired", username=name if isinstance(name, str) else "", focus="username",
                       message=ua.EXPIRED_ERROR, sub=ua.EXPIRED_HELP)
    username = pending["u"]
    if not verify_password(confirm, pending["h"]):
        return _result("mismatch", username=username, focus="confirm", message=ua.MISMATCH_ERROR,
                       sub=ua.MISMATCH_HELP)
    ip_key = f"register:ip:{rate_limit.client_ip(request)}"
    locked = rate_limit.retry_after(ip_key, rate_limit.REGISTER_PER_IP, rate_limit.REGISTER_WINDOW_SECONDS)
    if locked:
        return _result("signuplimit", username=username, focus="alert", retry_after=locked, status_code=429,
                       message=ua.SIGNUP_LIMIT_ERROR,
                       sub=ua.SIGNUP_LIMIT_HELP.format(n=ua.persian_digits(str(ua._minutes(locked)))))
    if db.query(User).filter(User.username == username).first() or (
        username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None
    ):
        request.session.pop(ua.PENDING_KEY, None)
        return _result("taken", username=username, focus="username", message=ua.TAKEN_ERROR)
    user = User(username=username, password_hash=pending["h"], last_login_at=utcnow())
    db.add(user)
    db.commit()
    rate_limit.record(ip_key, rate_limit.REGISTER_WINDOW_SECONDS)
    request.session.pop(ua.PENDING_KEY, None)
    request.session["user_id"] = user.id
    return _result("ok", username=user.username)


@router.post("/auth/logout")
async def api_logout(request: Request):
    _check_csrf(request)
    invalidate_session(request)
    response = _json({"result": "ok"})
    response.headers["Clear-Site-Data"] = '"cache"'
    return attach_session_cookie_deletion(response)


def _s(value) -> str | None:
    return None if value is None else str(value)


@router.get("/home")
async def api_home(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return _json({"error": "login required"}, status_code=401)
    prices = load_prices(db)
    view = build_portfolio(user, prices)
    now = utcnow()
    total = view.total_toman if view.total_toman > 0 else Decimal("1")
    debts = db.query(Debt).filter(Debt.user_id == user.id).all()
    _debt_list, debt_total, _next = debt_rows(debts)
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.taken_at >= now - dash.CHANGE_LOOKBACK - timedelta(days=1))
        .all()
    )
    changes = dash.net_worth_changes(snaps, view, debt_total, now)
    week_prices = dash.snapshot_unit_prices(
        dash.reference_snapshot(snaps, now, dash.CHANGE_WINDOWS[1][1], dash.CHANGE_WINDOWS[1][2])
    )
    trends = dash.build_week_asset_trends(snaps, view, now)
    usd_row = next((r for r in view.rows if r.key == "usd"), None)
    usd_price = usd_row.unit_price if usd_row is not None else None
    rows = []
    for row in [r for r in view.rows if r.value_toman > 0 or r.quantity > 0]:
        share = (row.value_toman / total * Decimal("100")).quantize(Decimal("0.1"))
        chip, _sort = dash.asset_week_change(row, week_prices)
        places = ASSET_META[row.key]["qty_places"]
        qty = (format_usd(row.quantity, fixed=True) if row.key == "usd"
               else format_qty(row.quantity, places if row.key not in ("car", "cash") else 0))
        spark = dash.sparkline(row.key, row.name_fa, trends.get(row.key, []), chip, 72)
        rows.append({
            "key": row.key, "name_fa": row.name_fa,
            "quantity_label": qty, "unit_fa": "دلار" if row.key == "usd" else row.unit_fa,
            "value_label": format_toman(row.value_toman), "share_label": format_share_label(share),
            "share": float(share), "chip": chip, "has_price": row.unit_price is not None,
            "spark": {"points": trends.get(row.key, []), "kind": spark["kind"], "label": spark["label"]} if spark else None,
        })
    if usd_price is not None and usd_price > 0:
        usd_label = dash._format_usd(view.total_toman / usd_price)
        usd_points = dash.week_usd_series(snaps, usd_price, view.total_toman, now)
        usd_spark = dash.usd_sparkline(usd_points)
        usd_spark = {"points": usd_points, "kind": usd_spark["kind"], "label": usd_spark["label"]} if usd_spark else None
    else:
        usd_label, usd_spark = "—", None
    today = tehran_today()
    windows = [{"key": w["key"], "period": w["period"], "kind": w["kind"], "label": w["label"]}
               for w in changes["windows"]]
    price = dash.price_status(view.prices_fetched_at, now)
    return _json({
        "username": user.username,
        "net": {"label": format_toman(view.total_toman - debt_total), "big": dash.big_toman(view.total_toman - debt_total)},
        "assets_total": {"label": format_toman(view.total_toman), "big": dash.big_toman(view.total_toman)},
        "debt_total": {"label": format_toman(debt_total), "big": dash.big_toman(debt_total), "has": debt_total != 0},
        "usd": {"label": usd_label, "spark": usd_spark},
        "changes": windows,
        "price": price,
        "missing": [ASSET_LABEL_FA.get(k, k) for k in view.missing_prices],
        "next_instalment": dash.next_instalment(debts, today),
        "month_spend": dash.month_spend_tile(db, user, today),
        "rows": rows,
        "empty": not rows and debt_total == 0,
        "generated_at": now.isoformat(),
    })
