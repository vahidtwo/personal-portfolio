import os
from pathlib import Path


def _admin_usernames() -> frozenset[str]:
    raw = os.environ.get("ADMIN_USERNAMES", "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
ADMIN_USERNAMES = _admin_usernames()
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'inventory.db'}")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
HTTPS_ONLY = os.environ.get("HTTPS_ONLY", "0") == "1"
SESSION_COOKIE_NAME = "inventory_session"
CHANDE_URL = os.environ.get(
    "CHANDE_URL",
    "https://chande.net/api/v1/prices/current",
)
PRICE_REFRESH_HOURS = int(os.environ.get("PRICE_REFRESH_HOURS", "1"))
PRICE_MANUAL_REFRESH_MINUTES = int(os.environ.get("PRICE_MANUAL_REFRESH_MINUTES", "5"))
ENABLE_INTERNAL_SCHEDULER = os.environ.get("ENABLE_INTERNAL_SCHEDULER", "1") == "1"
# Bump when static JS/CSS change so browsers and the service worker pick up new assets.
STATIC_ASSET_VERSION = os.environ.get("STATIC_ASSET_VERSION", "20260303b")

# Firebase Cloud Messaging (optional). Web client keys are public; keep service account secret.
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_MESSAGING_SENDER_ID = os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "")
FIREBASE_APP_ID = os.environ.get("FIREBASE_APP_ID", "")
FIREBASE_VAPID_KEY = os.environ.get("FIREBASE_VAPID_KEY", "")
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH",
    str(DATA_DIR / "firebase-service-account.json"),
)


def _firebase_credentials_json_raw() -> str:
    return os.environ.get("FIREBASE_CREDENTIALS_JSON", "")


FIREBASE_CREDENTIALS_JSON = _firebase_credentials_json_raw()


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
