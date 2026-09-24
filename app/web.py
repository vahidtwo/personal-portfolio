"""Jinja rendering and session flash messages."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.formatting import format_toman, format_when, persian_digits
from app.security import csrf_token, get_current_user, is_admin

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["toman"] = format_toman
templates.env.filters["when"] = format_when
templates.env.filters["fa"] = persian_digits


def render(request: Request, name: str, db: Session, **context) -> HTMLResponse:
    current = get_current_user(request, db)
    context.update(
        {
            "request": request,
            "user": current,
            "is_admin": is_admin(current),
            "csrf": csrf_token(request),
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
