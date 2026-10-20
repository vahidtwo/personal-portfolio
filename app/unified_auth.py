"""Phase 3 unified sign-in: one form for log in and sign up (spec /workspace/mockups/phase3/spec.md §6, §10).

Step a: POST /auth/continue {username, password}
  - existing user + right password -> log in -> /dashboard
  - existing user + wrong password -> generic «نام کاربری یا رمز درست نیست.» (nothing says which field)
  - unknown username (+ valid password) -> step b, after a dummy bcrypt so timing matches a real check
Step b: POST /auth/create {password_confirm}
  - nothing is created before this step. The pending sign-up (username + a bcrypt hash of the step-a
    password, never the password itself) lives in the signed session for 5 minutes, never in the URL.

Rate limits reuse the existing per-IP+username and per-IP login buckets and the per-IP sign-up bucket.
They are in memory: a container restart resets them (see README «Rate limits»).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import rate_limit, security
from app.db import get_db
from app.models import User, utcnow
from app.security import (
    hash_password,
    normalize_username,
    redirect_to_dashboard_if_authenticated,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)
from app.web import flash, render


def _now() -> float:
    """Wall clock for the pending sign-up TTL (patchable in tests)."""
    return time.time()

router = APIRouter()

PENDING_KEY = "pending_signup"
PENDING_TTL_SECONDS = 5 * 60
GENERIC_ERROR = "نام کاربری یا رمز درست نیست."
RATE_LIMIT_ERROR = "چند بار پشت سر هم اشتباه شد. چند دقیقه دیگر دوباره امتحان کنید."
MISMATCH_ERROR = "دو رمز یکی نیستند. دوباره بنویسید."
SIGNUP_LIMIT_ERROR = "تعداد ساخت حساب از این شبکه زیاد است. کمی بعد دوباره امتحان کنید."
EXPIRED_ERROR = "زمان ساخت حساب تمام شد. لطفاً دوباره نام کاربری و رمز را بنویسید."

# Same cost as real hashes (rounds=12), so an unknown username takes as long as a wrong password.
_DUMMY_HASH = hash_password("dummy-password-for-equal-timing")


def _page(request: Request, db: Session, *, step: str = "a", username: str = "", error: str | None = None,
          status_code: int = 200) -> HTMLResponse:
    response = render(request, "auth.html", db, step=step, username=username, error=error)
    response.status_code = status_code
    return response


def _pending(request: Request) -> dict | None:
    data = request.session.get(PENDING_KEY)
    if not isinstance(data, dict):
        return None
    if _now() - float(data.get("t", 0)) > PENDING_TTL_SECONDS:
        request.session.pop(PENDING_KEY, None)
        return None
    return data


@router.get("/auth", response_class=HTMLResponse)
async def auth_form(request: Request, back: str = "", db: Session = Depends(get_db)):
    if redirect := redirect_to_dashboard_if_authenticated(request, db):
        return redirect
    username = ""
    pending = _pending(request)
    if back and pending:
        username = pending.get("u", "")
    request.session.pop(PENDING_KEY, None)
    return _page(request, db, username=username)


@router.post("/auth/continue")
async def auth_continue(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    request.session.pop(PENDING_KEY, None)
    username = normalize_username(username)
    ip = rate_limit.client_ip(request)
    user_key = f"login:user:{username}:{ip}"
    ip_key = f"login:ip:{ip}"
    window = rate_limit.LOGIN_WINDOW_SECONDS
    if rate_limit.is_limited(user_key, rate_limit.LOGIN_FAILS_PER_USER, window) or rate_limit.is_limited(
        ip_key, rate_limit.LOGIN_FAILS_PER_IP, window
    ):
        return _page(request, db, username=username, error=RATE_LIMIT_ERROR, status_code=429)
    if validate_username(username) or not password:
        verify_password(password or "x", _DUMMY_HASH)
        return _page(request, db, username=username, error=validate_username(username) or GENERIC_ERROR)
    user = db.query(User).filter(User.username == username).first()
    if user is not None:
        if not verify_password(password, user.password_hash):
            rate_limit.record(user_key, window)
            rate_limit.record(ip_key, window)
            return _page(request, db, username=username, error=GENERIC_ERROR)
        rate_limit.clear(user_key)
        user.last_login_at = utcnow()
        db.commit()
        request.session["user_id"] = user.id
        return RedirectResponse("/dashboard", status_code=303)
    # Unknown username: equal timing, then step b. Nothing is created yet.
    verify_password(password, _DUMMY_HASH)
    error = validate_password(password)
    if not error and username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        error = security.ADMIN_NAME_ERROR
    if error:
        return _page(request, db, username=username, error=error)
    request.session[PENDING_KEY] = {"u": username, "h": hash_password(password), "t": _now()}
    return _page(request, db, step="b", username=username)


@router.post("/auth/create")
async def auth_create(
    request: Request,
    password_confirm: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    pending = _pending(request)
    if pending is None:
        return _page(request, db, error=EXPIRED_ERROR)
    username = pending["u"]
    if not verify_password(password_confirm, pending["h"]):
        return _page(request, db, step="b", username=username, error=MISMATCH_ERROR)
    ip_key = f"register:ip:{rate_limit.client_ip(request)}"
    if rate_limit.is_limited(ip_key, rate_limit.REGISTER_PER_IP, rate_limit.REGISTER_WINDOW_SECONDS):
        return _page(request, db, step="b", username=username, error=SIGNUP_LIMIT_ERROR, status_code=429)
    if db.query(User).filter(User.username == username).first():
        # Someone took the name in the meantime: back to step a, generic wording.
        request.session.pop(PENDING_KEY, None)
        return _page(request, db, username=username, error="این نام کاربری همین حالا گرفته شد. نام دیگری بنویسید.")
    if username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        request.session.pop(PENDING_KEY, None)
        return _page(request, db, username=username, error=security.ADMIN_NAME_ERROR)
    user = User(username=username, password_hash=pending["h"], last_login_at=utcnow())
    db.add(user)
    db.commit()
    rate_limit.record(ip_key, rate_limit.REGISTER_WINDOW_SECONDS)
    request.session.pop(PENDING_KEY, None)
    request.session["user_id"] = user.id
    flash(request, "حساب شما ساخته شد. دارایی‌هایتان را در صفحهٔ دارایی‌ها وارد کنید.")
    return RedirectResponse("/assets", status_code=303)
