"""Nightly SQLite backups of the app database and the login rate-limit database.

- Copies are taken with the sqlite3 online backup API from a read-only (mode=ro) connection, so the
  live database is never written to and a running app keeps working during the copy.
- Each copy is gzipped into DATA_DIR/backups/ (dir 0700, files 0600) and kept for RETENTION_DAYS.
- Only files named nightly-* are pruned; other backups in the same folder are left alone.

CLI:
    python -m app.backup run            # take a backup of every database now
    python -m app.backup restore-check  # open the newest backup of each database, run PRAGMA integrity_check
"""
from __future__ import annotations

import asyncio
import fcntl
import gzip
import logging
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

RETENTION_DAYS = 14
TEHRAN = ZoneInfo("Asia/Tehran")
RUN_AT = (3, 30)  # local Tehran time
PREFIX = "nightly-"
NAME_RE = re.compile(r"^nightly-(?P<db>[a-z_]+)-(?P<ts>\d{8}-\d{6})\.sqlite\.gz$")


def data_dir() -> Path:
    from app.config import DATA_DIR

    return Path(DATA_DIR)


def backup_dir() -> Path:
    return data_dir() / "backups"


def _main_db_path() -> Path | None:
    from app.config import DATABASE_URL

    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL[len("sqlite:///"):])


def databases() -> dict[str, Path]:
    """Label -> path of each SQLite file to back up (only files that exist)."""
    from app.rate_limit import DB_NAME

    found: dict[str, Path] = {}
    main = _main_db_path()
    if main is not None and main.is_file():
        found["inventory"] = main
    rl = data_dir() / DB_NAME
    if rl.is_file():
        found["rate_limit"] = rl
    return found


def _ensure_dir() -> Path:
    folder = backup_dir()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def backup_one(label: str, src: Path, now: datetime | None = None) -> Path:
    """Online backup of `src` into a gzipped file; the source is opened read-only."""
    folder = _ensure_dir()
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    out = folder / f"{PREFIX}{label}-{ts}.sqlite.gz"
    fd, tmp_name = tempfile.mkstemp(dir=folder, prefix=".bk-", suffix=".sqlite")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(tmp)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        part = out.with_name(out.name + ".part")
        with tmp.open("rb") as raw, gzip.open(part, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(raw, gz)
        os.chmod(part, 0o600)
        os.replace(part, out)
    finally:
        tmp.unlink(missing_ok=True)
        out.with_name(out.name + ".part").unlink(missing_ok=True)
    return out


def prune(now: float | None = None) -> list[Path]:
    folder = backup_dir()
    if not folder.is_dir():
        return []
    cutoff = (now or time.time()) - RETENTION_DAYS * 86400
    removed = []
    for path in folder.iterdir():
        if NAME_RE.match(path.name) and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def run_backup() -> list[Path]:
    made = [backup_one(label, path) for label, path in databases().items()]
    prune()
    return made


def latest(label: str) -> Path | None:
    folder = backup_dir()
    if not folder.is_dir():
        return None
    names = sorted(
        (p for p in folder.iterdir() if (m := NAME_RE.match(p.name)) and m["db"] == label),
        key=lambda p: NAME_RE.match(p.name)["ts"],
    )
    return names[-1] if names else None


def integrity_check(backup: Path) -> str:
    """Unzip the backup to a temp file, open it and return PRAGMA integrity_check ("ok" when healthy)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plain = Path(tmpdir) / "check.sqlite"
        with gzip.open(backup, "rb") as gz, plain.open("wb") as raw:
            shutil.copyfileobj(gz, raw)
        conn = sqlite3.connect(f"{plain.as_uri()}?mode=ro", uri=True)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
        finally:
            conn.close()
    return "\n".join(str(r[0]) for r in rows)


def restore_check(labels=("inventory", "rate_limit")) -> dict[str, str]:
    results = {}
    for label in labels:
        newest = latest(label)
        results[label] = "missing" if newest is None else integrity_check(newest)
    return results


# ---- in-app nightly schedule ---------------------------------------------------------------

def seconds_until_next_run(now: datetime | None = None) -> float:
    local = (now or datetime.now(timezone.utc)).astimezone(TEHRAN)
    target = local.replace(hour=RUN_AT[0], minute=RUN_AT[1], second=0, microsecond=0)
    if target <= local:
        target = (local + timedelta(days=1)).replace(hour=RUN_AT[0], minute=RUN_AT[1], second=0, microsecond=0)
    return (target - local).total_seconds()


def run_backup_locked() -> list[Path] | None:
    """Run the backup unless another process (e.g. a second worker) is already doing it."""
    folder = _ensure_dir()
    with (folder / ".nightly.lock").open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Nightly backup already running elsewhere; skipped")
            return None
        return run_backup()


async def nightly_worker() -> None:
    while True:
        await asyncio.sleep(seconds_until_next_run())
        try:
            made = await asyncio.to_thread(run_backup_locked)
            if made is not None:
                logger.info("Nightly backup done: %s", ", ".join(p.name for p in made))
        except Exception:
            logger.exception("Nightly backup failed")


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO)
    cmd = argv[0] if argv else ""
    if cmd == "run":
        for path in run_backup():
            print(path)
        return 0
    if cmd == "restore-check":
        results = restore_check()
        for label, result in results.items():
            print(f"{label}: {result}")
        return 0 if all(r == "ok" for r in results.values()) else 1
    print(__doc__.split("CLI:")[1].strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
