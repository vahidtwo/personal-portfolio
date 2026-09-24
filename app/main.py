"""App entrypoint. Routes live in feature modules."""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin_users import router as admin_users_router
from app.auth_routes import router as auth_router
from app.config import DATA_DIR, ENABLE_INTERNAL_SCHEDULER, HTTPS_ONLY, SECRET_KEY
from app.dashboard import router as dashboard_router
from app.db import init_db
from app.db_admin import router as db_admin_router
from app.debts import router as debts_router
from app.expenses import router as expenses_router
from app.jobs import run_hourly_job
from app.mcp_http import router as mcp_router
from app.profile import router as profile_router
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
    await run_hourly_job(take_snapshots=False)
    if ENABLE_INTERNAL_SCHEDULER:
        start_hourly_scheduler()
    else:
        logger.info("Internal hourly scheduler disabled (use external cron + scripts/create_snapshot.py)")
    yield
    await stop_hourly_scheduler()


app = FastAPI(title="My Inventory", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key(),
    session_cookie="inventory_session",
    same_site="lax",
    https_only=HTTPS_ONLY,
    max_age=60 * 60 * 24 * 30,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/health")
async def health():
    return JSONResponse({"ok": True})


app.include_router(pwa_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_users_router)
app.include_router(db_admin_router)
app.include_router(mcp_router)
app.include_router(profile_router)
app.include_router(debts_router)
app.include_router(expenses_router)
app.include_router(spends_router)
