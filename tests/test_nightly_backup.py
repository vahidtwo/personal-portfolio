"""Nightly SQLite backups (app/backup.py) against temporary databases."""
from __future__ import annotations

import gzip
import hashlib
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import pytest


@pytest.fixture()
def bk(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'inventory.db'}")
    for name in list(sys.modules):
        if name == "app.backup" or name == "app.config":
            del sys.modules[name]
    import app.backup as backup

    main = sqlite3.connect(tmp_path / "inventory.db")
    main.execute("PRAGMA journal_mode=WAL")
    main.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    main.executemany("INSERT INTO t (name) VALUES (?)", [(f"fake-{i}",) for i in range(200)])
    main.commit()
    rl = sqlite3.connect(tmp_path / "rate_limit.sqlite")
    rl.execute("PRAGMA journal_mode=WAL")
    rl.execute("CREATE TABLE hits (key TEXT, ts REAL)")
    rl.execute("INSERT INTO hits VALUES ('ip:192.0.2.1', 1.0)")
    rl.commit()
    yield backup, tmp_path, main
    main.close()
    rl.close()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_backup_both_dbs_gzipped_and_readable(bk):
    backup, tmp, live = bk
    made = backup.run_backup()
    names = sorted(p.name for p in made)
    assert len(names) == 2 and names[0].startswith("nightly-inventory-") and names[1].startswith("nightly-rate_limit-")
    for p in made:
        assert p.parent == tmp / "backups" and p.suffix == ".gz"
        assert oct(p.stat().st_mode & 0o777) == "0o600"
        with gzip.open(p) as gz:
            assert gz.read(16) == b"SQLite format 3\x00"
    assert oct((tmp / "backups").stat().st_mode & 0o777) == "0o700"
    assert not [p for p in (tmp / "backups").iterdir() if p.name.startswith(".bk-") or p.name.endswith(".part")]


def test_backup_is_read_only_against_live_db(bk):
    backup, tmp, live = bk
    live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = _digest(tmp / "inventory.db")
    os.chmod(tmp / "inventory.db", 0o444)
    try:
        backup.backup_one("inventory", tmp / "inventory.db")
    finally:
        os.chmod(tmp / "inventory.db", 0o644)
    assert _digest(tmp / "inventory.db") == before


def test_backup_includes_uncheckpointed_wal_rows(bk):
    backup, tmp, live = bk
    live.execute("INSERT INTO t (name) VALUES ('fake-after-wal')")
    live.commit()
    out = backup.backup_one("inventory", tmp / "inventory.db")
    assert backup.integrity_check(out) == "ok"
    plain = tmp / "plain.sqlite"
    plain.write_bytes(gzip.decompress(out.read_bytes()))
    c = sqlite3.connect(plain)
    assert c.execute("SELECT count(*) FROM t").fetchone()[0] == 201
    c.close()


def test_restore_check_uses_latest_and_flags_corruption(bk):
    backup, tmp, live = bk
    old = backup.backup_one("inventory", tmp / "inventory.db", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    backup.backup_one("rate_limit", tmp / "rate_limit.sqlite")
    assert backup.latest("inventory") == old
    assert backup.restore_check() == {"inventory": "ok", "rate_limit": "ok"}
    newer = backup.backup_one("inventory", tmp / "inventory.db", now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    raw = bytearray(gzip.decompress(newer.read_bytes()))
    raw[4096 + 100: 4096 + 600] = b"\xff" * 500
    newer.write_bytes(gzip.compress(bytes(raw)))
    assert backup.latest("inventory") == newer
    assert backup.restore_check()["inventory"] != "ok"
    assert backup.main(["restore-check"]) == 1


def test_restore_check_missing(bk):
    backup, tmp, live = bk
    assert backup.restore_check() == {"inventory": "missing", "rate_limit": "missing"}


def test_prune_keeps_14_days_and_other_files(bk):
    backup, tmp, live = bk
    folder = tmp / "backups"
    folder.mkdir(mode=0o700)
    old = folder / "nightly-inventory-20250101-000000.sqlite.gz"
    fresh = folder / "nightly-inventory-20250120-000000.sqlite.gz"
    other = folder / "predelete-20250101-000000-abcd1234.db"
    for p in (old, fresh, other):
        p.write_bytes(b"x")
    now = time.time()
    os.utime(old, (now - 15 * 86400, now - 15 * 86400))
    os.utime(fresh, (now - 13 * 86400, now - 13 * 86400))
    os.utime(other, (now - 400 * 86400, now - 400 * 86400))
    assert backup.prune(now) == [old]
    assert fresh.exists() and other.exists()


def test_next_run_is_0330_tehran(bk):
    backup, *_ = bk
    # 2026-10-31 00:00 UTC = 03:30 Tehran -> exactly one day later
    assert backup.seconds_until_next_run(datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)) == 86400
    # 2026-10-30 23:00 UTC = 02:30 Tehran -> one hour
    assert backup.seconds_until_next_run(datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)) == 3600


def test_locked_run_skips_when_busy(bk):
    import fcntl

    backup, tmp, live = bk
    folder = tmp / "backups"
    folder.mkdir(mode=0o700)
    with (folder / ".nightly.lock").open("a+") as h:
        fcntl.flock(h.fileno(), fcntl.LOCK_EX)
        assert backup.run_backup_locked() is None
    assert len(backup.run_backup_locked()) == 2
