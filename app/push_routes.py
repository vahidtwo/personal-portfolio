"""Push notification API (Firebase)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import rate_limit
from app.amounts_api import same_origin
from app.config import FIREBASE_VAPID_KEY, firebase_android_config, firebase_web_config
from app.db import get_db
from app.firebase_push import (
    device_counts,
    firebase_admin_ready,
    remove_device_token,
    send_push_detailed,
    upsert_device_token,
)
from app.security import get_current_user, require_csrf

router = APIRouter()

NO_STORE = {"Cache-Control": "no-store, private", "Vary": "Cookie"}
TEST_LIMIT = 3
TEST_WINDOW_SECONDS = 60
TEST_TITLE = "دارایی‌تو"
TEST_BODY = "اعلان آزمایشی: اعلان‌ها روی این دستگاه کار می‌کنند."


def _json(payload: dict, status_code: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers={**NO_STORE, **(headers or {})})


@router.get("/api/push/config")
def push_config():
    cfg = firebase_web_config()
    android = firebase_android_config()
    if cfg is None and android is None:
        return JSONResponse({"enabled": False})
    return JSONResponse(
        {
            "enabled": cfg is not None,
            "config": cfg,
            "vapidKey": FIREBASE_VAPID_KEY or None,
            "android": android,
        }
    )


async def _json_body(request: Request) -> dict | None:
    try:
        payload = await request.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


@router.post("/api/push/register")
async def push_register(request: Request, db: Session = Depends(get_db)):
    # No CSRF token: the Android app posts JSON without one; the same-origin check guards this endpoint.
    if not same_origin(request):
        return _json({"ok": False, "error": "origin"}, 403)
    user = get_current_user(request, db)
    if user is None:
        return _json({"ok": False, "error": "login"}, 401)
    payload = await _json_body(request)
    if payload is None:
        return _json({"ok": False, "error": "invalid"}, 400)
    token = str(payload.get("token") or "").strip()
    platform = str(payload.get("platform") or "web").strip().lower()
    if not token or len(token) > 4096:
        return _json({"ok": False, "error": "token"}, 400)
    upsert_device_token(db, user, token, platform)
    db.commit()
    return _json({"ok": True})


@router.post("/api/push/unregister")
async def push_unregister(request: Request, db: Session = Depends(get_db)):
    # No CSRF token: the Android app posts JSON without one; the same-origin check guards this endpoint.
    if not same_origin(request):
        return _json({"ok": False, "error": "origin"}, 403)
    user = get_current_user(request, db)
    if user is None:
        return _json({"ok": False, "error": "login"}, 401)
    payload = await _json_body(request)
    if payload is None:
        return _json({"ok": False, "error": "invalid"}, 400)
    token = str(payload.get("token") or "").strip()
    if token:
        remove_device_token(db, user, token)
        db.commit()
    return _json({"ok": True})


@router.get("/api/push/status")
def push_status(request: Request, db: Session = Depends(get_db)):
    if not same_origin(request):
        return _json({"ok": False, "error": "origin"}, 403)
    user = get_current_user(request, db)
    if user is None:
        return _json({"ok": False, "error": "login"}, 401)
    return _json(
        {
            "ok": True,
            "server": firebase_admin_ready(),
            "web": firebase_web_config() is not None,
            "android": firebase_android_config() is not None,
            "devices": device_counts(db, user.id),
        }
    )


@router.post("/api/push/test")
async def push_test(request: Request, db: Session = Depends(get_db)):
    """Send one test notification to the signed-in user's own registered devices."""
    if not same_origin(request):
        return _json({"ok": False, "error": "origin"}, 403)
    user = get_current_user(request, db)
    if user is None:
        return _json({"ok": False, "error": "login"}, 401)
    payload = await _json_body(request)
    if payload is None:
        return _json({"ok": False, "error": "invalid"}, 400)
    try:
        require_csrf(request, str(payload.get("csrf") or ""))
    except Exception:
        return _json({"ok": False, "error": "csrf"}, 400)
    key = f"push-test:{user.id}"
    wait = rate_limit.retry_after(key, TEST_LIMIT, TEST_WINDOW_SECONDS)
    if wait:
        return _json({"ok": False, "error": "rate", "retry_after": wait}, 429, {"Retry-After": str(wait)})
    rate_limit.record(key, TEST_WINDOW_SECONDS)
    result = send_push_detailed(
        db,
        user.id,
        title=TEST_TITLE,
        body=TEST_BODY,
        data={"type": "test", "url": "/profile#push-settings"},
    )
    return _json(
        {
            "ok": result.total > 0,
            "error": result.error,
            "sent": result.sent,
            "failed": result.failed,
            "devices": result.devices,
            "removed": result.removed,
        }
    )
