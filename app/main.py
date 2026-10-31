"""App entrypoint. Routes live in feature modules."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.session_marker import SessionMarkerMiddleware
from app.native_api import router as native_api_router
from app.static_gzip import StaticGZipMiddleware

from app.admin_users import router as admin_users_router
from app.assets_page import router as assets_router
from app.car_routes import router as car_router
from app.auth_routes import router as auth_router
from app.unified_auth import router as unified_auth_router
from app.config import (
    DATA_DIR,
    ENABLE_INTERNAL_SCHEDULER,
    HTTPS_ONLY,
    SECRET_KEY,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
)
from app.dashboard import router as dashboard_router
from app.db import init_db
from app.db_admin import router as db_admin_router
from app.debts import router as debts_router
from app.expenses import router as expenses_router
from app.firebase_push import validate_firebase_admin_at_startup
from app.jobs import run_hourly_job
from app.mcp_http import router as mcp_router
from app.profile import router as profile_router
from app.push_routes import router as push_router
from app.pwa import router as pwa_router
from app.scheduler import start_hourly_scheduler, start_nightly_backup, stop_hourly_scheduler
from app.spends import router as spends_router
from app.web import BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Placeholder values from docker-compose.yml / .env.example. Running with one of them means every
# deploy can sign sessions with a guessable key, so start-up stops instead.
PLACEHOLDER_SECRET_KEYS = frozenset({"change-me-in-dokploy", "change-me-to-a-long-random-string"})


class InsecureSecretKey(RuntimeError):
    pass


def _secret_key() -> str:
    # Used exactly as set: surrounding spaces are part of the key, never trimmed away.
    key = SECRET_KEY or ""
    if not key:
        raise InsecureSecretKey(
            "SECRET_KEY is not set. Set it to a long random string (e.g. in Dokploy > Environment); "
            "for local runs export an explicit dev key, e.g. SECRET_KEY=dev-only-key."
        )
    if key in PLACEHOLDER_SECRET_KEYS:
        raise InsecureSecretKey(
            f"SECRET_KEY is the placeholder {key!r}. Set a long random value (e.g. in Dokploy > Environment)."
        )
    return key


SCHEDULER_OFF_WARNING = (
    "ENABLE_INTERNAL_SCHEDULER is off: the hourly job and the nightly SQLite backups will NOT run in this "
    "process. No backups will be made unless an external cron runs scripts/create_snapshot.py and the backup."
)


def warn_scheduler_off() -> None:
    logger.warning("!" * 72)
    logger.warning(SCHEDULER_OFF_WARNING)
    logger.warning("!" * 72)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    validate_firebase_admin_at_startup()
    await run_hourly_job(take_snapshots=False)
    if ENABLE_INTERNAL_SCHEDULER:
        start_hourly_scheduler()
        start_nightly_backup()
    else:
        warn_scheduler_off()
    yield
    await stop_hourly_scheduler()


# Server release (semver). The Android app keeps its own versionName in android_release.json.
SERVER_VERSION = "12.1.0"
app = FastAPI(title="Daraiito", version=SERVER_VERSION, lifespan=lifespan)
# Added first = runs inside SessionMiddleware, so it sees the final session (see app/session_marker.py).
app.add_middleware(
    SessionMarkerMiddleware, max_age=SESSION_MAX_AGE_SECONDS, https_only=HTTPS_ONLY, secret_key=_secret_key()
)
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key(),
    session_cookie=SESSION_COOKIE_NAME,
    same_site="lax",
    https_only=HTTPS_ONLY,
    max_age=SESSION_MAX_AGE_SECONDS,
)
app.add_middleware(StaticGZipMiddleware, minimum_size=1000)  # /static/*.css|*.js only
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# Pages with a form the user types into. They get "no-cache" instead of "no-store" so Back/Forward
# (bfcache and the browser's form restore) brings the typed values back; "no-cache" still makes every
# normal load revalidate with the server, so a deploy is picked up on the next load. "private" keeps
# shared proxies from storing them.
FORM_PAGE_PATHS = frozenset({"/assets", "/profile", "/auth", "/login", "/register"})
FORM_PAGE_CACHE_CONTROL = "no-cache, private"


def is_form_page(path: str, query_params) -> bool:
    if path in FORM_PAGE_PATHS:
        return True
    return path == "/dashboard" and query_params.get("tab") == "daily"  # the daily spend form


@app.middleware("http")
async def no_store_html(request, call_next):
    """Never let a browser, proxy or WebView HTTP cache keep an HTML page: after a deploy the next load
    must come from the server. Form pages (GET only) use "no-cache, private" instead so typed input
    survives Back/Forward. Versioned /static assets keep their normal caching. The service worker's
    own offline copy of the dashboard (Cache API) is not affected by this header."""
    response = await call_next(request)
    if not request.url.path.startswith("/static/") and response.headers.get("content-type", "").startswith("text/html"):
        if request.method == "GET" and response.status_code == 200 and is_form_page(request.url.path, request.query_params):
            response.headers["Cache-Control"] = FORM_PAGE_CACHE_CONTROL
        else:
            response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health():
    return JSONResponse({"ok": True})


app.include_router(pwa_router)
app.include_router(push_router)
app.include_router(auth_router)
app.include_router(unified_auth_router)
app.include_router(native_api_router)
app.include_router(dashboard_router)
app.include_router(admin_users_router)
app.include_router(db_admin_router)
app.include_router(mcp_router)
app.include_router(assets_router)
app.include_router(car_router)
app.include_router(profile_router)
app.include_router(debts_router)
app.include_router(expenses_router)
app.include_router(spends_router)
