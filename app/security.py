from __future__ import annotations

import re
import secrets
from decimal import Decimal, InvalidOperation

import bcrypt
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models import User

USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


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
        return "نام کاربری ۳ تا ۳۲ حرف، با حرف انگلیسی شروع شود / Username: 3–32 chars, start with a letter"
    return None


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "رمز عبور حداقل ۸ کاراکتر / Password must be at least 8 characters"
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
            detail=f"عدد نامعتبر / Invalid number: {field}",
        ) from exc
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"مقدار منفی مجاز نیست / Negative values are not allowed: {field}",
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


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user
