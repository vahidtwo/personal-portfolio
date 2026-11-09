"""Restore ONE deleted user (and all their rows) from a pre-delete backup into the live DB.

Usage (inside the container, or anywhere with access to the DB file):

    python scripts/restore_user.py <backup.db> <user_id> [--db /app/data/inventory.db] [--dry-run]

    # prod example:
    docker exec -it <container> python scripts/restore_user.py \\
        /app/data/backups/predelete-20261013-111500-1a2b3c4d.db 17

What it does, in ONE transaction (BEGIN IMMEDIATE; all or nothing):
- refuses if the user id OR username already exists in the live DB
- copies the users row with its original id
- copies every table in the backup that has a user_id column (holdings, snapshots,
  debts, monthly expenses, daily spends, push tokens, ...), keeping original ids
- categories are global in the live DB: each category the user's spends use is matched
  to a live category (same slug, else same parent and name) and the spends are pointed
  to it; a category with no match is added to the global list. An older backup with
  per-user categories works the same way.
- only columns present in both DBs are copied; aborts if any row id already exists
- runs PRAGMA foreign_key_check and integrity_check before COMMIT
Take a fresh backup of the live DB before running it on prod.
Approach based on ~/incident/restore_users.py (Oct 13 2026).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys


def _user_tables(conn: sqlite3.Connection, schema: str) -> list[str]:
    names = [r[0] for r in conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return [t for t in names if t != "users"
            and "user_id" in {r[1] for r in conn.execute(f'PRAGMA {schema}.table_info("{t}")')}]


def _cols(conn, schema, table):
    return [r[1] for r in conn.execute(f'PRAGMA {schema}.table_info("{table}")')]


def _name_key(name):
    text = (name or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u200c", "")
    return " ".join(text.split()).casefold()


def _live_category(conn, slug, name, parent_id):
    if slug:
        row = conn.execute("SELECT id FROM main.spend_categories WHERE slug=?", (slug,)).fetchone()
        if row:
            return row[0]
    key = _name_key(name)
    for cid, other in conn.execute(
            "SELECT id, name FROM main.spend_categories WHERE parent_id IS ? ORDER BY archived, id", (parent_id,)):
        if _name_key(other) == key:
            return cid
    taken = slug and conn.execute("SELECT 1 FROM main.spend_categories WHERE slug=?", (slug,)).fetchone()
    conn.execute(
        "INSERT INTO main.spend_categories (parent_id, name, name_key, slug, is_seed, sort_order, archived, created_at) "
        "VALUES (?, ?, ?, ?, 0, 0, 0, datetime('now'))",
        (parent_id, name, key, None if taken else slug))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _map_categories(conn, user_id, done) -> dict[int, int]:
    """backup category id -> live global category id, for every category the user's backup spends use."""
    if "user_id" in _cols(conn, "main", "spend_categories"):
        raise SystemExit("live DB still has per-user categories; run the app migrations first")
    before = conn.execute("SELECT count(*) FROM main.spend_categories").fetchone()[0]
    used = [r[0] for r in conn.execute(
        "SELECT DISTINCT category_id FROM bk.daily_spends WHERE user_id=?", (user_id,))]
    mapping: dict[int, int] = {}
    for cid in used:
        row = conn.execute("SELECT parent_id, name, slug FROM bk.spend_categories WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise SystemExit(f"backup spend category {cid} is missing")
        parent_live = None
        if row[0] is not None:
            parent = conn.execute("SELECT name, slug FROM bk.spend_categories WHERE id=?", (row[0],)).fetchone()
            parent_live = _live_category(conn, parent[1], parent[0], None)
        mapping[cid] = _live_category(conn, row[2], row[1], parent_live)
    added = conn.execute("SELECT count(*) FROM main.spend_categories").fetchone()[0] - before
    if added:
        done["spend_categories"] = added
    return mapping


def _copy_spends(conn, user_id, mapping, done) -> None:
    cols = [c for c in _cols(conn, "bk", "daily_spends") if c in set(_cols(conn, "main", "daily_spends"))]
    rows = conn.execute(
        f'SELECT {",".join(cols)} FROM bk.daily_spends WHERE user_id=? ORDER BY rowid', (user_id,)).fetchall()
    at = cols.index("category_id")
    for r in rows:
        r = list(r)
        r[at] = mapping[r[at]]
        conn.execute(f'INSERT INTO main.daily_spends ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})', r)
    done["daily_spends"] = len(rows)


def restore_user(backup: str, user_id: int, db_path: str, dry_run: bool = False) -> dict[str, int]:
    if not os.path.isfile(backup):
        raise SystemExit(f"backup not found: {backup}")
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
    try:
        conn.execute("ATTACH DATABASE ? AS bk", (backup,))
        conn.execute("BEGIN IMMEDIATE")
        try:
            src = conn.execute("SELECT username FROM bk.users WHERE id=?", (user_id,)).fetchone()
            if src is None:
                raise SystemExit(f"user id {user_id} not in backup")
            username = src[0]
            if conn.execute("SELECT 1 FROM main.users WHERE id=?", (user_id,)).fetchone():
                raise SystemExit(f"user id {user_id} already exists in live DB; refusing")
            if conn.execute("SELECT 1 FROM main.users WHERE lower(username)=lower(?)", (username,)).fetchone():
                raise SystemExit(f"username {username!r} already exists in live DB; refusing")
            live_tables = set(_user_tables(conn, "main"))
            done: dict[str, int] = {}

            def copy(table: str, where: str):
                cols = [c for c in _cols(conn, "bk", table) if c in set(_cols(conn, "main", table))]
                cl = ",".join(f'"{c}"' for c in cols)
                n = conn.execute(
                    f'INSERT INTO main."{table}" ({cl}) SELECT {cl} FROM bk."{table}" WHERE {where} ORDER BY rowid',
                    (user_id,)).rowcount
                done[table] = done.get(table, 0) + n

            copy("users", "id=?")
            category_map = _map_categories(conn, user_id, done)
            for t in _user_tables(conn, "bk"):
                if t == "spend_categories":
                    continue
                if t == "daily_spends" and t in live_tables:
                    _copy_spends(conn, user_id, category_map, done)
                    continue
                if t not in live_tables:
                    print(f"skip {t}: not in live DB", file=sys.stderr)
                    continue
                copy(t, "user_id=?")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise SystemExit("foreign_key_check failed; rolled back")
            if conn.execute("PRAGMA main.integrity_check").fetchone()[0] != "ok":
                raise SystemExit("integrity_check failed; rolled back")
            conn.execute("ROLLBACK" if dry_run else "COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return done


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("backup")
    p.add_argument("user_id", type=int)
    default_db = os.path.join(os.environ.get("DATA_DIR", "/app/data"), "inventory.db")
    p.add_argument("--db", default=default_db)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    done = restore_user(a.backup, a.user_id, a.db, a.dry_run)
    for t, n in done.items():
        print(f"{t}: {n}")
    print("DRY RUN, rolled back" if a.dry_run else "restored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
