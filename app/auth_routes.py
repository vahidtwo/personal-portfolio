"""Landing, register, login, and logout."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, utcnow
from app import rate_limit
from app import security
from app.security import (
    attach_session_cookie_deletion,
    get_authenticated_user,
    hash_password,
    invalidate_session,
    normalize_username,
    redirect_to_dashboard_if_authenticated,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)
from app.web import BASE_DIR, flash, render

router = APIRouter()

_APK_PATH = BASE_DIR / "static" / "my-inventory.apk"


def _apk_sha256() -> str | None:
    if not _APK_PATH.is_file():
        return None
    digest = hashlib.sha256()
    with _APK_PATH.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_to_dashboard_if_authenticated(request, db):
        return redirect
    return render(request, "landing.html", db, apk_sha256=_apk_sha256())


@router.head("/")
async def home_head():
    return Response(status_code=200, media_type="text/html")


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_to_dashboard_if_authenticated(request, db):
        return redirect
    return render(request, "register.html", db, error=None, form={"username": ""})


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    username = normalize_username(username)
    ip_key = f"register:ip:{rate_limit.client_ip(request)}"
    if rate_limit.is_limited(ip_key, rate_limit.REGISTER_PER_IP, rate_limit.REGISTER_WINDOW_SECONDS):
        return render(
            request,
            "register.html",
            db,
            error="تعداد ثبت‌نام زیاد است. کمی بعد دوباره تلاش کنید",
            form={"username": username},
        )
    error = validate_username(username) or validate_password(password)
    # Signing up with an admin name is only allowed to bootstrap an empty install.
    if not error and username in security.ADMIN_USERNAMES and db.query(User.id).first() is not None:
        error = security.ADMIN_NAME_ERROR
    if not error and password != password_confirm:
        error = "رمز عبور و تکرار آن یکسان نیستند"
    if error:
        return render(request, "register.html", db, error=error, form={"username": username})
    if db.query(User).filter(User.username == username).first():
        return render(
            request,
            "register.html",
            db,
            error="این نام کاربری قبلاً ثبت شده است",
            form={"username": username},
        )
    user = User(username=username, password_hash=hash_password(password), last_login_at=utcnow())
    db.add(user)
    db.commit()
    rate_limit.record(ip_key, rate_limit.REGISTER_WINDOW_SECONDS)
    request.session["user_id"] = user.id
    flash(request, "حساب شما ساخته شد. دارایی‌هایتان را در صفحهٔ دارایی‌ها وارد کنید.")
    return RedirectResponse("/assets", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_to_dashboard_if_authenticated(request, db):
        return redirect
    return render(request, "login.html", db, error=None, form={"username": ""})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    username = normalize_username(username)
    ip = rate_limit.client_ip(request)
    user_key = f"login:user:{username}:{ip}"
    ip_key = f"login:ip:{ip}"
    window = rate_limit.LOGIN_WINDOW_SECONDS
    if rate_limit.is_limited(user_key, rate_limit.LOGIN_FAILS_PER_USER, window) or rate_limit.is_limited(
        ip_key, rate_limit.LOGIN_FAILS_PER_IP, window
    ):
        return render(
            request,
            "login.html",
            db,
            error="تلاش‌های ناموفق زیاد بود. ۱۵ دقیقه دیگر دوباره امتحان کنید",
            form={"username": username},
        )
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        rate_limit.record(user_key, window)
        rate_limit.record(ip_key, window)
        return render(
            request,
            "login.html",
            db,
            error="نام کاربری یا رمز عبور نادرست است",
            form={"username": username},
        )
    rate_limit.clear(user_key)
    user.last_login_at = utcnow()
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf: str = Form("")):
    require_csrf(request, csrf)
    invalidate_session(request)
    response = RedirectResponse("/login", status_code=303)
    # Drop the browser's HTTP cache (and back/forward cache) for this site: no private page after logout.
    # The service worker deletes its own offline copy of the dashboard on this same response.
    response.headers["Clear-Site-Data"] = '"cache"'
    return attach_session_cookie_deletion(response)
