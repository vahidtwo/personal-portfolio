from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager

from app.chande import fetch_chande_prices
from app.config import DATA_DIR
from app.db import SessionLocal
from app.models import MarketPrice, User, utcnow
from app.portfolio import load_prices, snapshot_all_users, snapshot_user
from app.sanjeh import SanjehAuthError, fetch_sanjeh_portfolio

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
        await refresh_all_sanjeh_cars()
        if not take_snapshots:
            return
        try:
            count = create_snapshots()
            logger.info("Stored hourly snapshots for %s users", count)
        except Exception:
            logger.exception("Failed to store portfolio snapshots")


async def refresh_user_sanjeh_car(user: User) -> None:
    if not user.sanjeh_token:
        user.car_toman = 0
        user.car_count = 0
        user.car_fetched_at = None
        return
    portfolio = await fetch_sanjeh_portfolio(user.sanjeh_token)
    user.car_toman = portfolio.total_toman
    user.car_count = portfolio.car_count
    user.car_fetched_at = utcnow()


async def refresh_all_sanjeh_cars() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.sanjeh_token.isnot(None), User.sanjeh_token != "").all()
        for user in users:
            try:
                await refresh_user_sanjeh_car(user)
            except SanjehAuthError:
                logger.warning("Invalid Sanjeh token for user %s", user.id)
            except Exception:
                logger.exception("Failed to refresh Sanjeh car value for user %s", user.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def refresh_prices_and_snapshot_user(user_id: int) -> None:
    """Refresh market prices when possible, then store one snapshot for this user."""
    try:
        fetched = await fetch_chande_prices()
        upsert_prices(fetched)
    except Exception:
        logger.exception("Price fetch failed; snapshot will use stored prices")
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        if user.sanjeh_token:
            try:
                await refresh_user_sanjeh_car(user)
            except SanjehAuthError:
                logger.warning("Invalid Sanjeh token for user %s", user.id)
            except Exception:
                logger.exception("Failed to refresh Sanjeh car for user %s", user.id)
        prices = load_prices(db)
        if not prices:
            logger.warning("No market prices in database; skipped snapshot for user %s", user_id)
            return
        snapshot_user(db, user, prices, utcnow())
        db.commit()
        logger.info("Snapshot stored for user %s after holdings change", user_id)
    except Exception:
        db.rollback()
        logger.exception("Failed to store snapshot for user %s", user_id)
    finally:
        db.close()


def create_snapshots() -> int:
    """Record current portfolio totals for every user using prices in the database."""
    db = SessionLocal()
    try:
        prices = load_prices(db)
        if not prices:
            raise RuntimeError("هیچ قیمت بازاری در پایگاه داده نیست؛ ابتدا قیمت را به‌روز کنید")
        count = snapshot_all_users(db, prices)
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
