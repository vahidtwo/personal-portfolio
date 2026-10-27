"""Migration 0004 (users.sanjeh_status): additive, idempotent, existing rows untouched.

Runs on a FAKE database built at revision 0003 with fake users/holdings, then on a byte copy of it.
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


def _alembic(db, action, rev):
    subprocess.run([sys.executable, "-c", ALEMBIC, str(db), action, rev], check=True,
                   env={"DATA_DIR": str(db.parent), "PATH": "/usr/bin:/bin"})


def _dump(db):
    c = sqlite3.connect(db)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' and name != 'alembic_version' order by name"):
        cols = [r[1] for r in c.execute(f"pragma table_info({t})") if r[1] != "sanjeh_status"]
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


def _fake_db_at_0003(tmp_path):
    db = tmp_path / "fake.db"
    _alembic(db, "upgrade", "0003_admin_audit_log")
    c = sqlite3.connect(db)
    cols = {r[1] for r in c.execute("pragma table_info(users)")}
    assert "sanjeh_status" not in cols
    _insert(c, "users", id=1, username="fake_a", car_toman=2850000000, car_count=2, sanjeh_token="FAKE-TOKEN-1",
            car_fetched_at="2026-10-01 10:00:00")
    _insert(c, "users", id=2, username="fake_b", car_toman=0, car_count=0, btc=0.5)
    c.execute("insert into holdings (user_id, asset_key, quantity, updated_at) values (1, 'car_count', 2, '2026-10-01 10:00:00'), (2, 'btc', 0.5, '2026-10-01 10:00:00')")
    c.commit()
    c.close()
    return db


def test_0004_on_copy_of_fake_db_adds_only_nullable_column_and_keeps_data(tmp_path):
    original = _fake_db_at_0003(tmp_path)
    copy = tmp_path / "copy.db"
    shutil.copyfile(original, copy)
    before = _dump(copy)
    _alembic(copy, "upgrade", "head")
    c = sqlite3.connect(copy)
    info = {r[1]: r for r in c.execute("pragma table_info(users)")}
    assert info["sanjeh_status"][2].upper() == "VARCHAR(16)" and info["sanjeh_status"][3] == 0  # nullable
    assert c.execute("select id, sanjeh_status from users order by id").fetchall() == [(1, None), (2, None)]
    assert c.execute("select version_num from alembic_version").fetchone()[0] == "0004_sanjeh_status"
    c.close()
    assert _dump(copy) == before  # every other table, column and row identical
    assert _dump(original) == before  # the original fake DB was never touched


def test_0004_is_idempotent_and_downgrade_removes_only_the_column(tmp_path):
    db = _fake_db_at_0003(tmp_path)
    before = _dump(db)
    _alembic(db, "upgrade", "head")
    _alembic(db, "stamp", "0003_admin_audit_log")  # column already there: re-running must be a no-op
    _alembic(db, "upgrade", "head")
    assert _dump(db) == before
    _alembic(db, "downgrade", "0003_admin_audit_log")
    cols = {r[1] for r in sqlite3.connect(db).execute("pragma table_info(users)")}
    assert "sanjeh_status" not in cols and _dump(db) == before


def test_existing_null_status_reads_as_connected():
    from app.car_routes import car_state
    from app.models import User

    assert car_state(User(username="x", password_hash="h", sanjeh_token="FAKE")) == "connected"
    assert car_state(User(username="x", password_hash="h")) == "none"
