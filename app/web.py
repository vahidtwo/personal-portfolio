"""Jinja rendering and session flash messages."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import json

from app.config import STATIC_ASSET_VERSION, firebase_web_config
from app.formatting import format_number, format_toman, format_when, persian_digits
from app.security import csrf_token, get_current_user, is_admin

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["static_v"] = STATIC_ASSET_VERSION
templates.env.filters["toman"] = format_toman
templates.env.filters["when"] = format_when
templates.env.filters["fa"] = persian_digits  # digits only (years, ids, input values)
templates.env.filters["num"] = format_number  # THE display number formatter
# Signup rules shown as hints come from the real validator constants.
from app.security import PASSWORD_MIN_LENGTH, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH  # noqa: E402

from app.formatting import tehran_today  # noqa: E402

templates.env.globals["current_jalali_year"] = lambda: tehran_today().year
templates.env.globals["auth_rules"] = {
    "username_min": USERNAME_MIN_LENGTH,
    "username_max": USERNAME_MAX_LENGTH,
    "password_min": PASSWORD_MIN_LENGTH,
}


def render(request: Request, name: str, db: Session, **context) -> HTMLResponse:
    current = get_current_user(request, db)
    push_cfg = firebase_web_config()
    context.update(
        {
            "request": request,
            "user": current,
            "is_admin": is_admin(current),
            "csrf": csrf_token(request),
            "push_enabled": push_cfg is not None,
            "firebase_web_config_json": json.dumps(push_cfg, ensure_ascii=False) if push_cfg else "",
        }
    )
    return templates.TemplateResponse(request, name, context)


def flash(request: Request, message: str, *, error: bool = False) -> None:
    request.session["flash"] = message
    request.session["flash_error"] = error


def pop_flash(request: Request) -> tuple[str | None, bool]:
    message = request.session.pop("flash", None)
    is_error = bool(request.session.pop("flash_error", False))
    return message, is_error
