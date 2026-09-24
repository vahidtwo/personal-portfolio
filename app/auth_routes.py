"""Landing, register, login, and logout."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, utcnow
from app.security import (
    get_current_user,
    hash_password,
    normalize_username,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)
from app.web import flash, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "landing.html", db)


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "register.html", db, error=None, form={"username": ""})


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    username = normalize_username(username)
    error = validate_username(username) or validate_password(password)
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
    request.session["user_id"] = user.id
    flash(request, "حساب شما ساخته شد. موجودی را در پروفایل وارد کنید.")
    return RedirectResponse("/profile", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
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
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        return render(
            request,
            "login.html",
            db,
            error="نام کاربری یا رمز عبور نادرست است",
            form={"username": username},
        )
    user.last_login_at = utcnow()
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf: str = Form("")):
    require_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
