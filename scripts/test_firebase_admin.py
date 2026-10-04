#!/usr/bin/env python3
"""Validate Firebase Admin env vars and run an FCM dry-run send."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.firebase_push import FirebaseAdminConfigError, dry_run_firebase_message, get_firebase_admin

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        get_firebase_admin()
        logger.info("Firebase Admin initialized from environment variables")
        dry_run_firebase_message()
        logger.info("FCM dry-run succeeded (credentials accepted by Firebase)")
        return 0
    except FirebaseAdminConfigError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:
        logger.exception("Firebase Admin dry-run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
