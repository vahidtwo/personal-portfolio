import json
import os
import sqlite3
import stat
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_batch_delete import _confirm, _db_path, _seed, _submit
from tests.test_user_delete_guard import _exists


def test_write_lock_held_from_recount_through_commit(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud
    seen = {}

    def hook(conn):
        # inside the locked txn: backup already written, another writer must be blocked
        seen["backup_exists"] = (ud.backup_dir() / backup).exists()
        other = sqlite3.connect(_db_path(), timeout=0.2)
        try:
            other.execute("INSERT INTO debts (user_id, title, monthly_toman, months_left, due_year, due_month, due_day, created_at) "
                          "VALUES (?, 'race', 1, 1, 1405, 1, 1, '2026-01-01')", (ids["alice"],))
            other.commit()
            seen["blocked"] = False
        except sqlite3.OperationalError as e:
            seen["blocked"] = "locked" in str(e)
        finally:
            other.close()
    monkeypatch.setattr(ud, "_before_commit_hook", hook)
    _submit(client, sel, expected, backup)
    assert seen == {"backup_exists": True, "blocked": True}
    assert not _exists(ids["alice"])
    # backup taken under the lock is a consistent pre-delete snapshot
    bk = sqlite3.connect(ud.backup_dir() / backup)
    assert bk.execute("select count(*) from holdings where user_id=?", (ids["alice"],)).fetchone()[0] == 2
    assert bk.execute("select count(*) from admin_audit_log").fetchone()[0] == 0


def test_concurrent_writer_before_lock_is_caught_by_recount(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud
    real = ud._raw_connect

    def racing_connect(db):
        c = sqlite3.connect(_db_path())
        c.execute("INSERT INTO holdings (user_id, asset_key, quantity, updated_at) VALUES (?, 'eth', 1, '2026-01-01')", (ids["alice"],))
        c.commit(); c.close()
        return real(db)
    monkeypatch.setattr(ud, "_raw_connect", racing_connect)
    _submit(client, sel, expected, backup)
    assert _exists(ids["alice"])
    assert not (ud.backup_dir() / backup).exists()


def test_no_row_references_deleted_users(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"], ids["bob"]]
    _, expected, backup = _confirm(client, sel)
    _submit(client, sel, expected, backup)
    c = sqlite3.connect(_db_path())
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    checked = 0
    for t in tables:
        cols = {r[1] for r in c.execute(f'pragma table_info("{t}")')}
        fk_cols = {r[3] for r in c.execute(f'pragma foreign_key_list("{t}")') if r[2] == "users"}
        for col in (cols & {"user_id"}) | fk_cols:
            q = ",".join("?" * len(sel))
            assert c.execute(f'select count(*) from "{t}" where "{col}" in ({q})', sel).fetchone()[0] == 0, (t, col)
            checked += 1
    # orphan category references from daily_spends
    assert c.execute("select count(*) from daily_spends where category_id not in (select id from spend_categories)").fetchone()[0] == 0
    assert c.execute("pragma foreign_key_check").fetchall() == []
    assert checked >= 7


def test_low_disk_space_refuses_delete(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud
    import shutil
    monkeypatch.setattr(ud.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10**9, 10**9, 10))
    r = _submit(client, sel, expected, backup)
    assert _exists(ids["alice"])
    assert not (ud.backup_dir() / backup).exists()
    assert "فضای خالی دیسک" in r.text


def test_prune_keeps_newest_10_and_drops_older_than_30_days(client, monkeypatch):
    import app.user_delete as ud
    folder = ud._ensure_backup_dir()
    now = time.time()
    names = []
    for i in range(15):  # 15 files, all 40+ days old
        n = f"predelete-202601{i+10:02d}-000000-{i:08x}.db"
        p = folder / n; p.write_bytes(b"x")
        os.utime(p, (now - (40 + i) * 86400,) * 2)
        names.append(n)
    recent = folder / "predelete-20261013-000000-ffffffff.db"; recent.write_bytes(b"x")
    other = folder / "manual-keep.db"; other.write_bytes(b"x")
    os.utime(other, (now - 100 * 86400,) * 2)
    removed = ud.prune_backups(now)
    left = {p.name for p in folder.iterdir()}
    assert "manual-keep.db" in left and recent.name in left
    kept_old = [n for n in names if n in left]
    assert len(kept_old) == 9  # newest 10 kept = recent + 9 newest old ones
    assert set(removed) == set(names[9:])
    # young files are never pruned even beyond 10
    for i in range(12):
        (folder / f"predelete-20261012-0000{i:02d}-{i:08x}.db").write_bytes(b"x")
    ud.prune_backups(now)
    assert sum(1 for p in folder.iterdir() if p.name.startswith("predelete-20261012")) == 12


def test_successful_delete_prunes_old_backups(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    import app.user_delete as ud
    folder = ud._ensure_backup_dir()
    now = time.time()
    for i in range(12):
        p = folder / f"predelete-20250101-0000{i:02d}-{i:08x}.db"; p.write_bytes(b"x")
        os.utime(p, (now - (60 + i) * 86400,) * 2)
    _, expected, backup = _confirm(client, [ids["alice"]])
    _submit(client, [ids["alice"]], expected, backup)
    files = [p for p in folder.iterdir() if p.name.startswith("predelete-")]
    assert len(files) == 10 and (folder / backup).exists()


def test_backup_permissions_and_not_served(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    _, expected, backup = _confirm(client, [ids["alice"]])
    _submit(client, [ids["alice"]], expected, backup)
    import app.user_delete as ud
    folder = ud.backup_dir()
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((folder / backup).stat().st_mode) == 0o600
    data = (folder / backup).read_bytes()[:16]
    for path in (f"/backups/{backup}", f"/data/backups/{backup}", f"/static/../data/backups/{backup}",
                 f"/static/backups/{backup}", f"/app/data/backups/{backup}", "/inventory.db",
                 "/static/../../data/inventory.db", "/data/inventory.db", "/static/%2e%2e/data/inventory.db",
                 "/secret_key", "/data/secret_key"):
        r = client.get(path)
        assert r.status_code in (404, 405) or not r.content.startswith(data[:15]), path
        assert not r.content.startswith(b"SQLite format 3"), path


def test_restore_script_restores_all_rows_identically(client, monkeypatch, tmp_path):
    ids = _seed(client, monkeypatch)
    uid = ids["alice"]
    live_path = _db_path()
    c = sqlite3.connect(live_path)
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")
              if "user_id" in {x[1] for x in c.execute(f'pragma table_info("{r[0]}")')}]
    orig = {t: sorted(c.execute(f'select * from "{t}" where user_id=?', (uid,)).fetchall()) for t in tables}
    orig_user = c.execute("select * from users where id=?", (uid,)).fetchall()
    c.close()
    _, expected, backup = _confirm(client, [uid])
    _submit(client, [uid], expected, backup)
    assert not _exists(uid)
    import app.user_delete as ud
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    try:
        import restore_user
    finally:
        sys.path.pop(0)
    restore_user.restore_user(str(ud.backup_dir() / backup), uid, live_path)
    c = sqlite3.connect(live_path)
    assert c.execute("select * from users where id=?", (uid,)).fetchall() == orig_user
    for t in tables:
        assert sorted(c.execute(f'select * from "{t}" where user_id=?', (uid,)).fetchall()) == orig[t], t
    assert len(orig["holdings"]) == 2 and len(orig["push_device_tokens"]) == 1
    c.close()
    # refuses a second restore (id exists) and leaves DB unchanged
    with pytest.raises(SystemExit):
        restore_user.restore_user(str(ud.backup_dir() / backup), uid, live_path)
    # refuses when the username was taken by someone else
    c = sqlite3.connect(live_path)
    c.execute("update users set id=9999 where id=?", (uid,)); c.commit(); c.close()
    with pytest.raises(SystemExit, match="username"):
        restore_user.restore_user(str(ud.backup_dir() / backup), uid, live_path)


def test_snapshot_write_during_delete_waits_and_succeeds(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud
    from datetime import datetime, timezone
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot
    result = {}

    def writer():
        db = SessionLocal()
        try:
            t0 = time.time()
            db.add(PortfolioSnapshot(user_id=ids["carol"], taken_at=datetime.now(timezone.utc),
                                     total_toman=Decimal("7"), breakdown_json="{}"))
            db.commit()
            result["ok"] = True
            result["waited"] = time.time() - t0
        except Exception as e:  # noqa: BLE001
            result["err"] = repr(e)
        finally:
            db.close()

    def hook(conn):  # lock held: start the app write, keep the lock 1.5s, then commit
        th = threading.Thread(target=writer)
        th.start()
        result["thread"] = th
        time.sleep(1.5)
        result["done_before_commit"] = "ok" in result or "err" in result
    monkeypatch.setattr(ud, "_before_commit_hook", hook)
    _submit(client, sel, expected, backup)
    result["thread"].join(15)
    assert not _exists(ids["alice"])
    assert result.get("ok") is True, result
    assert result["done_before_commit"] is False and result["waited"] >= 1.0
    c = sqlite3.connect(_db_path())
    assert c.execute("select count(*) from portfolio_snapshots where user_id=?", (ids["carol"],)).fetchone()[0] == 1


def test_backup_integrity_failure_rolls_back(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud

    def bad(out):
        raise RuntimeError("backup integrity check failed: *** corrupt")
    monkeypatch.setattr(ud, "_verify_backup", bad)
    before = sqlite3.connect(_db_path()).execute("select count(*) from users").fetchone()[0]
    r = _submit(client, sel, expected, backup)
    assert _exists(ids["alice"])
    assert sqlite3.connect(_db_path()).execute("select count(*) from users").fetchone()[0] == before
    assert not (ud.backup_dir() / backup).exists()
    assert not list(ud.backup_dir().glob("*.part"))
