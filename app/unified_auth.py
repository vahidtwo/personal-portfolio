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

import math
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import rate_limit, security
from app.db import get_db
from app.formatting import persian_digits
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
GENERIC_HELP = "رمز را دوباره بنویسید. حروف بزرگ و کوچک فرق دارند."
USERNAME_ERROR = "نام کاربری باید با حرف انگلیسی شروع شود و ۳ تا ۳۲ حرف باشد."
SHORT_PASSWORD_ERROR = "برای حساب تازه، رمز دست‌کم ۸ حرف باشد."
RATE_LIMIT_ERROR = "چند بار پشت سر هم اشتباه شد."
RATE_LIMIT_HELP = "برای امنیت، ورود شما تا حدود {n} دقیقهٔ دیگر بسته است."
MISMATCH_ERROR = "دو رمز یکی نیستند."
MISMATCH_HELP = "رمز را یک بار دیگر بنویسید، یا برگردید و از اول بنویسید."
SIGNUP_LIMIT_ERROR = "از این شبکه حساب زیادی ساخته شده."
SIGNUP_LIMIT_HELP = "حدود {n} دقیقهٔ دیگر دوباره امتحان کنید. اگر حساب دارید، نام کاربری را بررسی کنید."
EXPIRED_ERROR = "زمان ساخت حساب تمام شد."
EXPIRED_HELP = "برای امنیت، نام کاربری و رمز را دوباره بنویسید."
TAKEN_ERROR = "این نام کاربری همین حالا گرفته شد. نام دیگری بنویسید."

# Same cost as real hashes (rounds=12), so an unknown username takes as long as a wrong password.
_DUMMY_HASH = hash_password("dummy-password-for-equal-timing")


def _minutes(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))


def _page(request: Request, db: Session, *, step: str = "a", username: str = "", error: str | None = None,
          alert_sub: str | None = None, alert_kind: str = "danger", username_error: str | None = None,
          password_error: str | None = None, password_invalid: bool = False, focus: str | None = None,
          retry_seconds: int = 0, status_code: int = 200) -> HTMLResponse:
    """Render /auth. Field-level problems go inline (`username_error`, `password_error`); the alert is only for
    wrong credentials, rate limits and an expired sign-up. `focus` is username|password|confirm|alert."""
    if focus is None:
        if error:
            focus = "alert" if alert_kind == "warn" else ("confirm" if step == "b" else "password")
        else:
            focus = "confirm" if step == "b" else ("username" if not username or username_error else "password")
    if username_error:
        focus = "username"
    elif password_error:
        focus = "password"
    minutes = _minutes(retry_seconds) if retry_seconds else 0
    response = render(
        request, "auth.html", db, step=step, username=username, error=error, alert_sub=alert_sub,
        alert_kind=alert_kind, username_error=username_error, password_error=password_error,
        password_invalid=password_invalid, focus=focus, retry_seconds=retry_seconds,
        minutes_fa=persian_digits(str(minutes)) if minutes else "",
    )
    response.status_code = status_code
    if status_code == 429 and retry_seconds:
        response.headers["Retry-After"] = str(retry_seconds)
    return response


def _rate_limited_page(request: Request, db: Session, *, username: str, seconds: int) -> HTMLResponse:
    return _page(request, db, username=username, error=RATE_LIMIT_ERROR,
                 alert_sub=RATE_LIMIT_HELP.format(n=persian_digits(str(_minutes(seconds)))), alert_kind="warn",
                 retry_seconds=seconds, status_code=429)


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
    locked = max(
        rate_limit.retry_after(user_key, rate_limit.LOGIN_FAILS_PER_USER, window),
        rate_limit.retry_after(ip_key, rate_limit.LOGIN_FAILS_PER_IP, window),
    )
    if locked:
        return _rate_limited_page(request, db, username=username, seconds=locked)
    if validate_username(username):
        verify_password(password or "x", _DUMMY_HASH)
        return _page(request, db, username=username, username_error=USERNAME_ERROR)
    if not password:
        verify_password("x", _DUMMY_HASH)
        return _page(request, db, username=username, error=GENERIC_ERROR, alert_sub=GENERIC_HELP,
                     password_invalid=True, focus="password")
    user = db.query(User).filter(User.username == username).first()
    if user is not None:
        if not verify_password(password, user.password_hash):
            rate_limit.record(user_key, window, rate_limit.LOGIN_FAILS_PER_USER)
            rate_limit.record(ip_key, window, rate_limit.LOGIN_FAILS_PER_IP)
            return _page(request, db, username=username, error=GENERIC_ERROR, alert_sub=GENERIC_HELP,
                         password_invalid=True, focus="password")
        rate_limit.clear(user_key)
        rate_limit.clear(ip_key)
        user.last_login_at = utcnow()
        db.commit()
        request.session["user_id"] = user.id
        return RedirectResponse("/dashboard", status_code=303)
    # Unknown username: equal timing, then step b. Nothing is created yet.
    verify_password(password, _DUMMY_HASH)
    if validate_password(password):
        return _page(request, db, username=username, password_error=SHORT_PASSWORD_ERROR)
    if username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        return _page(request, db, username=username, username_error=security.ADMIN_NAME_ERROR)
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
    stale = request.session.get(PENDING_KEY)
    pending = _pending(request)
    if pending is None:
        # Expired (or no) sign-up: refill the username so only the password has to be typed again.
        name = stale.get("u", "") if isinstance(stale, dict) else ""
        request.session.pop(PENDING_KEY, None)
        return _page(request, db, username=name if isinstance(name, str) else "", error=EXPIRED_ERROR,
                     alert_sub=EXPIRED_HELP, focus="username")
    username = pending["u"]
    if not verify_password(password_confirm, pending["h"]):
        return _page(request, db, step="b", username=username, error=MISMATCH_ERROR, alert_sub=MISMATCH_HELP,
                     focus="confirm")
    ip_key = f"register:ip:{rate_limit.client_ip(request)}"
    locked = rate_limit.retry_after(ip_key, rate_limit.REGISTER_PER_IP, rate_limit.REGISTER_WINDOW_SECONDS)
    if locked:
        return _page(request, db, step="b", username=username, error=SIGNUP_LIMIT_ERROR,
                     alert_sub=SIGNUP_LIMIT_HELP.format(n=persian_digits(str(_minutes(locked)))),
                     alert_kind="warn", retry_seconds=locked, status_code=429)
    if db.query(User).filter(User.username == username).first():
        # Someone took the name in the meantime: back to step a, generic wording.
        request.session.pop(PENDING_KEY, None)
        return _page(request, db, username=username, username_error=TAKEN_ERROR)
    if username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        request.session.pop(PENDING_KEY, None)
        return _page(request, db, username=username, username_error=security.ADMIN_NAME_ERROR)
    user = User(username=username, password_hash=pending["h"], last_login_at=utcnow())
    db.add(user)
    db.commit()
    rate_limit.record(ip_key, rate_limit.REGISTER_WINDOW_SECONDS)
    request.session.pop(PENDING_KEY, None)
    request.session["user_id"] = user.id
    flash(request, "حساب شما ساخته شد. دارایی‌هایتان را در صفحهٔ دارایی‌ها وارد کنید.")
    return RedirectResponse("/assets", status_code=303)
