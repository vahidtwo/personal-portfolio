from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager

from app.chande import fetch_chande_prices
from app.config import DATA_DIR
from app.db import SessionLocal
from app.models import MarketPrice
from app.portfolio import load_prices, snapshot_all_users

logger = logging.getLogger(__name__)
LOCK_PATH = DATA_DIR / "hourly.lock"


@contextmanager
def _job_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield True
    except BlockingIOError:
        yield False
    finally:
        handle.close()


def upsert_prices(prices) -> None:
    db = SessionLocal()
    try:
        for item in prices:
            row = db.get(MarketPrice, item.key)
            if row is None:
                row = MarketPrice(
                    symbol=item.key,
                    price_toman=item.price_toman,
                    source_updated_at=item.source_updated_at,
                    fetched_at=item.fetched_at,
                )
                db.add(row)
            else:
                row.price_toman = item.price_toman
                row.source_updated_at = item.source_updated_at
                row.fetched_at = item.fetched_at
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def run_hourly_job(take_snapshots: bool = True) -> None:
    with _job_lock() as acquired:
        if not acquired:
            logger.info("Hourly job already running; skip")
            return
        try:
            fetched = await fetch_chande_prices()
        except Exception:
            logger.exception("Failed to fetch prices from chande.net")
            return
        upsert_prices(fetched)
        if not take_snapshots:
            return
        db = SessionLocal()
        try:
            prices = load_prices(db)
            count = snapshot_all_users(db, prices)
            db.commit()
            logger.info("Stored hourly snapshots for %s users", count)
        except Exception:
            db.rollback()
            logger.exception("Failed to store portfolio snapshots")
        finally:
            db.close()
