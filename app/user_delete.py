"""Admin batch delete of users with data (Vahid, Oct 13 2026).

Safeguards (Gorg/Boz spec):
- automatic SQLite online backup before every delete; no backup -> no delete
- confirm counts are recomputed on submit; any change aborts
- all selected users are deleted in ONE transaction (all or none)
- self and ADMIN_USERNAMES are refused server-side
- every delete is written to admin_audit_log in the same transaction
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

import app.security as security
from app.models import (
    AdminAuditLog, DailySpend, Debt, Holding, MonthlyExpense, PortfolioSnapshot, PushDeviceToken,
    SpendCategory, User,
)

COUNT_TABLES: tuple[tuple[str, str], ...] = (
    ("portfolio_snapshots", "اسنپ‌شات"),
    ("holdings", "دارایی"),
    ("debts", "بدهی/قسط"),
    ("monthly_expenses", "هزینه ماهانه"),
    ("daily_spends", "خرج روزانه"),
    ("push_device_tokens", "توکن اعلان"),
    ("spend_categories_custom", "دسته‌بندی شخصی"),
    ("spend_categories_seed", "دسته‌بندی پیش‌فرض"),
)
_MODELS = {
    "portfolio_snapshots": PortfolioSnapshot, "holdings": Holding, "debts": Debt,
    "monthly_expenses": MonthlyExpense, "daily_spends": DailySpend, "push_device_tokens": PushDeviceToken,
}
BACKUP_NAME_RE = re.compile(r"^predelete-\d{8}-\d{6}-[0-9a-f]{8}\.db$")


class DeleteRefused(Exception):
    """Delete was not run; message is shown to the admin (Persian)."""


def count_user_rows(db: Session, user_id: int) -> dict[str, int]:
    counts = {name: db.query(m.id).filter(m.user_id == user_id).count() for name, m in _MODELS.items()}
    q = db.query(SpendCategory.id).filter(SpendCategory.user_id == user_id)
    counts["spend_categories_custom"] = q.filter(SpendCategory.is_seed.is_(False)).count()
    counts["spend_categories_seed"] = q.filter(SpendCategory.is_seed.is_(True)).count()
    return counts


def protected_reason(target: User, actor: User) -> str | None:
    if target.id == actor.id:
        return "نمی‌توانید حساب خودتان را حذف کنید."
    if security.normalize_username(target.username) in security.ADMIN_USERNAMES:
        return f"حساب ادمین «{target.username}» حذف نمی‌شود."
    return None


def new_backup_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"predelete-{ts}-{secrets.token_hex(4)}.db"


def backup_dir() -> Path:
    from app.config import DATA_DIR
    return Path(DATA_DIR) / "backups"


def make_backup(db: Session, name: str) -> Path:
    """Online backup via sqlite3 backup API. Raises on any failure."""
    if not BACKUP_NAME_RE.match(name):
        raise ValueError("bad backup name")
    src_path = db.get_bind().url.database
    if not src_path or src_path == ":memory:":
        raise RuntimeError("database is not a file")
    folder = backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if dest.exists():
        raise FileExistsError(str(dest))
    tmp = folder / (name + ".part")
    src = sqlite3.connect(src_path)
    try:
        out = sqlite3.connect(tmp)
        try:
            src.backup(out)
            if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup integrity check failed")
        finally:
            out.close()
    finally:
        src.close()
    os.chmod(tmp, 0o600)
    os.replace(tmp, dest)
    return dest


def delete_users(
    db: Session, actor: User, user_ids: list[int], expected: dict[int, dict[str, int]], backup_name: str,
) -> dict[int, dict[str, int]]:
    """Validate, back up, then delete every user in one transaction. Returns deleted counts."""
    ids = sorted(set(user_ids))
    if not ids:
        raise DeleteRefused("هیچ کاربری انتخاب نشده است.")
    targets = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    if set(targets) != set(ids):
        raise DeleteRefused("برخی کاربران دیگر وجود ندارند؛ دوباره انتخاب کنید.")
    for u in targets.values():
        reason = protected_reason(u, actor)
        if reason:
            raise DeleteRefused(reason)
    current = {uid: count_user_rows(db, uid) for uid in ids}
    if {int(k): v for k, v in expected.items()} != current:
        raise DeleteRefused("داده‌های کاربران از زمان تأیید تغییر کرده است؛ دوباره بررسی کنید.")
    db.rollback()  # end any read transaction so the backup sees a consistent, committed DB

    try:
        make_backup(db, backup_name)
    except Exception as exc:  # noqa: BLE001
        raise DeleteRefused(f"پشتیبان‌گیری ناموفق بود؛ هیچ کاربری حذف نشد. ({type(exc).__name__})") from exc

    usernames = {uid: targets[uid].username for uid in ids}
    actor_name = actor.username
    try:
        # Re-check inside the delete transaction (nothing changed since the backup).
        if {uid: count_user_rows(db, uid) for uid in ids} != current:
            raise DeleteRefused("داده‌ها هنگام حذف تغییر کرد؛ هیچ کاربری حذف نشد.")
        for uid in ids:
            for model in (DailySpend, PortfolioSnapshot, Holding, Debt, MonthlyExpense, PushDeviceToken):
                db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
            db.query(SpendCategory).filter(
                SpendCategory.user_id == uid, SpendCategory.parent_id.is_not(None)
            ).delete(synchronize_session=False)
            db.query(SpendCategory).filter(SpendCategory.user_id == uid).delete(synchronize_session=False)
            db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        db.add(AdminAuditLog(
            actor_username=actor_name,
            action="delete_users",
            targets_json=json.dumps([{"id": uid, "username": usernames[uid]} for uid in ids], ensure_ascii=False),
            counts_json=json.dumps({str(k): v for k, v in current.items()}),
            backup_filename=backup_name,
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return current
