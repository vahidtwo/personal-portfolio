import html
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from tests.test_user_delete_guard import _csrf, _exists


def _seed(client, monkeypatch):
    import importlib
    from app.db import SessionLocal
    from app.models import (DailySpend, Debt, Holding, MonthlyExpense, PortfolioSnapshot, PushDeviceToken,
                            SpendCategory, User)
    from app.security import hash_password

    db = SessionLocal()
    users = {n: User(username=n, password_hash=hash_password("password123"))
             for n in ("boss", "boss2", "alice", "bob", "carol")}
    db.add_all(users.values()); db.commit()
    now = datetime.now(timezone.utc)
    for n in ("alice", "bob"):
        uid = users[n].id
        parent = SpendCategory(user_id=uid, name="p", is_seed=True); db.add(parent); db.flush()
        child = SpendCategory(user_id=uid, name="c", parent_id=parent.id); db.add(child); db.flush()
        db.add_all([
            PortfolioSnapshot(user_id=uid, taken_at=now, total_toman=Decimal("5"), breakdown_json="{}"),
            Holding(user_id=uid, asset_key="btc", quantity=Decimal("0.5"), updated_at=now),
            Holding(user_id=uid, asset_key="usd", quantity=Decimal("10"), updated_at=now),
            Debt(user_id=uid, title="d", monthly_toman=Decimal("1"), months_left=1, due_year=1405, due_month=1, due_day=1),
            MonthlyExpense(user_id=uid, title="e", amount_toman=Decimal("1"), due_day=1),
            DailySpend(user_id=uid, category_id=child.id, amount_toman=Decimal("3"), spent_on=date.today()),
            PushDeviceToken(user_id=uid, token=f"t{uid}", platform="web", updated_at=now),
        ])
    db.commit()
    ids = {n: u.id for n, u in users.items()}
    db.close()
    admins = frozenset({"boss", "boss2"})
    for mod in ("app.security", "app.admin_users", "app.db_admin", "app.config"):
        m = importlib.import_module(mod)
        if hasattr(m, "ADMIN_USERNAMES"):
            monkeypatch.setattr(m, "ADMIN_USERNAMES", admins)
    t = _csrf(client, "/login")
    client.post("/login", data={"username": "boss", "password": "password123", "csrf": t})
    return ids


def _confirm(client, ids):
    r = client.get("/admin/users/delete?" + "&".join(f"ids={i}" for i in ids))
    form = dict(re.findall(r'name="(expected_json|backup_name)" value="([^"]*)"', r.text))
    return r, html.unescape(form.get("expected_json", "")), form.get("backup_name", "")


def _submit(client, ids, expected, backup, count=None):
    t = _csrf(client, "/admin")
    return client.post("/admin/users/delete", data={
        "csrf": t, "ids": [str(i) for i in ids], "expected_json": expected, "backup_name": backup,
        "confirm_count": str(len(ids) if count is None else count)})


def _rows(db_path):
    c = sqlite3.connect(db_path)
    out = {t: c.execute(f"select count(*) from {t}").fetchone()[0] for t in
           ("users", "portfolio_snapshots", "holdings", "debts", "monthly_expenses", "daily_spends",
            "push_device_tokens", "spend_categories")}
    c.close()
    return out


def _db_path():
    from app.db import engine
    return engine.url.database


def test_batch_delete_happy_path_counts_backup_audit(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"], ids["bob"]]
    r, expected, backup = _confirm(client, sel)
    assert r.status_code == 200 and backup in r.text and "alice" in r.text
    shown = json.loads(expected)
    before = _rows(_db_path())
    _submit(client, sel, expected, backup)
    assert not _exists(ids["alice"]) and not _exists(ids["bob"]) and _exists(ids["carol"])
    after = _rows(_db_path())
    # every counted row is gone, matching the confirm screen exactly
    per_table = {"portfolio_snapshots": 0, "holdings": 0, "debts": 0, "monthly_expenses": 0,
                 "daily_spends": 0, "push_device_tokens": 0, "spend_categories": 0}
    for c in shown.values():
        for k, v in c.items():
            per_table["spend_categories" if k.startswith("spend_categories") else k] += v
    for t, n in per_table.items():
        assert before[t] - after[t] == n, t
    assert before["users"] - after["users"] == 2
    from app.user_delete import backup_dir
    assert (backup_dir() / backup).exists()
    c = sqlite3.connect(_db_path())
    log = c.execute("select actor_username, action, targets_json, counts_json, backup_filename from admin_audit_log").fetchall()
    assert len(log) == 1 and log[0][0] == "boss" and log[0][1] == "delete_users" and log[0][4] == backup
    assert json.loads(log[0][3]) == shown


def test_backup_failure_aborts_delete(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ud, "_backup_from", boom)
    before = _rows(_db_path())
    _submit(client, sel, expected, backup)
    assert _exists(ids["alice"]) and _rows(_db_path()) == before


def test_failure_mid_batch_rolls_back_everything(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"], ids["bob"]]
    _, expected, backup = _confirm(client, sel)
    import app.user_delete as ud

    def fail_at_end(conn):  # after all deletes + audit insert, before COMMIT
        raise RuntimeError("fail at end")
    monkeypatch.setattr(ud, "_before_commit_hook", fail_at_end)
    before = _rows(_db_path())
    with pytest.raises(RuntimeError):
        _submit(client, sel, expected, backup)
    assert _exists(ids["alice"]) and _exists(ids["bob"]) and _rows(_db_path()) == before


def test_counts_changed_since_confirm_aborts(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"]]
    _, expected, backup = _confirm(client, sel)
    from app.db import SessionLocal
    from app.models import Debt
    db = SessionLocal()
    db.add(Debt(user_id=ids["alice"], title="new", monthly_toman=Decimal("1"), months_left=1, due_year=1405, due_month=1, due_day=1))
    db.commit(); db.close()
    _submit(client, sel, expected, backup)
    assert _exists(ids["alice"])


def test_wrong_typed_count_aborts(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    sel = [ids["alice"], ids["bob"]]
    _, expected, backup = _confirm(client, sel)
    _submit(client, sel, expected, backup, count=1)
    assert _exists(ids["alice"]) and _exists(ids["bob"])
    _submit(client, sel, expected, backup, count="۲")  # Persian digits accepted
    assert not _exists(ids["alice"]) and not _exists(ids["bob"])


def test_self_and_admins_protected_server_side(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    for target in (ids["boss"], ids["boss2"]):
        r, _, _ = _confirm(client, [target, ids["carol"]])
        assert "حذف قطعی" not in r.text
        expected = json.dumps({str(target): {}, str(ids["carol"]): {}})
        from app.user_delete import new_backup_name
        _submit(client, [target, ids["carol"]], expected, new_backup_name())
        assert _exists(target) and _exists(ids["carol"])
    # forged expected counts for the real counts still refused
    from app.db import SessionLocal
    from app.user_delete import count_user_rows, new_backup_name
    db = SessionLocal()
    exp = json.dumps({str(i): count_user_rows(db, i) for i in (ids["boss2"],)}); db.close()
    _submit(client, [ids["boss2"]], exp, new_backup_name())
    assert _exists(ids["boss2"])


def test_non_admin_cannot_use_batch_delete(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    client.post("/logout", data={"csrf": _csrf(client, "/admin")})
    client.cookies.clear()
    t = _csrf(client, "/login")
    client.post("/login", data={"username": "carol", "password": "password123", "csrf": t})
    from app.db import SessionLocal
    from app.user_delete import count_user_rows, new_backup_name
    db = SessionLocal(); exp = json.dumps({str(ids["alice"]): count_user_rows(db, ids["alice"])}); db.close()
    t = _csrf(client, "/profile")
    client.post("/admin/users/delete", data={"csrf": t, "ids": [str(ids["alice"])], "expected_json": exp,
                "backup_name": new_backup_name(), "confirm_count": "1"})
    assert _exists(ids["alice"])


def test_restore_one_user_from_backup_brings_back_all_rows(client, monkeypatch):
    ids = _seed(client, monkeypatch)
    uid = ids["alice"]
    _, expected, backup = _confirm(client, [uid])
    from app.user_delete import backup_dir
    tables = ("portfolio_snapshots", "holdings", "debts", "monthly_expenses", "daily_spends",
              "push_device_tokens", "spend_categories")
    live = sqlite3.connect(_db_path())
    orig = {t: sorted(live.execute(f"select * from {t} where user_id=?", (uid,)).fetchall()) for t in tables}
    orig_user = live.execute("select * from users where id=?", (uid,)).fetchall()
    live.close()
    _submit(client, [uid], expected, backup)
    assert not _exists(uid)
    # restore procedure: ATTACH backup, copy the user's rows back (parents first)
    live = sqlite3.connect(_db_path())
    live.execute("ATTACH DATABASE ? AS bk", (str(backup_dir() / backup),))
    live.execute("INSERT INTO users SELECT * FROM bk.users WHERE id=?", (uid,))
    live.execute("INSERT INTO spend_categories SELECT * FROM bk.spend_categories WHERE user_id=? AND parent_id IS NULL", (uid,))
    for t in tables:
        live.execute(f"INSERT OR IGNORE INTO {t} SELECT * FROM bk.{t} WHERE user_id=?", (uid,))
    live.commit()
    assert live.execute("select * from users where id=?", (uid,)).fetchall() == orig_user
    for t in tables:
        assert sorted(live.execute(f"select * from {t} where user_id=?", (uid,)).fetchall()) == orig[t], t
    assert len(orig["holdings"]) == 2
    live.close()


def _alembic(db, rev, op="upgrade"):
    code = (
        "import sys; from alembic import command; from alembic.config import Config; "
        "from app.db import engine; cfg=Config(); cfg.set_main_option('script_location','app/migrations');\n"
        "with engine.begin() as c:\n cfg.attributes['connection']=c; getattr(command, sys.argv[1])(cfg, sys.argv[2])"
    )
    subprocess.run([sys.executable, "-c", code, op, rev], check=True,
                   env={"DATA_DIR": str(db.parent), "PATH": "/usr/bin:/bin"})


def test_migration_0003_up_down_keeps_data(tmp_path):
    db = tmp_path / "inventory.db"
    _alembic(db, "0002_holdings")
    c = sqlite3.connect(db)
    c.execute("INSERT INTO users (id, username, password_hash, full_name, mobile, salary_toman, gold_grams, coin_emami, coin_bahar, coin_half, coin_quarter, coin_gram, silver_grams, btc, ada, eth, sol, doge, matic, usd, cash_toman, car_toman, car_count, created_at) VALUES (1,'u','h','','',0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,'2026-01-01')")
    c.execute("INSERT INTO holdings (user_id, asset_key, quantity, updated_at) VALUES (1,'btc',1,'2026-01-01')")
    c.commit()
    dump0 = [l for l in c.iterdump()]; c.close()
    _alembic(db, "0003_admin_audit_log")
    c = sqlite3.connect(db)
    assert "admin_audit_log" in {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert c.execute("select version_num from alembic_version").fetchone()[0] == "0003_admin_audit_log"
    assert [l for l in c.iterdump() if "admin_audit_log" not in l and "alembic_version" not in l] == \
           [l for l in dump0 if "alembic_version" not in l]
    c.close()
    _alembic(db, "0002_holdings", "downgrade")
    c = sqlite3.connect(db)
    assert "admin_audit_log" not in {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert [l for l in c.iterdump()] == dump0
    c.close()
    _alembic(db, "head")
