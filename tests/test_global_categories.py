"""Global spend categories: the migration, admin-only CRUD, archive, and no per-user rows."""
import re
import sqlite3
from datetime import date

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.test_sanjeh_token_encrypt import _alembic

DAILY = "/dashboard?tab=daily"
ZWNJ = "\u200c"


def _ok(db, *args):
    r = _alembic(db, *args)
    assert r.returncode == 0, r.stderr
    return r


def _fake_multi_user_db(tmp_path):
    """Schema at 0006 with three users, each with a private copy of the default tree plus a few custom rows."""
    from app.daily_spend import DAILY_SPEND_TREE

    db = tmp_path / "inventory.db"
    _ok(db, "upgrade", "0006_due_reminders")
    c = sqlite3.connect(db)
    now = "2026-01-01 00:00:00"
    for uid in (1, 2, 3):
        c.execute("INSERT INTO users (id, username, password_hash, full_name, mobile, salary_toman, gold_grams, coin_emami,"
                  " coin_bahar, coin_half, coin_quarter, coin_gram, silver_grams, btc, ada, eth, sol, doge, matic, usd,"
                  " cash_toman, car_toman, car_count, created_at) VALUES (?, ?, 'x', '', '', 0, 0, 0, 0, 0, 0, 0, 0, 0,"
                  " 0, 0, 0, 0, 0, 0, 0, 0, 0, ?)", (uid, f"user{uid}", now))
        for p_index, (p_slug, p_name, children) in enumerate(DAILY_SPEND_TREE):
            cur = c.execute("INSERT INTO spend_categories (user_id, parent_id, name, slug, is_seed, sort_order, created_at)"
                            " VALUES (?, NULL, ?, ?, 1, ?, ?)", (uid, p_name, p_slug, p_index, now))
            pid = cur.lastrowid
            for c_index, (c_slug, c_name) in enumerate(children):
                c.execute("INSERT INTO spend_categories (user_id, parent_id, name, slug, is_seed, sort_order, created_at)"
                          " VALUES (?, ?, ?, ?, 1, ?, ?)", (uid, pid, c_name, c_slug, c_index, now))

    def cat(uid, slug):
        return c.execute("SELECT id FROM spend_categories WHERE user_id=? AND slug=?", (uid, slug)).fetchone()[0]

    def custom(uid, parent_slug, name, slug=None):
        return c.execute("INSERT INTO spend_categories (user_id, parent_id, name, slug, is_seed, sort_order, created_at)"
                         " VALUES (?, ?, ?, ?, 0, 9, ?)", (uid, cat(uid, parent_slug), name, slug, now)).lastrowid

    fee1 = custom(1, "sms", "کارمزد", "sms_fee")
    fee2 = custom(2, "sms", "\u0643\u0627\u0631\u0645\u0632\u062f")  # Arabic kaf, no slug: same category as fee1
    coffee1 = custom(1, "food", f"قهوه{ZWNJ}ی  صبح ")
    coffee3 = custom(3, "food", "قهوهی صبح")  # differs only by ZWNJ and spaces
    tea2 = custom(2, "food", "چای")
    spends = [
        (1, cat(1, "cafe"), 100), (1, cat(1, "cafe"), 200), (2, cat(2, "cafe"), 300), (3, cat(3, "fuel"), 400),
        (1, fee1, 5), (2, fee2, 6), (1, coffee1, 7), (3, coffee3, 8), (2, tea2, 9), (3, cat(3, "sms_bank"), 900),
    ]
    for i, (uid, cid, amount) in enumerate(spends):
        c.execute("INSERT INTO daily_spends (user_id, category_id, amount_toman, spent_on, note, created_at)"
                  " VALUES (?, ?, ?, ?, ?, ?)", (uid, cid, amount, date(2026, 1, 1 + i).isoformat(), f"n{i}", now))
    c.commit()
    c.close()
    return db


def _key(name):
    from app.models import category_name_key

    return category_name_key(name)


def _per_category_name(db):
    """(parent name key, child name key) -> number of spends, over all users."""
    c = sqlite3.connect(db)
    out = {}
    for parent, child in c.execute(
            "SELECT p.name, s.name FROM daily_spends d JOIN spend_categories s ON s.id = d.category_id"
            " LEFT JOIN spend_categories p ON p.id = s.parent_id"):
        k = (_key(parent), _key(child))
        out[k] = out.get(k, 0) + 1
    c.close()
    return out


def _spends(db):
    c = sqlite3.connect(db)
    rows = c.execute("SELECT id, user_id, amount_toman, spent_on, note FROM daily_spends ORDER BY id").fetchall()
    c.close()
    return rows


def _checks(db):
    c = sqlite3.connect(db)
    out = (c.execute("PRAGMA integrity_check").fetchone()[0], c.execute("PRAGMA foreign_key_check").fetchall(),
           c.execute("SELECT count(*) FROM daily_spends WHERE category_id NOT IN (SELECT id FROM spend_categories)").fetchone()[0],
           c.execute("SELECT count(*) FROM spend_categories WHERE parent_id IS NOT NULL"
                     " AND parent_id NOT IN (SELECT id FROM spend_categories)").fetchone()[0])
    c.close()
    return out


def _cols(db):
    c = sqlite3.connect(db)
    out = [r[1] for r in c.execute("PRAGMA table_info(spend_categories)")]
    c.close()
    return out


def test_migration_merges_per_user_rows_keeps_every_spend_and_is_idempotent(tmp_path):
    db = _fake_multi_user_db(tmp_path)
    before_names, before_spends = _per_category_name(db), _spends(db)
    c = sqlite3.connect(db)
    kept_ids = dict(c.execute("SELECT slug, id FROM spend_categories WHERE user_id = 1 AND slug IS NOT NULL AND slug != 'sms_fee'"))
    c.close()
    _ok(db, "upgrade", "head")
    assert "user_id" not in _cols(db) and {"archived", "icon", "color", "name_key"} <= set(_cols(db))
    assert _per_category_name(db) == before_names
    assert _spends(db) == before_spends
    assert _checks(db) == ("ok", [], 0, 0)
    c = sqlite3.connect(db)
    assert c.execute("SELECT count(*) FROM spend_categories").fetchone()[0] == 35 + 3  # fee, coffee, tea
    assert dict(c.execute("SELECT slug, id FROM spend_categories WHERE slug IS NOT NULL AND slug != 'sms_fee'")) == kept_ids
    assert c.execute("SELECT count(*) FROM spend_categories WHERE slug = 'sms_fee'").fetchone()[0] == 1
    assert c.execute("SELECT count(DISTINCT category_id) FROM daily_spends").fetchone()[0] == 6
    snapshot = c.execute("SELECT * FROM spend_categories ORDER BY id").fetchall()
    c.close()

    _ok(db, "stamp", "0006_due_reminders")
    _ok(db, "upgrade", "head")  # already global: a re-run changes nothing
    c = sqlite3.connect(db)
    assert c.execute("SELECT * FROM spend_categories ORDER BY id").fetchall() == snapshot
    c.close()
    assert _spends(db) == before_spends

    _ok(db, "downgrade", "0006_due_reminders")
    assert "user_id" in _cols(db) and "archived" not in _cols(db)
    assert _per_category_name(db) == before_names and _spends(db) == before_spends
    assert _checks(db) == ("ok", [], 0, 0)
    c = sqlite3.connect(db)
    assert c.execute("SELECT count(*) FROM daily_spends d JOIN spend_categories s ON s.id = d.category_id"
                     " WHERE s.user_id != d.user_id").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM spend_categories s JOIN spend_categories p ON p.id = s.parent_id"
                     " WHERE s.user_id != p.user_id").fetchone()[0] == 0
    c.close()

    _ok(db, "upgrade", "head")
    assert _per_category_name(db) == before_names and _spends(db) == before_spends
    assert _checks(db) == ("ok", [], 0, 0)
    c = sqlite3.connect(db)
    assert c.execute("SELECT count(*), sum(is_seed) FROM spend_categories").fetchone() == (38, 35)
    c.close()


def test_migration_refuses_ambiguous_merge_and_changes_nothing(tmp_path):
    db = _fake_multi_user_db(tmp_path)
    c = sqlite3.connect(db)
    c.execute("UPDATE spend_categories SET slug = 'other_slug' WHERE user_id = 2 AND slug = 'cafe'")
    c.commit()
    before = c.execute("SELECT * FROM spend_categories ORDER BY id").fetchall()
    c.close()
    r = _alembic(db, "upgrade", "head")
    assert r.returncode != 0 and "share a name but have slugs" in r.stderr
    c = sqlite3.connect(db)
    assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_due_reminders"
    assert c.execute("SELECT * FROM spend_categories ORDER BY id").fetchall() == before
    assert "_alembic_tmp_spend_categories" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    c.close()


def test_empty_database_gets_the_default_tree_once(tmp_path):
    db = tmp_path / "inventory.db"
    _ok(db, "upgrade", "head")
    _ok(db, "stamp", "0006_due_reminders")
    _ok(db, "upgrade", "head")
    c = sqlite3.connect(db)
    assert c.execute("SELECT count(*), sum(is_seed) FROM spend_categories").fetchone() == (35, 35)
    c.close()


def _count():
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        return db.query(SpendCategory).count()


def test_new_user_creates_no_category_rows(client, no_network):
    before = _count()
    assert before == 35
    _register(client, "newbie")
    client.get(DAILY)
    r = client.post("/api/sms-spend", json={"amount_toman": "90000", "note": "x", "idempotency_key": "k" * 64})
    assert r.json()["ok"]
    client.cookies.clear()
    _register(client, "second")
    client.get(DAILY)
    assert _count() == before


def _admin(client, monkeypatch, name="boss"):
    import importlib

    for mod in ("app.security", "app.admin_users", "app.db_admin", "app.config"):
        m = importlib.import_module(mod)
        if hasattr(m, "ADMIN_USERNAMES"):
            monkeypatch.setattr(m, "ADMIN_USERNAMES", frozenset({name}))
    _register(client, name)


def _child(slug):
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        row = db.query(SpendCategory).filter(SpendCategory.slug == slug).one()
        return row.id, row.parent_id


def test_non_admin_gets_403_on_category_crud(client, monkeypatch, no_network):
    _admin(client, monkeypatch, "boss")
    client.cookies.clear()
    _register(client, "mallory")
    cid, pid = _child("cafe")
    t = _csrf(client, "/profile")
    data = {"csrf": t, "name": "hacked", "parent_id": str(pid), "sort_order": "0", "archived": "0"}
    for path in ("/admin/db/spend-categories/new", f"/admin/db/spend-categories/{cid}",
                 f"/admin/db/spend-categories/{cid}/delete"):
        r = client.post(path, data=data, follow_redirects=False)
        assert r.status_code == 403, path
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        assert db.get(SpendCategory, cid).name == "کافه"
        assert db.query(SpendCategory).filter(SpendCategory.name == "hacked").count() == 0


def test_admin_crud_requires_csrf_and_archives_instead_of_deleting_used(client, monkeypatch, no_network):
    from app.db import SessionLocal
    from app.models import DailySpend, SpendCategory

    _admin(client, monkeypatch)
    cid, pid = _child("cafe")
    r = client.post("/admin/db/spend-categories/new", data={"name": "قهوه", "parent_id": str(pid)})
    assert r.status_code == 400
    t = _csrf(client, "/admin/db/spend-categories/new")
    r = client.post("/admin/db/spend-categories/new", data={"csrf": t, "name": " قهوه ", "parent_id": str(pid),
                    "icon": "☕", "color": "#123abc", "sort_order": "7", "archived": "0"}, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        new = db.query(SpendCategory).filter(SpendCategory.name == "قهوه").one()
        assert (new.parent_id, new.icon, new.color, new.sort_order, new.archived) == (pid, "☕", "#123abc", 7, False)
        new_id = new.id
    r = client.post("/admin/db/spend-categories/new", data={"csrf": t, "name": "قهوه", "parent_id": str(pid)})
    assert "همین نام" in r.text
    r = client.post(f"/admin/db/spend-categories/{cid}", data={"csrf": t, "name": "کافه و قهوه", "parent_id": str(pid),
                    "icon": "", "color": "bad", "sort_order": "1", "archived": "0"})
    assert "رنگ" in r.text
    r = client.post(f"/admin/db/spend-categories/{cid}", data={"csrf": t, "name": "کافه و قهوه", "parent_id": str(pid),
                    "icon": "", "color": "", "sort_order": "1", "archived": "0"}, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        db.add(DailySpend(user_id=1, category_id=cid, amount_toman=1000, spent_on=date(2026, 1, 1), note=""))
        db.commit()
    client.post(f"/admin/db/spend-categories/{cid}/delete", data={"csrf": t})
    with SessionLocal() as db:
        assert db.get(SpendCategory, cid) is not None  # in use: never hard-deleted
    client.post(f"/admin/db/spend-categories/{new_id}/delete", data={"csrf": t})
    sms_bank, _ = _child("sms_bank")
    client.post(f"/admin/db/spend-categories/{sms_bank}/delete", data={"csrf": t})
    with SessionLocal() as db:
        assert db.get(SpendCategory, new_id) is None  # unused: deleted
        assert db.get(SpendCategory, sms_bank) is not None
    page = client.get("/admin/db/spend-categories").text
    assert "کافه و قهوه" in page and "فعال" in page


def _picker(html):
    block = re.search(r'<select name="category_id".*?</select>', html, re.S).group(0)
    return set(re.findall(r'<option value="(\d+)"', block))


def test_archived_category_hidden_from_picker_but_kept_on_old_spends(client, monkeypatch, no_network):
    from app.db import SessionLocal
    from app.models import DailySpend, SpendCategory, User
    import jdatetime

    _admin(client, monkeypatch)
    cid, pid = _child("cafe")
    today = jdatetime.date.today()
    form = {"amount_toman": "5000", "year": str(today.year), "month": str(today.month), "day": str(today.day),
            "parent_id": str(pid), "category_id": str(cid), "note": "old"}
    assert client.post("/profile/spends", data={**form, "csrf": _csrf(client, DAILY)}, follow_redirects=False).status_code == 303
    assert str(cid) in _picker(client.get(DAILY).text)
    t = _csrf(client, "/admin/db/spend-categories/new")
    client.post(f"/admin/db/spend-categories/{cid}", data={"csrf": t, "name": "کافه", "parent_id": str(pid),
                "icon": "", "color": "", "sort_order": "1", "archived": "1"})
    with SessionLocal() as db:
        assert db.get(SpendCategory, cid).archived
        spend_id = db.query(DailySpend).one().id
    html = client.get(DAILY).text
    assert str(cid) not in _picker(html)
    assert "کافه" in html  # the old spend still shows its category name
    r = client.post("/profile/spends", data={**form, "note": "new", "csrf": _csrf(client, DAILY)},
                    headers={"Accept": "application/json"})
    assert r.status_code == 422 and "category_id" in r.json()["fields"]
    edit = client.get(f"{DAILY}&edit_spend={spend_id}").text
    assert str(cid) in _picker(edit)  # editing the old spend keeps its archived category selectable
    r = client.post(f"/profile/spends/{spend_id}", data={**form, "amount_toman": "6000", "csrf": _csrf(client, DAILY)},
                    follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        row = db.get(DailySpend, spend_id)
        assert (row.category_id, int(row.amount_toman)) == (cid, 6000)
        assert db.query(DailySpend).count() == 1
        assert db.query(User).count() == 1


def test_parent_archived_hides_its_children(client, monkeypatch, no_network):
    from app.db import SessionLocal
    from app.models import SpendCategory

    _admin(client, monkeypatch)
    cid, pid = _child("cafe")
    with SessionLocal() as db:
        db.get(SpendCategory, pid).archived = True
        db.commit()
    picker = _picker(client.get(DAILY).text)
    assert str(cid) not in picker and picker


def test_restore_script_maps_an_old_per_user_backup_onto_global_categories(tmp_path):
    import shutil
    import sys
    from pathlib import Path

    live = _fake_multi_user_db(tmp_path)
    backup = tmp_path / "backup.db"
    shutil.copy(live, backup)
    before = _per_category_name(backup)
    _ok(live, "upgrade", "head")
    c = sqlite3.connect(live)
    c.execute("DELETE FROM daily_spends WHERE user_id = 3")
    c.execute("DELETE FROM users WHERE id = 3")
    c.commit()
    c.close()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import restore_user
    finally:
        sys.path.pop(0)
    categories = sqlite3.connect(live).execute("SELECT count(*) FROM spend_categories").fetchone()[0]
    restore_user.restore_user(str(backup), 3, str(live))
    assert _per_category_name(live) == before
    assert _checks(live) == ("ok", [], 0, 0)
    assert sqlite3.connect(live).execute("SELECT count(*) FROM spend_categories").fetchone()[0] == categories
