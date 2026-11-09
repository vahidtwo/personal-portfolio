"""Jinja rendering and session flash messages."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import pass_context
from markupsafe import Markup
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import json

from app import config as _config
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


# Amounts are never written into page HTML. Templates mark each one with amt()/amt_attrs()/amt_json(),
# which emit an empty placeholder; GET /api/amounts renders the same page with a collector and
# returns the values as JSON, and amounts.js fills the placeholders.
@pass_context
def _amt(ctx, key, value):
    bag = ctx.get("_amounts")
    if bag is not None:
        bag[str(key)] = "" if value is None else str(value)
    return Markup('<span data-amt="%s"></span>') % (str(key),)


@pass_context
def _amt_attrs(ctx, *pairs):
    bag = ctx.get("_amounts")
    names = []
    for attr, key, value in pairs:
        if bag is not None:
            bag[str(key)] = value if isinstance(value, (dict, list)) else ("" if value is None else str(value))
        names.append(f"{attr}={key}")
    return Markup(' data-amt-attr="%s"') % (" ".join(names),)


@pass_context
def _amt_json(ctx, key, value):
    bag = ctx.get("_amounts")
    if bag is not None:
        bag[str(key)] = value
    return Markup("null")


templates.env.globals["amt"] = _amt
templates.env.globals["amt_attrs"] = _amt_attrs
templates.env.globals["amt_json"] = _amt_json
# Signup rules shown as hints come from the real validator constants.
from app.security import PASSWORD_MIN_LENGTH, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH  # noqa: E402

from app.formatting import tehran_today  # noqa: E402



def android_apk_info() -> dict | None:
    """Version + size of the Android APK actually on the server, or None when the file is missing."""
    from app.apk_info import apk_info

    return apk_info(BASE_DIR / "static" / "my-inventory.apk")


templates.env.globals["android_apk_info"] = android_apk_info
templates.env.globals["current_jalali_year"] = lambda: tehran_today().year
templates.env.globals["auth_rules"] = {
    "username_min": USERNAME_MIN_LENGTH,
    "username_max": USERNAME_MAX_LENGTH,
    "password_min": PASSWORD_MIN_LENGTH,
}


def page_url_for(name: str, context: dict) -> str | None:
    """The GET URL of the page a POST re-rendered (e.g. a validation error), so the address bar can show it
    with history.replaceState instead of the form's action URL. None = leave the address bar alone."""
    if name == "assets.html":
        return "/assets"
    if name == "profile.html":
        if context.get("tab") != "debts":
            return "/profile"
        url = "/profile?tab=debts"
        if context.get("editing_id"):
            url += f"&edit={int(context['editing_id'])}"
        elif context.get("editing_expense_id"):
            url += f"&spend={int(context['editing_expense_id'])}"
        return url
    if name == "dashboard.html" and context.get("tab") == "daily":
        url = "/dashboard?tab=daily"
        if context.get("daily_year") and context.get("daily_month"):
            url += f"&jy={int(context['daily_year'])}&jm={int(context['daily_month'])}"
        if context.get("editing_spend_id"):
            url += f"&edit_spend={int(context['editing_spend_id'])}"
        return url
    return None


AMOUNTS_NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Cookie"}


def render(request: Request, name: str, db: Session, **context) -> HTMLResponse:
    if request.method == "POST" and "page_url" not in context:
        context["page_url"] = page_url_for(name, context)
    current = get_current_user(request, db)
    push_cfg = firebase_web_config()
    context.update(
        {
            "request": request,
            "user": current,
            "is_admin": is_admin(current),
            "csrf": csrf_token(request),
            "push_enabled": push_cfg is not None,
            # Domain-move notice: server-side host check (the JS checks the host again and never runs in the app).
            "move_notice": (request.url.hostname or "").lower() == _config.MOVE_NOTICE_OLD_HOST,
            "move_new_url": _config.MOVE_NEW_URL,
            "firebase_web_config": push_cfg or {},
        }
    )
    collect = getattr(request.state, "amounts_collect", None)
    if collect is not None:
        context["_amounts"] = collect
        templates.get_template(name).render(context)
        return JSONResponse({"v": collect}, headers=AMOUNTS_NO_STORE)
    return templates.TemplateResponse(request, name, context)


def flash(request: Request, message: str, *, error: bool = False) -> None:
    request.session["flash"] = message
    request.session["flash_error"] = error


def pop_flash(request: Request) -> tuple[str | None, bool]:
    message = request.session.pop("flash", None)
    is_error = bool(request.session.pop("flash_error", False))
    return message, is_error


_LANDING_MANIFEST: dict | None = None


def landing_manifest() -> dict:
    """slot -> {"dark": [{file, w, h}, ...], "light": [...]} for the landing screenshots (scripts/landing_shots.py)."""
    global _LANDING_MANIFEST
    if _LANDING_MANIFEST is None:
        path = BASE_DIR / "static" / "landing" / "manifest.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _LANDING_MANIFEST = data.get("slots", {}) if isinstance(data, dict) else {}
    return _LANDING_MANIFEST


templates.env.globals["landing_manifest"] = landing_manifest
