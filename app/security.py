from __future__ import annotations

import re
import secrets
from decimal import Decimal, InvalidOperation

import bcrypt
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import ADMIN_USERNAMES, HTTPS_ONLY, SESSION_COOKIE_NAME
from app.models import User

USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SAMESITE = "lax"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_username(username: str) -> str | None:
    if not USERNAME_RE.match(username):
        return "نام کاربری باید ۳ تا ۳۲ کاراکتر باشد و با حرف انگلیسی شروع شود"
    return None


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "رمز عبور باید حداقل ۸ کاراکتر باشد"
    return None


def parse_decimal(raw: str | None, *, field: str) -> Decimal:
    text = (raw or "0").strip().translate(PERSIAN_DIGITS).replace(",", "").replace("٬", "").replace(" ", "")
    if text == "":
        return Decimal("0")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"عدد نامعتبر: {field}",
        ) from exc
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"مقدار منفی مجاز نیست: {field}",
        )
    return value


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def require_csrf(request: Request, submitted: str | None) -> None:
    expected = request.session.get("csrf")
    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSRF token invalid")


def invalidate_session(request: Request) -> None:
    request.session.clear()


def attach_session_cookie_deletion(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        secure=HTTPS_ONLY,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )
    return response


def redirect_to_login(request: Request, *, status_code: int = 303) -> RedirectResponse:
    """Clear invalid auth state and redirect to login (never loop back to dashboard)."""
    invalidate_session(request)
    target = "/login"
    if request.url.path.rstrip("/") == target.rstrip("/"):
        target = "/"
    response = RedirectResponse(target, status_code=status_code)
    return attach_session_cookie_deletion(response)


def redirect_to_dashboard_if_authenticated(request: Request, db: Session) -> RedirectResponse | None:
    user = get_authenticated_user(request, db)
    if user is None:
        return None
    if request.url.path.rstrip("/") == "/dashboard":
        return None
    return RedirectResponse("/dashboard", status_code=303)


def get_authenticated_user(request: Request, db: Session) -> User | None:
    """Return the logged-in user only when session user_id maps to a real row; else clear session."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        invalidate_session(request)
        return None
    if uid <= 0:
        invalidate_session(request)
        return None
    user = db.get(User, uid)
    if user is None:
        invalidate_session(request)
        return None
    return user


def get_current_user(request: Request, db: Session) -> User | None:
    return get_authenticated_user(request, db)


def is_admin(user: User | None) -> bool:
    if user is None or not ADMIN_USERNAMES:
        return False
    return normalize_username(user.username) in ADMIN_USERNAMES


def require_user(request: Request, db: Session) -> User:
    user = get_authenticated_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user
