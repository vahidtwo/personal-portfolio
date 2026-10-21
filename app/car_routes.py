"""Car (Sanjeh) card v2 on /assets: connect, refresh, disconnect (+ short undo).

Every route takes CSRF, answers JSON when asked (Accept: application/json) and otherwise redirects back to
/assets (no-JS fallback). GET /assets never calls Sanjeh: only these POSTs and the background jobs do.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_number, format_toman
from app.jobs import refresh_user_sanjeh_car
from app.models import User, utcnow
from app.sanjeh import SanjehAuthError, fetch_sanjeh_portfolio
from app.security import csrf_token, get_authenticated_user, redirect_to_login, require_csrf
from app.web import flash, templates

logger = logging.getLogger(__name__)
router = APIRouter()

REFRESH_COOLDOWN_S = 300  # after a SUCCESSFUL refresh: ~1 manual refresh per 5 minutes
RETRY_COOLDOWN_S = 30  # after a failed refresh: «دوباره امتحان کنید» works again soon
UNDO_WINDOW_S = 10
_next_refresh_at: dict[int, float] = {}  # user id -> monotonic time the next manual refresh is allowed
# single uvicorn worker (Dockerfile --workers 1): undo lives in memory for 10 s, never in the cookie
_pending_undo: dict[int, tuple[float, dict]] = {}

ERR_REJECTED = "سنجه این توکن را نپذیرفت. دوباره از سنجه کپی کنید."
ERR_EMPTY = "توکن API سنجه را بچسبانید."
ERR_FAILED = "سنجه فعلاً پاسخ نمی‌دهد. کمی بعد دوباره امتحان کنید."
ERR_TOO_SOON = "قیمت همین چند دقیقه پیش گرفته شد. کمی بعد دوباره امتحان کنید."
TOAST_DISCONNECTED = "اتصال سنجه قطع شد."
FLASH_CONNECTED = "به سنجه وصل شد."
FLASH_UNDONE = "اتصال سنجه برگردانده شد."


def _ago(dt) -> str | None:  # None -> template shows «نامشخص»
    from datetime import timezone

    from app.dashboard import age_label_fa

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    label = age_label_fa(utcnow() - dt)
    return "لحظاتی پیش" if label == "لحظاتی" else f"{label} پیش"


def car_state(user: User) -> str:
    if not user.sanjeh_token:
        return "none"
    if user.sanjeh_status == "rejected":
        return "rejected"
    if user.sanjeh_status == "failed":
        return "fetchfail"
    return "connected"  # 'ok' or NULL (rows from before migration 0004)


def undo_available(user_id: int) -> bool:
    item = _pending_undo.get(user_id)
    if item and item[0] > time.monotonic():
        return True
    _pending_undo.pop(user_id, None)
    return False


def car_context(user: User) -> dict:
    value = Decimal(user.car_toman or 0)
    count = int(user.car_count or 0)
    return {
        "car_state": car_state(user),
        "car_value_label": format_toman(value) if user.sanjeh_token else None,
        "car_count_label": format_number(count, 0) if user.sanjeh_token else None,
        "car_ago": _ago(user.car_fetched_at),
        "car_undo": undo_available(user.id),
    }


def _wants_json(request: Request) -> bool:
    return "application/json" in (request.headers.get("accept") or "")


def _card_html(request: Request, user: User) -> str:
    tpl = templates.get_template("partials/car_card.html")
    return tpl.render(csrf=csrf_token(request), **car_context(user))


def _ok(request: Request, user: User, message: str | None = None):
    if _wants_json(request):
        return JSONResponse({"ok": True, "state": car_state(user), "html": _card_html(request, user),
                             "message": message})
    if message:
        flash(request, message)
    return RedirectResponse("/assets#group-car", status_code=303)


def _fail(request: Request, user: User, error: str, message: str, *, status: int, sheet: str | None = None):
    if _wants_json(request):
        return JSONResponse({"ok": False, "error": error, "message": message, "state": car_state(user),
                             "html": _card_html(request, user)}, status_code=status)
    if sheet:
        return RedirectResponse(f"/assets?car={sheet}&err={error}#car-sheet", status_code=303)
    flash(request, message, error=True)
    return RedirectResponse("/assets#group-car", status_code=303)


@router.post("/assets/car/connect")
async def car_connect(request: Request, csrf: str = Form(""), token: str = Form(""), db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    token = token.strip()
    sheet = "replace" if user.sanjeh_token else "connect"
    if not token or len(token) > 128:
        return _fail(request, user, "empty" if not token else "rejected", ERR_EMPTY if not token else ERR_REJECTED,
                     status=422, sheet=sheet)
    # validate with Sanjeh BEFORE saving: a rejected/failed token never replaces the old one
    try:
        portfolio = await fetch_sanjeh_portfolio(token)
    except SanjehAuthError:
        return _fail(request, user, "rejected", ERR_REJECTED, status=422, sheet=sheet)
    except Exception:
        logger.exception("Sanjeh connect check failed for user %s", user.id)
        return _fail(request, user, "failed", ERR_FAILED, status=502, sheet=sheet)
    user.sanjeh_token = token
    user.car_toman = portfolio.total_toman
    user.car_count = portfolio.car_count
    user.car_fetched_at = utcnow()
    user.sanjeh_status = "ok"
    db.commit()
    _pending_undo.pop(user.id, None)
    _next_refresh_at[user.id] = time.monotonic() + REFRESH_COOLDOWN_S  # just fetched successfully
    return _ok(request, user, FLASH_CONNECTED)


@router.post("/assets/car/refresh")
async def car_refresh(request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    if not user.sanjeh_token:
        return _ok(request, user)
    if time.monotonic() < _next_refresh_at.get(user.id, 0.0):
        return _fail(request, user, "too_soon", ERR_TOO_SOON, status=429)
    # short guard while this attempt runs/after it fails; the 5-minute cooldown starts only on success
    _next_refresh_at[user.id] = time.monotonic() + RETRY_COOLDOWN_S
    try:
        await refresh_user_sanjeh_car(user)
    except SanjehAuthError:
        db.commit()  # sanjeh_status = rejected; old value kept
        return _fail(request, user, "rejected", ERR_REJECTED, status=200)
    except Exception:
        logger.exception("Sanjeh manual refresh failed for user %s", user.id)
        db.commit()  # sanjeh_status = failed; old value kept
        return _fail(request, user, "failed", ERR_FAILED, status=200)
    _next_refresh_at[user.id] = time.monotonic() + REFRESH_COOLDOWN_S
    db.commit()
    return _ok(request, user)


@router.post("/assets/car/disconnect")
async def car_disconnect(request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    if user.sanjeh_token:
        _pending_undo[user.id] = (time.monotonic() + UNDO_WINDOW_S, {
            "sanjeh_token": user.sanjeh_token, "car_toman": user.car_toman, "car_count": user.car_count,
            "car_fetched_at": user.car_fetched_at, "sanjeh_status": user.sanjeh_status,
        })
    user.sanjeh_token = None
    user.car_toman = Decimal("0")
    user.car_count = 0
    user.car_fetched_at = None
    user.sanjeh_status = None
    db.commit()
    if _wants_json(request):
        return _ok(request, user, TOAST_DISCONNECTED)
    return RedirectResponse("/assets#group-car", status_code=303)  # the toast (with undo) renders server-side


@router.post("/assets/car/undo")
async def car_undo(request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    require_csrf(request, csrf)
    item = _pending_undo.pop(user.id, None)
    if not item or item[0] <= time.monotonic() or user.sanjeh_token:
        return _fail(request, user, "expired", "دیگر نمی‌شود برگرداند؛ دوباره وصل شوید.", status=410)
    for key, val in item[1].items():
        setattr(user, key, val)
    db.commit()
    return _ok(request, user, FLASH_UNDONE)
