"""GET /api/amounts: the amounts of one signed-in page, as JSON, for amounts.js to fill in."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import get_authenticated_user
from app.web import AMOUNTS_NO_STORE

router = APIRouter()

SAME_SITE_FETCH = frozenset({"same-origin", "none"})


def _pages():
    from app.assets_page import assets_page
    from app.dashboard import dashboard
    from app.profile import profile_form

    return {"/dashboard": dashboard, "/profile": profile_form, "/assets": assets_page}


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=AMOUNTS_NO_STORE)


def same_origin(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site is not None and site.lower() not in SAME_SITE_FETCH:
        return False
    origin = request.headers.get("origin")
    if origin is not None:
        host = (request.headers.get("host") or "").lower()
        if origin == "null" or urlsplit(origin).netloc.lower() != host:
            return False
    return True


@router.get("/api/amounts")
async def amounts(request: Request, path: str = "", db: Session = Depends(get_db)):
    if not same_origin(request):
        return _error("origin", 403)
    if get_authenticated_user(request, db) is None:
        return _error("login", 401)
    parts = urlsplit(path)
    handler = _pages().get(parts.path)
    if parts.scheme or parts.netloc or handler is None:
        return _error("path", 400)
    scope = dict(request.scope)
    scope["path"] = parts.path
    scope["raw_path"] = parts.path.encode()
    scope["query_string"] = parts.query.encode()
    scope["state"] = {"amounts_collect": {}}
    response = await handler(Request(scope, request.receive), db=db)
    if isinstance(response, JSONResponse):
        return response
    return _error("reload", 409)
