"""Admin spend-categories page (/admin/categories) and its JSON API: access, locks, safe writes, picker, migration."""
import json
import re
import sqlite3
from datetime import date

from tests.test_global_categories import _admin, _child
from tests.test_holdings import _register, no_network  # noqa: F401
from tests.test_sanjeh_migration import _insert
from tests.test_sanjeh_token_encrypt import _alembic

PAGE = "/admin/categories"
API = "/admin/api/categories"
DAILY = "/dashboard?tab=daily"


def _token(client):
    return re.search(r'data-csrf="([^"]+)"', client.get(PAGE).text).group(1)


def _h(client):
    return {"X-CSRF-Token": _token(client)}


def _spend(cid, n=1, user_id=1):
    from app.db import SessionLocal
    from app.models import DailySpend

    with SessionLocal() as db:
        for i in range(n):
            db.add(DailySpend(user_id=user_id, category_id=cid, amount_toman=1000 + i, spent_on=date(2026, 1, 1 + i),
                              note="fake"))
        db.commit()


def _snapshot():
    from sqlalchemy import func

    from app.db import SessionLocal
    from app.models import DailySpend

    with SessionLocal() as db:
        counts = dict(db.query(DailySpend.category_id, func.count(DailySpend.id)).group_by(DailySpend.category_id).all())
        each = dict(db.query(DailySpend.id, DailySpend.category_id).all())
    return counts, each


def _row(cid):
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        return db.get(SpendCategory, cid)


def _rows(client):
    return {r["id"]: r for r in client.get(API).json()["rows"]}


def _routes(cid):
    return [("get", PAGE, None), ("get", API, None), ("post", API, {"name": "x"}), ("patch", f"{API}/{cid}", {"name": "x"}),
            ("post", f"{API}/{cid}/archive", {}), ("post", f"{API}/{cid}/restore", {}), ("delete", f"{API}/{cid}", None),
            ("post", f"{API}/reorder", {"parent_id": None, "ids": []}), ("post", f"{API}/seed", {})]


def test_non_admin_gets_403_and_signed_out_is_refused_everywhere(client, monkeypatch, no_network):
    _admin(client, monkeypatch, "boss")
    h = _h(client)
    client.cookies.clear()
    _register(client, "mallory")
    cid, _ = _child("cafe")
    before = _snapshot(), _row(cid).name
    for method, path, body in _routes(cid):
        kw = {"json": body} if body is not None else {}
        r = getattr(client, method)(path, headers=h, follow_redirects=False, **kw)
        assert r.status_code == 403, (method, path)
        assert "boss" not in r.text
    for path in ("/admin/db/spend-categories", "/admin/db/spend-categories/new", f"/admin/db/spend-categories/{cid}"):
        r = client.get(path, follow_redirects=False)  # the old editor's own guard: back to the dashboard
        assert r.status_code == 303 and r.headers["location"] == "/dashboard", path
    client.cookies.clear()
    for method, path, body in _routes(cid):
        kw = {"json": body} if body is not None else {}
        r = getattr(client, method)(path, follow_redirects=False, **kw)
        if path == PAGE:
            assert r.status_code in (302, 303, 307) and r.headers["location"].startswith("/auth")
        else:
            assert r.status_code == 401, (method, path)
    assert (_snapshot(), _row(cid).name) == before


def test_old_editor_urls_redirect_and_write_nothing(client, monkeypatch, no_network):
    from tests.test_holdings import _csrf

    _admin(client, monkeypatch)
    cid, pid = _child("cafe")
    for path in ("/admin/db/spend-categories", "/admin/db/spend-categories/new", f"/admin/db/spend-categories/{cid}"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == PAGE, path
    t = _csrf(client, "/profile")
    r = client.post(f"/admin/db/spend-categories/{cid}", data={"csrf": t, "name": "hacked", "parent_id": str(pid)},
                    follow_redirects=False)
    assert r.status_code == 303 and _row(cid).name == "کافه"
    assert f'href="{PAGE}"' in client.get("/admin/db").text


def test_page_and_api_show_counts_only(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    cid, _ = _child("cafe")
    _spend(cid, 3)
    page = client.get(PAGE)
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert 'dir="rtl"' in page.text and "admin-categories.js?v=20261110b" in page.text
    data = json.loads(re.search(r'<script type="application/json" id="ac-data">(.*?)</script>', page.text, re.S).group(1))
    row = next(r for r in data["rows"] if r["id"] == cid)
    assert row["spend_count"] == 3
    blob = json.dumps(data, ensure_ascii=False)
    for text in (blob, client.get(API).text):
        assert "amount" not in text and "1000" not in text and "1001" not in text and "boss" not in text
    assert "amount_toman" not in page.text and "1001" not in page.text
    assert len(data["config"]["palette"]) == 14 and all(p["contrast"] >= 4.5 for p in data["config"]["palette"])


def test_create_validates_palette_icons_and_duplicates_and_appends(client, monkeypatch, no_network):
    from app.category_style import PALETTE

    _admin(client, monkeypatch)
    h = _h(client)
    _, pid = _child("cafe")
    r = client.post(API, json={"name": "سفر", "icon": "✈️", "color": "#123abc"}, headers=h)
    assert r.status_code == 422 and "color" in r.json()["fields"]
    r = client.post(API, json={"name": "سفر", "icon": "<b>", "color": PALETTE[0][0]}, headers=h)
    assert r.status_code == 422 and "icon" in r.json()["fields"]
    r = client.post(API, json={"name": "", "parent_id": pid}, headers=h)
    assert r.status_code == 422 and "name" in r.json()["fields"]
    r = client.post(API, json={"name": "x" * 65, "parent_id": pid}, headers=h)
    assert r.status_code == 422
    r = client.post(API, json={"name": "سفر", "icon": "✈️", "color": PALETTE[3][0].upper()}, headers=h)
    assert r.status_code == 200
    new = _row(r.json()["id"])
    groups = [x for x in _rows(client).values() if x["parent_id"] is None]
    assert (new.icon, new.color, new.sort_order) == ("✈️", PALETTE[3][0], max(g["sort_order"] for g in groups))
    r = client.post(API, json={"name": " سفر "}, headers=h)
    assert r.status_code == 422 and "name" in r.json()["fields"]
    r = client.post(API, json={"name": "قطار", "parent_id": new.id, "icon": "🚗", "color": PALETTE[0][0]}, headers=h)
    kid = _row(r.json()["id"])
    assert (kid.parent_id, kid.icon, kid.color, kid.sort_order) == (new.id, None, None, 0)
    r = client.post(API, json={"name": "اتوبوس", "parent_id": new.id}, headers=h)
    assert _row(r.json()["id"]).sort_order == 1


def test_delete_only_unused_and_never_system(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    cid, pid = _child("cafe")
    _spend(cid, 2)
    before = _snapshot()
    r = client.delete(f"{API}/{cid}", headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "in_use" and r.json()["spend_count"] == 2
    r = client.delete(f"{API}/{pid}", headers=h)
    assert r.status_code == 409 and r.json()["child_count"] > 0
    for slug in ("sms", "sms_bank"):
        sid = _child(slug)[0]
        r = client.delete(f"{API}/{sid}", headers=h)
        assert r.status_code == 409 and r.json()["reason"] == "system"
    new_id = client.post(API, json={"name": "موقت", "parent_id": pid}, headers=h).json()["id"]
    assert client.delete(f"{API}/{new_id}", headers=h).status_code == 200
    assert _row(new_id) is None and _row(cid) is not None
    kids = sorted((r["sort_order"] for r in _rows(client).values() if r["parent_id"] == pid))
    assert kids == list(range(len(kids)))
    assert _snapshot() == before


def test_reorder_needs_the_exact_sibling_set(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    _, pid = _child("cafe")
    kids = [r["id"] for r in sorted(_rows(client).values(), key=lambda r: r["sort_order"]) if r["parent_id"] == pid]
    r = client.post(f"{API}/reorder", json={"parent_id": pid, "ids": kids[:-1]}, headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "stale"
    r = client.post(f"{API}/reorder", json={"parent_id": pid, "ids": kids + kids[:1]}, headers=h)
    assert r.status_code == 409
    new = list(reversed(kids))
    assert client.post(f"{API}/reorder", json={"parent_id": pid, "ids": new}, headers=h).status_code == 200
    got = [r["id"] for r in sorted(_rows(client).values(), key=lambda r: r["sort_order"]) if r["parent_id"] == pid]
    assert got == new and [_row(i).sort_order for i in new] == list(range(len(new)))
    groups = [r["id"] for r in _rows(client).values() if r["parent_id"] is None]
    assert client.post(f"{API}/reorder", json={"parent_id": None, "ids": groups[1:] + groups[:1]}, headers=h).status_code == 200


def test_stale_version_is_refused(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    cid, _ = _child("cafe")
    v = _rows(client)[cid]["version"]
    assert client.patch(f"{API}/{cid}", json={"name": "کافه ۲", "version": v}, headers=h).status_code == 200
    r = client.patch(f"{API}/{cid}", json={"name": "کافه ۳", "version": v}, headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "stale" and _row(cid).name == "کافه ۲"


def test_archive_parent_keeps_children_flags_and_restore_asks_for_parent(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    cid, pid = _child("cafe")
    assert client.post(f"{API}/{cid}/archive", headers=h).status_code == 200
    r = client.post(f"{API}/{pid}/archive", headers=h)
    assert r.status_code == 200 and cid not in [k["id"] for k in r.json()["hidden_children"]]
    assert r.json()["hidden_children"]
    rows = _rows(client)
    assert rows[pid]["archived"] and rows[cid]["archived"]
    assert all(not rows[k["id"]]["archived"] for k in r.json()["hidden_children"])
    r = client.post(f"{API}/{cid}/restore", json={}, headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "needs_parent_restore" and _row(cid).archived
    assert client.post(f"{API}/{cid}/restore", json={"with_parent": True}, headers=h).status_code == 200
    assert not _row(cid).archived and not _row(pid).archived


def test_sms_rows_are_locked(client, monkeypatch, no_network):
    from app.db import SessionLocal
    from app.spends import commission_category

    _admin(client, monkeypatch)
    h = _h(client)
    with SessionLocal() as db:
        fee = commission_category(db)
        db.commit()
        fee_id, sms_id = fee.id, fee.parent_id
    _, food = _child("cafe")
    rows = _rows(client)
    assert rows[fee_id]["system"] and "name" in rows[fee_id]["locks"]
    r = client.patch(f"{API}/{fee_id}", json={"name": "کارمزد بانک"}, headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "system"
    for sid in (fee_id, _child("sms_bank")[0]):
        assert client.patch(f"{API}/{sid}", json={"parent_id": food, "confirm_move": True}, headers=h).status_code == 409
        assert client.post(f"{API}/{sid}/archive", headers=h).status_code == 409
        assert client.delete(f"{API}/{sid}", headers=h).status_code == 409
    assert client.post(f"{API}/{sms_id}/archive", headers=h).status_code == 409
    sms_bank = _child("sms_bank")[0]
    assert client.patch(f"{API}/{sms_bank}", json={"name": "پیامک بانکی"}, headers=h).status_code == 200
    assert client.patch(f"{API}/{sms_id}", json={"icon": "💬"}, headers=h).status_code == 200
    with SessionLocal() as db:
        assert commission_category(db).id == fee_id
    row = _row(fee_id)
    assert (row.name, row.parent_id, row.archived) == ("کارمزد", sms_id, False)


def test_commission_found_by_slug_after_rename(client, no_network):
    from app.db import SessionLocal
    from app.models import SpendCategory
    from app.spends import commission_category

    with SessionLocal() as db:
        fee = commission_category(db)
        db.commit()
        fee_id = fee.id
        db.get(SpendCategory, fee_id).name = "کارمزد پیامک"
        db.commit()
        assert commission_category(db).id == fee_id
        assert db.query(SpendCategory).filter(SpendCategory.slug == "sms_fee").count() == 1


def test_move_with_spends_needs_confirm_and_keeps_every_spend(client, monkeypatch, no_network):
    from app.db import SessionLocal
    from app.models import AdminAuditLog

    _admin(client, monkeypatch)
    h = _h(client)
    cid, pid = _child("cafe")
    other, other_parent = _child("fuel")
    _spend(cid, 2)
    _spend(other, 1)
    before = _snapshot()
    r = client.patch(f"{API}/{cid}", json={"parent_id": other_parent}, headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "needs_confirm" and r.json()["spend_count"] == 2
    assert _row(cid).parent_id == pid
    r = client.patch(f"{API}/{cid}", json={"parent_id": None, "confirm_move": True}, headers=h)
    assert r.status_code == 422 and _row(cid).parent_id == pid
    r = client.patch(f"{API}/{pid}", json={"parent_id": other_parent}, headers=h)
    assert r.status_code == 422
    r = client.patch(f"{API}/{cid}", json={"parent_id": other_parent, "confirm_move": True}, headers=h)
    assert r.status_code == 200 and _row(cid).parent_id == other_parent
    assert _snapshot() == before
    for gid in (pid, other_parent):
        kids = sorted(r["sort_order"] for r in _rows(client).values() if r["parent_id"] == gid)
        assert kids == list(range(len(kids)))
    with SessionLocal() as db:
        log = db.query(AdminAuditLog).filter(AdminAuditLog.action == "category_reparent").one()
        assert json.loads(log.counts_json) == {"spends": 2} and "amount" not in log.targets_json
    unused = client.post(API, json={"name": "بی‌خرج", "parent_id": pid}, headers=h).json()["id"]
    assert client.patch(f"{API}/{unused}", json={"parent_id": other_parent}, headers=h).status_code == 200


def test_spend_counts_identical_across_every_operation(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    cid, pid = _child("cafe")
    fuel, fuel_parent = _child("fuel")
    _spend(cid, 3)
    _spend(fuel, 2)
    _spend(_child("sms_bank")[0], 1)
    before = _snapshot()
    v = _rows(client)
    steps = [
        ("patch", f"{API}/{cid}", {"name": "کافه‌ها"}),
        ("patch", f"{API}/{pid}", {"icon": "🍽️", "version": v[pid]["version"]}),
        ("post", f"{API}/{cid}/archive", {}), ("post", f"{API}/{pid}/archive", {}),
        ("post", f"{API}/{cid}/restore", {"with_parent": True}),
        ("delete", f"{API}/{cid}", None), ("delete", f"{API}/{pid}", None),
        ("patch", f"{API}/{fuel}", {"parent_id": pid, "confirm_move": True}),
        ("post", f"{API}/reorder", {"parent_id": None,
                                    "ids": [r["id"] for r in v.values() if r["parent_id"] is None][::-1]}),
        ("post", f"{API}/seed", {}),
    ]
    for method, path, body in steps:
        kw = {"json": body} if body is not None else {}
        getattr(client, method)(path, headers=h, **kw)
        assert _snapshot() == before, path
    assert _row(fuel).parent_id == pid and fuel_parent != pid


def test_picker_hides_groups_without_active_children(client, monkeypatch, no_network):
    _admin(client, monkeypatch)
    h = _h(client)
    new_group = client.post(API, json={"name": "خالی", "icon": "🏠"}, headers=h).json()["id"]
    html = client.get(DAILY).text
    assert "خالی" not in html
    kid = client.post(API, json={"name": "زیر", "parent_id": new_group}, headers=h).json()["id"]
    assert "خالی" in client.get(DAILY).text
    client.post(f"{API}/{kid}/archive", headers=h)
    assert "خالی" not in client.get(DAILY).text


def test_spend_row_badge_uses_group_emoji(client, monkeypatch, no_network):
    from app.category_style import group_badge

    assert group_badge("🚗", "حمل‌ونقل") == "🚗"
    assert group_badge("", "\u200cحمل") == "ح"
    assert group_badge(None, "") == ""


def test_seed_sets_default_icons_and_next_sort_order(client, no_network):
    from app.category_style import DEFAULT_GROUP_ICONS
    from app.daily_spend import next_sort_order
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        groups = db.query(SpendCategory).filter(SpendCategory.parent_id.is_(None)).all()
        assert {g.slug: g.icon for g in groups} == {s: DEFAULT_GROUP_ICONS[s] for s in (g.slug for g in groups)}
        assert next_sort_order(db, None) == max(g.sort_order for g in groups) + 1
        assert next_sort_order(db, 10 ** 6) == 0


def test_migration_0009_sets_only_empty_default_icons(tmp_path):
    db = tmp_path / "fake.db"

    def ok(*args):
        r = _alembic(db, *args)
        assert r.returncode == 0, r.stderr

    ok("upgrade", "0008_debt_reminder_days")
    c = sqlite3.connect(db)
    c.execute("DELETE FROM spend_categories")
    now = "2026-01-01 00:00:00"
    rows = [(1, None, "خوراک", "food", None), (2, None, "حمل", "transport", "🚲"), (3, None, "هدیه", "gifts", "  "),
            (4, None, "سفر", None, None), (5, 1, "کافه", "cafe", None), (6, None, "پیامک", "sms", "")]
    for rid, parent, name, slug, icon in rows:
        c.execute("INSERT INTO spend_categories (id, parent_id, name, name_key, slug, is_seed, sort_order, icon, color,"
                  " archived, created_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, NULL, 0, ?)",
                  (rid, parent, name, f"k{rid}", slug, rid, icon, now))
    _insert(c, "users", id=1, username="fake_u")
    _insert(c, "daily_spends", user_id=1, category_id=5, amount_toman=10, spent_on="2026-01-01", note="")
    c.commit()
    before = c.execute("select * from daily_spends").fetchall()
    c.close()

    def icons():
        with sqlite3.connect(db) as c:
            return dict(c.execute("select id, icon from spend_categories").fetchall())

    ok("upgrade", "head")
    after = icons()
    assert after == {1: "🍽️", 2: "🚲", 3: "🎁", 4: None, 5: None, 6: "💬"}
    ok("stamp", "0008_debt_reminder_days")
    ok("upgrade", "head")
    assert icons() == after
    ok("downgrade", "0008_debt_reminder_days")
    assert icons() == {1: None, 2: "🚲", 3: None, 4: None, 5: None, 6: None}
    with sqlite3.connect(db) as c:
        assert c.execute("select * from daily_spends").fetchall() == before
        assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
