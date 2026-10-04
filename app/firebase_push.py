"""Firebase Cloud Messaging (server SDK)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.config import (
    FIREBASE_CLIENT_EMAIL,
    FIREBASE_PRIVATE_KEY,
    FIREBASE_PRIVATE_KEY_ID,
    FIREBASE_PROJECT_ID,
    firebase_web_config,
)
from app.models import PushDeviceToken, User

logger = logging.getLogger(__name__)

_ADMIN_REQUIRED_ENV = (
    "FIREBASE_PROJECT_ID",
    "FIREBASE_CLIENT_EMAIL",
    "FIREBASE_PRIVATE_KEY",
)


class FirebaseAdminConfigError(RuntimeError):
    """Server Firebase Admin env is missing or invalid."""


def normalize_firebase_private_key(raw: str) -> str:
    key = (raw or "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1]
    return key.replace("\\n", "\n")


def _missing_admin_env_vars() -> list[str]:
    missing: list[str] = []
    if not (FIREBASE_PROJECT_ID or "").strip():
        missing.append("FIREBASE_PROJECT_ID")
    if not (FIREBASE_CLIENT_EMAIL or "").strip():
        missing.append("FIREBASE_CLIENT_EMAIL")
    if not (FIREBASE_PRIVATE_KEY or "").strip():
        missing.append("FIREBASE_PRIVATE_KEY")
    return missing


def _admin_env_partially_set() -> bool:
    return bool(
        (os.environ.get("FIREBASE_CLIENT_EMAIL") or "").strip()
        or (os.environ.get("FIREBASE_PRIVATE_KEY") or "").strip()
    )


def _service_account_dict() -> dict[str, str]:
    missing = _missing_admin_env_vars()
    if missing:
        raise FirebaseAdminConfigError(
            "Firebase Admin is missing required environment variables: " + ", ".join(missing)
        )
    private_key = normalize_firebase_private_key(FIREBASE_PRIVATE_KEY)
    if "BEGIN PRIVATE KEY" not in private_key:
        raise FirebaseAdminConfigError("FIREBASE_PRIVATE_KEY is not a valid PEM private key")
    project_id = FIREBASE_PROJECT_ID.strip()
    client_email = FIREBASE_CLIENT_EMAIL.strip()
    payload: dict[str, str] = {
        "type": "service_account",
        "project_id": project_id,
        "private_key": private_key,
        "client_email": client_email,
        "client_id": "",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email.replace('@', '%40')}",
    }
    if (FIREBASE_PRIVATE_KEY_ID or "").strip():
        payload["private_key_id"] = FIREBASE_PRIVATE_KEY_ID.strip()
    return payload


def get_firebase_admin() -> Any:
    """Initialize firebase-admin once from env vars; return the App instance."""
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise FirebaseAdminConfigError("firebase-admin package is not installed") from exc

    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred = credentials.Certificate(_service_account_dict())
    return firebase_admin.initialize_app(cred)


def validate_firebase_admin_at_startup() -> None:
    """If Admin env vars are partially configured, require a complete config (fail fast)."""
    if not _admin_env_partially_set():
        return
    get_firebase_admin()
    logger.info("Firebase Admin credentials loaded from environment variables")


def firebase_admin_ready() -> bool:
    try:
        get_firebase_admin()
        return True
    except FirebaseAdminConfigError as exc:
        logger.warning("%s", exc)
        return False
    except Exception:
        logger.exception("Firebase Admin initialization failed")
        return False


def dry_run_firebase_message(*, token: str = "dry-run-token") -> None:
    """Validate credentials and message shape without delivering (FCM dry_run)."""
    get_firebase_admin()
    from firebase_admin import messaging

    message = messaging.Message(
        notification=messaging.Notification(title="موجودی من", body="dry-run"),
        token=token,
    )
    messaging.send(message, dry_run=True)


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
