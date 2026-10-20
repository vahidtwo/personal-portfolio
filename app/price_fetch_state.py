"""Outcome of the last chande.net price fetch (manual refresh or scheduled job), with NO database change.

Stored as a tiny JSON file in DATA_DIR (the same volume as the SQLite DB), so it is shared by the web process
and an external cron (scripts/create_snapshot.py) and survives restarts. If the file can't be written (read-only
dir), the value is kept in this process only: it then resets on restart and isn't seen by other processes.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone

from app import config

logger = logging.getLogger(__name__)
STATE_FILE = "price_fetch_state.json"
_memory: dict | None = None


def _path():
    return config.DATA_DIR / STATE_FILE


def record(ok: bool, when: datetime | None = None) -> None:
    global _memory
    when = when or datetime.now(timezone.utc)
    _memory = {"ok": bool(ok), "at": when.astimezone(timezone.utc).isoformat()}
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, prefix=".pfs-")
        with os.fdopen(fd, "w") as f:
            json.dump(_memory, f)
        os.replace(tmp, _path())
    except OSError:
        logger.warning("price fetch state kept in memory only (DATA_DIR not writable)")


def last() -> tuple[bool, datetime] | None:
    """(ok, attempted_at UTC) of the most recent attempt, or None if nothing is known."""
    data = None
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = _memory
    if not isinstance(data, dict) or "at" not in data:
        return None
    try:
        at = datetime.fromisoformat(data["at"])
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return bool(data.get("ok")), at
