"""App entrypoint. Routes live in feature modules."""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.session_marker import SessionMarkerMiddleware
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
from app.scheduler import start_hourly_scheduler, stop_hourly_scheduler
from app.spends import router as spends_router
from app.web import BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _secret_key() -> str:
    if SECRET_KEY:
        return SECRET_KEY
    secret_path = DATA_DIR / "secret_key"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    generated = secrets.token_urlsafe(48)
    secret_path.write_text(generated, encoding="utf-8")
    logger.warning("SECRET_KEY was not set; generated %s", secret_path)
    return generated


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    validate_firebase_admin_at_startup()
    await run_hourly_job(take_snapshots=False)
    if ENABLE_INTERNAL_SCHEDULER:
        start_hourly_scheduler()
    else:
        logger.info("Internal hourly scheduler disabled (use external cron + scripts/create_snapshot.py)")
    yield
    await stop_hourly_scheduler()


app = FastAPI(title="My Inventory", lifespan=lifespan)
# Added first = runs inside SessionMiddleware, so it sees the final session (see app/session_marker.py).
app.add_middleware(SessionMarkerMiddleware, max_age=SESSION_MAX_AGE_SECONDS, https_only=HTTPS_ONLY)
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
