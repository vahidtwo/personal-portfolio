#!/usr/bin/env python3
"""Fetch market prices from chande.net and create portfolio snapshots for all users."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import init_db
from app.jobs import create_snapshots, run_hourly_job

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="به‌روزرسانی قیمت بازار و ثبت اسنپ‌شات پرتفوی همه کاربران",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="اسنپ‌شات با قیمت‌های فعلی دیتابیس (بدون دریافت از چنده)",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="فقط به‌روزرسانی قیمت؛ بدون اسنپ‌شات",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    init_db()

    if args.fetch_only and args.skip_fetch:
        logger.error("نمی‌توان همزمان --fetch-only و --skip-fetch را استفاده کرد")
        return 2

    if args.fetch_only:
        await run_hourly_job(take_snapshots=False)
        logger.info("قیمت‌ها به‌روز شد")
        return 0

    if args.skip_fetch:
        count = create_snapshots()
        logger.info("اسنپ‌شات برای %s کاربر ثبت شد", count)
        return 0

    await run_hourly_job(take_snapshots=True)
    logger.info("قیمت‌ها به‌روز شد و اسنپ‌شات ثبت شد")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:
        logger.exception("خطا در ایجاد اسنپ‌شات")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
