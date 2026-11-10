"""App entrypoint. Routes live in feature modules."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.session_marker import SessionMarkerMiddleware
from app.https_redirect import HttpsRedirectMiddleware
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
    HSTS_MAX_AGE,
    HTTPS_ONLY,
    SECRET_KEY,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    STATIC_ASSET_VERSION,
)
from app.amounts_api import router as amounts_router
from app.dashboard import router as dashboard_router
from app.db import init_db
from app.admin_categories import router as admin_categories_router
from app.db_admin import router as db_admin_router
from app.debts import router as debts_router
from app.expenses import router as expenses_router
from app.firebase_android import start_background_resolution, stop_background_resolution
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
    # A key of only whitespace counts as missing.
    key = SECRET_KEY or ""
    if not key.strip():
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
    start_background_resolution()
    await run_hourly_job(take_snapshots=False, send_reminders=False)
    if ENABLE_INTERNAL_SCHEDULER:
        start_hourly_scheduler()
        start_nightly_backup()
    else:
        warn_scheduler_off()
    yield
    stop_background_resolution()
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
if HTTPS_ONLY:
    # Outside the session middlewares: plain http is redirected before a session or cookie is touched.
    app.add_middleware(HttpsRedirectMiddleware, hsts_max_age=HSTS_MAX_AGE)
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


# Versioned static assets (/static/x.js?v=<STATIC_ASSET_VERSION>) never change under the same URL: a deploy
# bumps the version and so the URL. Let browsers / the WebView keep them for a year without revalidating,
# so a tab switch (a full page load) does not re-download or re-check ~15 CSS/JS files every time.
# Anything else under /static (no or old ?v=) is revalidated on every use (ETag -> cheap 304).
STATIC_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
STATIC_REVALIDATE_CACHE_CONTROL = "no-cache"


def static_cache_control(query_params) -> str:
    if query_params.get("v") == STATIC_ASSET_VERSION:
        return STATIC_IMMUTABLE_CACHE_CONTROL
    return STATIC_REVALIDATE_CACHE_CONTROL


@app.middleware("http")
async def static_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") and request.method in ("GET", "HEAD") and response.status_code in (200, 304):
        response.headers["Cache-Control"] = static_cache_control(request.query_params)
    return response


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


_COMMIT_ENV_VARS = ("GIT_SHA", "SOURCE_COMMIT", "DOKPLOY_COMMIT_SHA", "DOKPLOY_COMMIT_HASH")
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,40}")
# Written at image build time from the cloned .git (see Dockerfile); the env vars win over it.
_COMMIT_FILE = Path(__file__).resolve().parent.parent / "build-info" / "GIT_SHA"


def _short_commit(value: str) -> str:
    return value[:7].lower() if _COMMIT_RE.fullmatch(value) else "unknown"


def deployed_commit() -> str:
    """Short SHA of the deployed commit: first set commit env var, else the build file; 'unknown' if neither is valid."""
    for name in _COMMIT_ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return _short_commit(value)
    try:
        value = _COMMIT_FILE.read_text(encoding="ascii", errors="replace")[:100].strip()
    except OSError:
        return "unknown"
    return _short_commit(value) if value else "unknown"


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "commit": deployed_commit()})


app.include_router(pwa_router)
app.include_router(push_router)
app.include_router(auth_router)
app.include_router(unified_auth_router)
app.include_router(native_api_router)
app.include_router(dashboard_router)
app.include_router(amounts_router)
app.include_router(admin_users_router)
app.include_router(db_admin_router)
app.include_router(admin_categories_router)
app.include_router(mcp_router)
app.include_router(assets_router)
app.include_router(car_router)
app.include_router(profile_router)
app.include_router(debts_router)
app.include_router(expenses_router)
app.include_router(spends_router)
