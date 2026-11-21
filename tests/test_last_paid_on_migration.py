"""Migration 0010 (debts.last_paid_on): additive, idempotent, existing rows stay NULL.

Runs on a fake database built at revision 0009 with a debt row, then on a byte copy of it.
"""
import shutil
import sqlite3
import subprocess
import sys

ALEMBIC = """
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
cfg = Config(); cfg.set_main_option("script_location", "app/migrations")
eng = create_engine("sqlite:///" + sys.argv[1])
with eng.begin() as conn:
    cfg.attributes["connection"] = conn
    getattr(command, sys.argv[2])(cfg, sys.argv[3])
"""

PREV = "0009_default_group_icons"
REV = "0010_debt_last_paid_on"


def _alembic(db, action, rev):
    subprocess.run([sys.executable, "-c", ALEMBIC, str(db), action, rev], check=True,
                   env={"DATA_DIR": str(db.parent), "PATH": "/usr/bin:/bin"})


def _dump(db):
    c = sqlite3.connect(db)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' and name != 'alembic_version' order by name"):
        cols = [r[1] for r in c.execute(f"pragma table_info({t})") if r[1] != "last_paid_on"]
        out[t] = (cols, sorted(c.execute(f"select {','.join(cols)} from {t}").fetchall(), key=repr))
    c.close()
    return out


def _insert(c, table, **values):
    """Insert a fake row, filling any other NOT NULL column (no default) with a fake value of its type."""
    for _, name, typ, notnull, default, pk in c.execute(f"pragma table_info({table})").fetchall():
        if name in values or not notnull or default is not None or pk:
            continue
        t = (typ or "").upper()
        values[name] = 0 if any(k in t for k in ("INT", "NUM", "DEC", "BOOL", "FLOAT", "REAL")) else (
            "2026-01-01 00:00:00" if ("DATE" in t or "TIME" in t) else f"fake-{name}")
    keys = ",".join(values)
    c.execute(f"insert into {table} ({keys}) values ({','.join('?' * len(values))})", tuple(values.values()))


def _fake_db_at_0009(tmp_path):
    db = tmp_path / "fake.db"
    _alembic(db, "upgrade", PREV)
    c = sqlite3.connect(db)
    cols = {r[1] for r in c.execute("pragma table_info(debts)")}
    assert "last_paid_on" not in cols
    _insert(c, "users", id=1, username="fake_a")
    _insert(c, "debts", id=1, user_id=1, title="وام موجود", monthly_toman=2000000, months_left=5,
            due_year=1405, due_month=8, due_day=20)
    _insert(c, "debts", id=2, user_id=1, title="تمام", monthly_toman=700000, months_left=0,
            due_year=1405, due_month=7, due_day=5)
    c.commit()
    c.close()
    return db


def test_0010_on_copy_of_fake_db_adds_only_nullable_column_and_keeps_data(tmp_path):
    original = _fake_db_at_0009(tmp_path)
    copy = tmp_path / "copy.db"
    shutil.copyfile(original, copy)
    before = _dump(copy)
    _alembic(copy, "upgrade", REV)
    c = sqlite3.connect(copy)
    info = {r[1]: r for r in c.execute("pragma table_info(debts)")}
    typ = (info["last_paid_on"][2] or "").upper()
    assert typ in {"DATE", "DATETIME", ""} and info["last_paid_on"][3] == 0  # nullable
    assert c.execute("select id, last_paid_on from debts order by id").fetchall() == [(1, None), (2, None)]
    assert c.execute("select version_num from alembic_version").fetchone()[0] == REV
    c.close()
    assert _dump(copy) == before  # every other table, column and row identical
    assert _dump(original) == before  # the original fake DB was never touched


def test_0010_is_idempotent_and_downgrade_removes_only_the_column(tmp_path):
    db = _fake_db_at_0009(tmp_path)
    before = _dump(db)
    _alembic(db, "upgrade", REV)
    _alembic(db, "stamp", PREV)  # column already there: re-running must be a no-op
    _alembic(db, "upgrade", REV)
    assert _dump(db) == before
    _alembic(db, "downgrade", PREV)
    cols = {r[1] for r in sqlite3.connect(db).execute("pragma table_info(debts)")}
    assert "last_paid_on" not in cols and _dump(db) == before
