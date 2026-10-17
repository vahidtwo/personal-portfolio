"""Admin batch delete of users with data (Vahid, Oct 13 2026).

Safeguards (Gorg/Boz/Arab spec):
- the whole delete runs under ONE SQLite write lock (BEGIN IMMEDIATE): recount ->
  online backup (sqlite3 backup API, from the locking connection) -> delete -> audit row -> COMMIT
- no backup (error or not enough free disk) -> nothing is deleted
- counts shown on the confirm screen are recomputed under the lock; any change aborts
- all selected users are deleted in one transaction (all or none)
- self and ADMIN_USERNAMES are refused server-side
- backups: DATA_DIR/backups (dir 0700, files 0600); after a successful delete, files
  older than 30 days are pruned but the newest 10 are always kept
- restore one user: scripts/restore_user.py
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

import app.security as security
from app.models import User

KNOWN_LABELS: dict[str, str] = {
    "portfolio_snapshots": "اسنپ‌شات",
    "holdings": "دارایی",
    "debts": "بدهی/قسط",
    "monthly_expenses": "هزینه ماهانه",
    "daily_spends": "خرج روزانه",
    "push_device_tokens": "توکن اعلان",
    "spend_categories_custom": "دسته‌بندی شخصی",
    "spend_categories_seed": "دسته‌بندی پیش‌فرض",
    "monthly_incomes": "درآمد ماهانه",
}
BACKUP_NAME_RE = re.compile(r"^predelete-\d{8}-\d{6}-[0-9a-f]{8}\.db$")
BACKUP_KEEP_NEWEST = 10
BACKUP_MAX_AGE_DAYS = 30
DISK_MARGIN = 2  # need free space >= DISK_MARGIN * database size


class DeleteRefused(Exception):
    """Delete was not run; message is shown to the admin (Persian)."""


# ---- counting (generic over every table that has a user_id column) -------------

def _user_tables(conn) -> list[str]:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    out = []
    for t in tables:
        if t == "users":
            continue
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
        if "user_id" in cols:
            out.append(t)
    return out


def _sql_counts(conn, user_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in _user_tables(conn):
        if t == "spend_categories":
            counts["spend_categories_custom"] = conn.execute(
                "SELECT count(*) FROM spend_categories WHERE user_id=? AND NOT COALESCE(is_seed, 0)", (user_id,)).fetchone()[0]
            counts["spend_categories_seed"] = conn.execute(
                "SELECT count(*) FROM spend_categories WHERE user_id=? AND COALESCE(is_seed, 0)", (user_id,)).fetchone()[0]
        else:
            counts[t] = conn.execute(f'SELECT count(*) FROM "{t}" WHERE user_id=?', (user_id,)).fetchone()[0]
    return counts


class _SessionConn:
    """Tiny adapter so the same SQL helpers run on a Session (confirm screen)."""

    def __init__(self, db: Session):
        self.db = db

    def execute(self, sql, params=()):
        return self.db.connection().exec_driver_sql(sql, tuple(params))


def count_user_rows(db: Session, user_id: int) -> dict[str, int]:
    return _sql_counts(_SessionConn(db), user_id)


def count_labels(keys) -> list[tuple[str, str]]:
    return [(k, KNOWN_LABELS.get(k, k)) for k in keys]


# ---- protection ----------------------------------------------------------------

def _protected(target_id: int, target_username: str, actor_id: int) -> str | None:
    if target_id == actor_id:
        return "نمی‌توانید حساب خودتان را حذف کنید."
    if security.normalize_username(target_username) in security.ADMIN_USERNAMES:
        return f"حساب ادمین «{target_username}» حذف نمی‌شود."
    return None


def protected_reason(target: User, actor: User) -> str | None:
    return _protected(target.id, target.username, actor.id)


# ---- backups -------------------------------------------------------------------

def new_backup_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"predelete-{ts}-{secrets.token_hex(4)}.db"


def backup_dir() -> Path:
    from app.config import DATA_DIR
    return Path(DATA_DIR) / "backups"


def _ensure_backup_dir() -> Path:
    folder = backup_dir()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def _db_path_of(conn: sqlite3.Connection) -> str:
    for _seq, name, path in conn.execute("PRAGMA database_list"):
        if name == "main":
            return path
    return ""


def check_disk_space(db_path: str, folder: Path) -> None:
    db_size = os.path.getsize(db_path)
    free = shutil.disk_usage(folder).free
    if free < db_size * DISK_MARGIN:
        raise DeleteRefused(
            "فضای خالی دیسک برای پشتیبان‌گیری کافی نیست؛ هیچ کاربری حذف نشد."
        )


def _backup_from(conn: sqlite3.Connection, name: str) -> Path:
    """Online backup (sqlite3 backup API) taken while `conn` holds the BEGIN IMMEDIATE lock.

    SQLite refuses backup_step / VACUUM INTO on a connection that has an open write
    transaction (SQLITE_LOCKED / "cannot VACUUM from within a transaction"), so a second,
    read-only connection does the copy. The RESERVED lock held by `conn` still allows
    readers but blocks every other writer, and `conn` has written nothing yet, so the
    backup is exactly the state the delete runs against. The reader is closed before
    the caller deletes/commits.
    """
    if not BACKUP_NAME_RE.match(name):
        raise ValueError("bad backup name")
    db_path = _db_path_of(conn)
    if not db_path:
        raise RuntimeError("database is not a file")
    folder = _ensure_backup_dir()
    check_disk_space(db_path, folder)
    dest = folder / name
    if dest.exists():
        raise FileExistsError(str(dest))
    tmp = folder / (name + ".part")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        reader = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
        try:
            out = sqlite3.connect(tmp)
            try:
                reader.backup(out)
                _verify_backup(out)
            finally:
                out.close()
        finally:
            reader.close()
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest


def _verify_backup(out: sqlite3.Connection) -> None:
    """Backup must pass integrity_check before anything is deleted (else whole txn rolls back)."""
    res = out.execute("PRAGMA integrity_check").fetchone()[0]
    if res != "ok":
        raise RuntimeError(f"backup integrity check failed: {res}")
    if out.execute("SELECT count(*) FROM sqlite_master WHERE name='users'").fetchone()[0] != 1:
        raise RuntimeError("backup has no users table")


def prune_backups(now: float | None = None) -> list[str]:
    """Delete predelete-*.db older than 30 days, but always keep the newest 10."""
    folder = backup_dir()
    if not folder.is_dir():
        return []
    now = time.time() if now is None else now
    files = sorted(
        (p for p in folder.iterdir() if p.is_file() and BACKUP_NAME_RE.match(p.name)),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    removed = []
    for p in files[BACKUP_KEEP_NEWEST:]:
        if now - p.stat().st_mtime > BACKUP_MAX_AGE_DAYS * 86400:
            p.unlink()
            removed.append(p.name)
    return removed


def _raw_connect(db: Session) -> sqlite3.Connection:
    path = db.get_bind().url.database
    if not path or path == ":memory:":
        raise DeleteRefused("پایگاه داده فایل نیست.")
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _before_commit_hook(conn: sqlite3.Connection) -> None:
    """Test seam: runs inside the locked transaction right before COMMIT."""


def delete_users(
    db: Session, actor: User, user_ids: list[int], expected: dict[int, dict[str, int]], backup_name: str,
) -> dict[int, dict[str, int]]:
    """Validate, then under ONE SQLite write lock (BEGIN IMMEDIATE): recount, back up, delete, audit, commit."""
    ids = sorted(set(user_ids))
    if not ids:
        raise DeleteRefused("هیچ کاربری انتخاب نشده است.")
    if not BACKUP_NAME_RE.match(backup_name):
        raise DeleteRefused("نام فایل پشتیبان نامعتبر است.")
    actor_name = actor.username
    actor_id = actor.id
    db.rollback()  # release the session's read transaction before taking the write lock

    conn = _raw_connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")  # blocks every other writer until COMMIT/ROLLBACK
        try:
            q = ",".join("?" * len(ids))
            rows = conn.execute(f"SELECT id, username FROM users WHERE id IN ({q})", ids).fetchall()
            usernames = {r[0]: r[1] for r in rows}
            if set(usernames) != set(ids):
                raise DeleteRefused("برخی کاربران دیگر وجود ندارند؛ دوباره انتخاب کنید.")
            for uid, name in usernames.items():
                reason = _protected(uid, name, actor_id)
                if reason:
                    raise DeleteRefused(reason)
            current = {uid: _sql_counts(conn, uid) for uid in ids}
            if {int(k): v for k, v in expected.items()} != current:
                raise DeleteRefused("داده‌های کاربران از زمان تأیید تغییر کرده است؛ دوباره بررسی کنید.")
            try:
                _backup_from(conn, backup_name)
            except DeleteRefused:
                raise
            except Exception as exc:  # noqa: BLE001
                raise DeleteRefused(
                    f"پشتیبان‌گیری ناموفق بود؛ هیچ کاربری حذف نشد. ({type(exc).__name__})"
                ) from exc
            for uid in ids:
                conn.execute("DELETE FROM daily_spends WHERE user_id = ?", (uid,))
                for table in _user_tables(conn):
                    if table in ("users", "spend_categories", "daily_spends"):
                        continue
                    conn.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (uid,))
                conn.execute("DELETE FROM spend_categories WHERE user_id = ? AND parent_id IS NOT NULL", (uid,))
                conn.execute("DELETE FROM spend_categories WHERE user_id = ?", (uid,))
                conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            conn.execute(
                "INSERT INTO admin_audit_log (actor_username, action, targets_json, counts_json, backup_filename, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    actor_name, "delete_users",
                    json.dumps([{"id": uid, "username": usernames[uid]} for uid in ids], ensure_ascii=False),
                    json.dumps({str(k): v for k, v in current.items()}),
                    backup_name,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                ),
            )
            _before_commit_hook(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    try:
        prune_backups()
    except Exception:  # noqa: BLE001 - pruning must never undo a finished delete
        pass
    db.expire_all()
    return current
