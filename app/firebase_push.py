"""Firebase Cloud Messaging (server SDK)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import (
    FIREBASE_CREDENTIALS_JSON,
    FIREBASE_CREDENTIALS_PATH,
    firebase_web_config,
)
from app.models import PushDeviceToken, User

logger = logging.getLogger(__name__)

_firebase_ready = False


def firebase_admin_ready() -> bool:
    global _firebase_ready
    if _firebase_ready:
        return True
    if firebase_web_config() is None:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin not installed; push disabled")
        return False
    if firebase_admin._apps:
        _firebase_ready = True
        return True
    cred = None
    path = FIREBASE_CREDENTIALS_PATH
    if path and Path(path).is_file():
        cred = credentials.Certificate(path)
    elif FIREBASE_CREDENTIALS_JSON.strip():
        cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON))
    else:
        default = Path(path) if path else None
        data_path = Path(__file__).resolve().parent.parent / "data" / "firebase-service-account.json"
        if data_path.is_file():
            cred = credentials.Certificate(str(data_path))
        elif default and default.is_file():
            cred = credentials.Certificate(str(default))
    if cred is None:
        logger.warning("Firebase credentials missing; set FIREBASE_CREDENTIALS_PATH or data/firebase-service-account.json")
        return False
    firebase_admin.initialize_app(cred)
    _firebase_ready = True
    return True


def upsert_device_token(db: Session, user: User, token: str, platform: str) -> None:
    token = token.strip()
    if not token:
        return
    platform = platform if platform in ("web", "android") else "web"
    existing = db.query(PushDeviceToken).filter(PushDeviceToken.token == token).one_or_none()
    if existing is not None:
        existing.user_id = user.id
        existing.platform = platform
    else:
        db.add(PushDeviceToken(user_id=user.id, token=token, platform=platform))


def remove_device_token(db: Session, user: User, token: str) -> None:
    token = token.strip()
    if not token:
        return
    row = (
        db.query(PushDeviceToken)
        .filter(PushDeviceToken.user_id == user.id, PushDeviceToken.token == token)
        .one_or_none()
    )
    if row is not None:
        db.delete(row)


def service_worker_firebase_snippet() -> str:
    cfg = firebase_web_config()
    if cfg is None:
        return ""
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    return f"""

importScripts("https://www.gstatic.com/firebasejs/11.6.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/11.6.0/firebase-messaging-compat.js");
firebase.initializeApp({cfg_json});
const firebaseMessaging = firebase.messaging();
firebaseMessaging.onBackgroundMessage(function (payload) {{
  const title = (payload.notification && payload.notification.title) || "موجودی من";
  const body = (payload.notification && payload.notification.body) || "";
  const options = {{
    body: body,
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: payload.data || {{}},
  }};
  return self.registration.showNotification(title, options);
}});
"""


def send_push_to_user(
    db: Session,
    user_id: int,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    if not firebase_admin_ready():
        return 0
    from firebase_admin import messaging

    tokens = [
        row.token
        for row in db.query(PushDeviceToken).filter(PushDeviceToken.user_id == user_id).all()
    ]
    if not tokens:
        return 0
    note = messaging.Notification(title=title, body=body)
    message = messaging.MulticastMessage(
        notification=note,
        data=data or {},
        tokens=tokens,
    )
    response = messaging.send_each_for_multicast(message)
    stale: list[str] = []
    for idx, result in enumerate(response.responses):
        if result.success:
            continue
        exc = result.exception
        code = getattr(exc, "code", "") or str(exc)
        if "registration-token-not-registered" in str(code).lower() or "invalid" in str(code).lower():
            stale.append(tokens[idx])
    for token in stale:
        db.query(PushDeviceToken).filter(PushDeviceToken.token == token).delete()
    if stale:
        db.commit()
    return response.success_count
