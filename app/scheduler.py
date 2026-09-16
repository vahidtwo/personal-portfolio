from __future__ import annotations

import asyncio
import logging

from app.config import PRICE_REFRESH_HOURS
from app.jobs import run_hourly_job

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


async def _hourly_worker() -> None:
    """Run full hourly job on a fixed interval in the same event loop as FastAPI."""
    period = max(1, PRICE_REFRESH_HOURS) * 3600
    while True:
        await asyncio.sleep(period)
        logger.info("Scheduled hourly job triggered (every %s h)", PRICE_REFRESH_HOURS)
        try:
            await run_hourly_job(take_snapshots=True)
        except Exception:
            logger.exception("Scheduled hourly job failed")


def start_hourly_scheduler() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_hourly_worker(), name="hourly-portfolio")
    logger.info("Hourly scheduler started (interval=%s h)", PRICE_REFRESH_HOURS)


async def stop_hourly_scheduler() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
    logger.info("Hourly scheduler stopped")
