import os
import re
from pathlib import Path


def _admin_usernames() -> frozenset[str]:
    raw = os.environ.get("ADMIN_USERNAMES", "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
ADMIN_USERNAMES = _admin_usernames()
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'inventory.db'}")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
# On by default: http -> https redirect, HSTS and Secure cookies. Local dev and tests set HTTPS_ONLY=0.
HTTPS_ONLY = os.environ.get("HTTPS_ONLY", "1") == "1"
# Modest HSTS lifetime (seconds), no includeSubDomains, no preload.
HSTS_MAX_AGE = int(os.environ.get("HSTS_MAX_AGE", "86400"))
SESSION_COOKIE_NAME = "inventory_session"
# Session cookie lifetime. The service worker's offline copy of the dashboard expires after the same time.
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
CHANDE_URL = os.environ.get(
    "CHANDE_URL",
    "https://chande.net/api/v1/prices/current",
)
ARZBAN_PRICES_URL = os.environ.get(
    "ARZBAN_PRICES_URL",
    "https://fm5.ir/api/v1/prices",
)
PRICE_REFRESH_HOURS = int(os.environ.get("PRICE_REFRESH_HOURS", "1"))
PRICE_MANUAL_REFRESH_MINUTES = int(os.environ.get("PRICE_MANUAL_REFRESH_MINUTES", "5"))
ENABLE_INTERNAL_SCHEDULER = os.environ.get("ENABLE_INTERNAL_SCHEDULER", "1") == "1"
# Bump when static JS/CSS change so browsers and the service worker pick up new assets.
STATIC_ASSET_VERSION = os.environ.get("STATIC_ASSET_VERSION", "20261110d")
# Public origin shown to users (e.g. MCP URL). Empty = use the request's own base URL.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Domain move (docs: /workspace/plans/daraiito-domain-move.md): the one-time notice is shown on the old host only.
MOVE_NOTICE_OLD_HOST = "portfolio.vahidtwo.ir"
MOVE_NEW_URL = "https://daraiito.ir"

# Firebase Cloud Messaging (optional). Web client keys are public; keep service account secret.
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_MESSAGING_SENDER_ID = os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "")
FIREBASE_APP_ID = os.environ.get("FIREBASE_APP_ID", "")
FIREBASE_VAPID_KEY = os.environ.get("FIREBASE_VAPID_KEY", "")
# Android app of the same Firebase project (public client values, read by the app at runtime, so the APK
# needs no google-services.json). The API key falls back to the web key when no Android key is set.
FIREBASE_ANDROID_APP_ID = os.environ.get("FIREBASE_ANDROID_APP_ID", "")
FIREBASE_ANDROID_API_KEY = os.environ.get("FIREBASE_ANDROID_API_KEY", "")
# Server-only (FCM Admin SDK). Never expose in templates or static assets.
FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "")
FIREBASE_PRIVATE_KEY_ID = os.environ.get("FIREBASE_PRIVATE_KEY_ID", "")


def firebase_web_config() -> dict[str, str] | None:
    required = (
        FIREBASE_API_KEY,
        FIREBASE_AUTH_DOMAIN,
        FIREBASE_PROJECT_ID,
        FIREBASE_MESSAGING_SENDER_ID,
        FIREBASE_APP_ID,
    )
    if not all(required):
        return None
    return {
        "apiKey": FIREBASE_API_KEY,
        "authDomain": FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
        "messagingSenderId": FIREBASE_MESSAGING_SENDER_ID,
        "appId": FIREBASE_APP_ID,
    }


ANDROID_APP_ID_RE = re.compile(r"^1:[0-9]+:android:[0-9a-f]+$")


def firebase_android_config() -> dict[str, str] | None:
    app_id = FIREBASE_ANDROID_APP_ID.strip()
    api_key = (FIREBASE_ANDROID_API_KEY or FIREBASE_API_KEY).strip()
    project_id = FIREBASE_PROJECT_ID.strip()
    sender_id = FIREBASE_MESSAGING_SENDER_ID.strip()
    if not (app_id and api_key and project_id and sender_id) or not ANDROID_APP_ID_RE.match(app_id):
        return None
    if app_id.split(":")[1] != sender_id:
        return None
    return {"appId": app_id, "apiKey": api_key, "projectId": project_id, "senderId": sender_id}
