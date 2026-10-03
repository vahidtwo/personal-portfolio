"""Push notification API (Firebase)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import FIREBASE_VAPID_KEY, firebase_web_config
from app.db import get_db
from app.firebase_push import remove_device_token, send_push_to_user, upsert_device_token
from app.security import get_current_user

router = APIRouter()


@router.get("/api/push/config")
def push_config():
    cfg = firebase_web_config()
    if cfg is None:
        return JSONResponse({"enabled": False})
    return JSONResponse(
        {
            "enabled": True,
            "config": cfg,
            "vapidKey": FIREBASE_VAPID_KEY or None,
        }
    )


@router.post("/api/push/register")
async def push_register(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return JSONResponse({"ok": False, "error": "login"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    token = str(payload.get("token") or "").strip()
    platform = str(payload.get("platform") or "web").strip().lower()
    if not token:
        return JSONResponse({"ok": False, "error": "token"}, status_code=400)
    upsert_device_token(db, user, token, platform)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/push/unregister")
async def push_unregister(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return JSONResponse({"ok": False, "error": "login"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
    token = str(payload.get("token") or "").strip()
    if token:
        remove_device_token(db, user, token)
        db.commit()
    return JSONResponse({"ok": True})
