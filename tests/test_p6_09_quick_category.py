"""Tests for Phase 6 item 9: quick category, merchant memory, and delete undo."""

from datetime import timedelta
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]

ALEMBIC_RUN = """
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


def _alembic(db: Path, action: str, rev: str) -> None:
    subprocess.run(
        [sys.executable, "-c", ALEMBIC_RUN, str(db), action, rev],
        check=True,
        cwd=str(ROOT),
        env={"DATA_DIR": str(db.parent), "PATH": "/usr/bin:/bin"},
    )


def _insert(c: sqlite3.Connection, table: str, **values) -> None:
    for _, name, typ, notnull, default, pk in c.execute(f"pragma table_info({table})").fetchall():
        if name in values or not notnull or default is not None or pk:
            continue
        t = (typ or "").upper()
        values[name] = 0 if any(k in t for k in ("INT", "NUM", "DEC", "BOOL", "FLOAT", "REAL")) else (
            "2026-01-01 00:00:00" if ("DATE" in t or "TIME" in t) else f"fake-{name}"
        )
    keys = ",".join(values)
    c.execute(f"insert into {table} ({keys}) values ({','.join('?' * len(values))})", tuple(values.values()))


def _pick_cats():
    from app.db import SessionLocal
    from app.models import SpendCategory

    with SessionLocal() as db:
        children = (
            db.query(SpendCategory)
            .filter(
                SpendCategory.parent_id.is_not(None),
                SpendCategory.slug.notin_(("sms_bank", "sms_fee")),
            )
            .order_by(SpendCategory.id)
            .all()
        )
        sms_bank = db.query(SpendCategory).filter(SpendCategory.slug == "sms_bank").one()
        return children[0].id, children[1].id, children[2].id, sms_bank.id


def _api_spends_rows(client):
    res = client.get("/api/spends")
    assert res.status_code == 200, res.text
    return [r for g in res.json()["groups"] for r in g["rows"]]


def test_0014_migration_upgrade_downgrade_on_copy(tmp_path):
    db_path = tmp_path / "copy.db"
    _alembic(db_path, "upgrade", "0013_debt_payments")

    c = sqlite3.connect(db_path)
    _insert(c, "users", id=1, username="fake_u1")
    cid = c.execute("select id from spend_categories where parent_id is not null limit 1").fetchone()[0]
    _insert(c, "daily_spends", id=1, user_id=1, category_id=cid, amount_toman=150000, spent_on="2026-11-01", note="نان")
    c.commit()
    c.close()

    copy_path = tmp_path / "copied.db"
    shutil.copy2(db_path, copy_path)

    _alembic(copy_path, "upgrade", "0014_spend_category_memory")
    c2 = sqlite3.connect(copy_path)
    tables = {r[0] for r in c2.execute("select name from sqlite_master where type='table'")}
    assert "spend_merchant_categories" in tables
    cols = {r[1] for r in c2.execute("pragma table_info(daily_spends)")}
    assert "deleted_at" in cols and "category_source" in cols
    assert c2.execute("select amount_toman, deleted_at, category_source from daily_spends where id=1").fetchone() == (150000, None, None)

    # Idempotent re-run
    _alembic(copy_path, "stamp", "0013_debt_payments")
    _alembic(copy_path, "upgrade", "0014_spend_category_memory")

    # Downgrade refuses while soft-deleted rows remain
    c2.execute("update daily_spends set deleted_at = '2026-11-02 00:00:00' where id = 1")
    c2.commit()
    c2.close()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(copy_path, "downgrade", "0013_debt_payments")

    c3 = sqlite3.connect(copy_path)
    c3.execute("update daily_spends set deleted_at = NULL where id = 1")
    c3.commit()
    c3.close()
    _alembic(copy_path, "downgrade", "0013_debt_payments")

    c4 = sqlite3.connect(copy_path)
    tables_after = {r[0] for r in c4.execute("select name from sqlite_master where type='table'")}
    assert "spend_merchant_categories" not in tables_after
    cols_after = {r[1] for r in c4.execute("pragma table_info(daily_spends)")}
    assert "deleted_at" not in cols_after and "category_source" not in cols_after
    assert c4.execute("select amount_toman, note from daily_spends where id=1").fetchone() == (150000, "نان")
    c4.close()


def test_first_use_add_form_has_no_preselected_category(client, no_network):
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    assert '<option value="" selected>انتخاب دسته…</option>' in html
    assert '<option value="" selected>انتخاب زیردسته…</option>' in html
    assert re.search(r'<span class="sp-flabel" id="sp-cl"\s+hidden>', html)
    assert re.search(r'data-sp-cchips\s+hidden', html)

    csrf = _csrf(client, "/dashboard?tab=daily")
    r = client.post(
        "/profile/spends",
        data={"amount_toman": "120000", "category_id": "", "year": "1405", "month": "8", "day": "12", "jy": "1405", "jm": "8", "note": "قهوه", "csrf": csrf},
    )
    assert "دسته را انتخاب کنید" in r.text
    assert 'href="#sp-category_id"' in r.text


def test_category_change_and_undo_with_and_without_remember(client, no_network):
    _register(client, "alice")
    c_a, c_b, c_c, sms_bank_id = _pick_cats()

    r = client.post(
        "/api/sms-spend",
        json={"amount_toman": "185000", "idempotency_key": "1" * 64, "note": "برداشت اسنپ 1405/08/12"},
    )
    assert r.status_code == 200
    spend_id = r.json()["id"]

    daily_html = client.get("/dashboard?tab=daily").text
    assert "data-sp-catq" in daily_html
    assert "دسته؟" in daily_html

    rows = _api_spends_rows(client)
    assert rows[0]["is_sms_bank"] is True
    assert rows[0]["category_source"] is None

    csrf = _csrf(client, "/dashboard?tab=daily")

    # 1. Change without remembering
    c1 = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": c_a, "remember_merchant": False},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert c1.status_code == 200
    d1 = c1.json()
    assert d1["ok"] is True
    assert d1["category_id"] == c_a
    assert d1["is_sms_bank"] is False
    assert d1["undo_memory_id"] is None
    assert client.get("/api/merchant-categories").json()["items"] == []

    # Undo restores sms_bank
    u1 = client.patch(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": d1["prev_category_id"], "category_source": d1["prev_category_source"], "undo": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert u1.status_code == 200
    assert u1.json()["is_sms_bank"] is True

    # 2. Change WITH remember_merchant=True -> creates memory; undo deletes that newly created memory
    c2 = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": c_b, "remember_merchant": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert c2.status_code == 200
    d2 = c2.json()
    mem_id = d2["undo_memory_id"]
    assert isinstance(mem_id, int)
    assert len(client.get("/api/merchant-categories").json()["items"]) == 1

    u2 = client.patch(
        f"/profile/spends/{spend_id}/category",
        json={
            "category_id": d2["prev_category_id"],
            "category_source": d2["prev_category_source"],
            "undo": True,
            "undo_memory_id": mem_id,
        },
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert u2.status_code == 200
    assert client.get("/api/merchant-categories").json()["items"] == []

    # 3. Pre-existing memory updated via remember_merchant=True -> undo restores old category_id, does not delete
    c3 = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": c_b, "remember_merchant": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    existing_mem_id = c3.json()["undo_memory_id"]
    c4 = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": c_c, "remember_merchant": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    d4 = c4.json()
    assert d4["undo_memory_id"] is None
    assert d4["restore_memory_id"] == existing_mem_id
    assert d4["restore_memory_category_id"] == c_b

    u4 = client.patch(
        f"/profile/spends/{spend_id}/category",
        json={
            "category_id": d4["prev_category_id"],
            "category_source": d4["prev_category_source"],
            "undo": True,
            "restore_memory_id": d4["restore_memory_id"],
            "restore_memory_category_id": d4["restore_memory_category_id"],
        },
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert u4.status_code == 200
    mems = client.get("/api/merchant-categories").json()["items"]
    assert len(mems) == 1 and mems[0]["category_id"] == c_b

    # Invalid / sms category rejected
    bad = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": sms_bank_id},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert bad.status_code == 422

    # Other user cannot edit
    client.post("/logout", data={"csrf": csrf})
    _register(client, "bob")
    csrf_bob = _csrf(client, "/dashboard?tab=daily")
    r_other = client.post(
        f"/profile/spends/{spend_id}/category",
        json={"category_id": c_c},
        headers={"X-CSRF-Token": csrf_bob, "Accept": "application/json"},
    )
    assert r_other.status_code == 404


def test_learned_merchant_applies_to_next_sms_only_and_commission_wins(client, no_network):
    _register(client, "alice")
    c_a, _, _, _ = _pick_cats()

    # Older spend from same merchant stays untouched
    r_old = client.post(
        "/api/sms-spend",
        json={"amount_toman": "185000", "idempotency_key": "a" * 64, "note": "اسنپ"},
    ).json()
    r_fix = client.post(
        "/api/sms-spend",
        json={"amount_toman": "150000", "idempotency_key": "b" * 64, "note": "اسنپ"},
    ).json()
    csrf = _csrf(client, "/dashboard?tab=daily")
    client.post(
        f"/profile/spends/{r_fix['id']}/category",
        json={"category_id": c_a, "remember_merchant": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )

    # New SMS with ZWNJ + extra spaces matches the same merchant
    r_next = client.post(
        "/api/sms-spend",
        json={"amount_toman": "210000", "idempotency_key": "c" * 64, "note": "  اسنپ\u200c "},
    )
    assert r_next.status_code == 200
    next_id = r_next.json()["id"]

    # Commission (< 50,000) still wins over learned merchant
    r_comm = client.post(
        "/api/sms-spend",
        json={"amount_toman": "12000", "idempotency_key": "d" * 64, "note": "اسنپ"},
    )
    assert r_comm.status_code == 200
    comm_id = r_comm.json()["id"]

    spends = {s["id"]: s for s in _api_spends_rows(client)}
    assert spends[r_old["id"]]["is_sms_bank"] is True
    assert spends[r_old["id"]]["category_source"] is None
    assert spends[next_id]["category_id"] == c_a
    assert spends[next_id]["category_source"] == "learned"
    assert spends[next_id]["is_sms_bank"] is False
    assert spends[comm_id]["is_sms_bank"] is False
    assert spends[comm_id]["category_source"] is None

    daily_html = client.get("/dashboard?tab=daily").text
    assert '<span class="p6-learned">دستهٔ یادگرفته</span>' in daily_html

    prof_html = client.get("/profile").text
    assert 'id="learned-merchants"' in prof_html
    assert "فروشگاه‌های یادگرفته" in prof_html
    assert "اسنپ" in prof_html

    # Delete learned merchant -> past learned tag remains, future SMS goes back to sms_bank
    mem_id = client.get("/api/merchant-categories").json()["items"][0]["id"]
    del_r = client.delete(f"/api/merchant-categories/{mem_id}", headers={"X-CSRF-Token": csrf})
    assert del_r.status_code == 200 and del_r.json()["ok"] is True

    r_after = client.post(
        "/api/sms-spend",
        json={"amount_toman": "220000", "idempotency_key": "e" * 64, "note": "اسنپ"},
    ).json()
    spends2 = {s["id"]: s for s in _api_spends_rows(client)}
    assert spends2[next_id]["category_source"] == "learned"
    assert spends2[r_after["id"]]["is_sms_bank"] is True

    assert "هنوز فروشگاهی یاد گرفته نشده" in client.get("/profile").text


def test_merchant_key_normalization_and_empty_merchant_skips_memory(client, no_network):
    from app.models import merchant_name_key

    assert merchant_name_key("  كافه   فرضی ") == "کافه فرضی"
    assert merchant_name_key("اسنپ\u200c") == "اسنپ"
    assert merchant_name_key("  ") == ""

    _register(client, "alice")
    c_a, _, _, _ = _pick_cats()
    r = client.post(
        "/api/sms-spend",
        json={"amount_toman": "90000", "idempotency_key": "f" * 64, "note": "کارت 6037-9911-2233-4455 مانده 500000"},
    )
    assert r.status_code == 200
    csrf = _csrf(client, "/dashboard?tab=daily")
    res = client.post(
        f"/profile/spends/{r.json()['id']}/category",
        json={"category_id": c_a, "remember_merchant": True},
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert res.status_code == 200 and res.json()["undo_memory_id"] is None
    assert client.get("/api/merchant-categories").json()["items"] == []


def test_soft_delete_totals_restore_and_24h_cleanup(client, no_network):
    from app.db import SessionLocal
    from app.models import DailySpend, utcnow
    from app.spends import cleanup_deleted_spends

    _register(client, "alice")
    r_sms = client.post(
        "/api/sms-spend",
        json={"amount_toman": "250000", "idempotency_key": "9" * 64, "note": "فروشگاه فرضی آلفا"},
    )
    assert r_sms.status_code == 200
    sid = r_sms.json()["id"]
    csrf = _csrf(client, "/dashboard?tab=daily")

    # Soft delete
    d = client.post(
        f"/profile/spends/{sid}/delete",
        data={"csrf": csrf},
        headers={"Accept": "application/json"},
    )
    assert d.status_code == 200 and d.json()["ok"] is True

    # Excluded from API list, web list, and SMS idempotency lookup
    assert _api_spends_rows(client) == []
    assert "فروشگاه فرضی آلفا" not in client.get("/dashboard?tab=daily").text

    # Re-sending same idempotency_key while soft-deleted creates a distinct row
    r_dup = client.post(
        "/api/sms-spend",
        json={"amount_toman": "250000", "idempotency_key": "9" * 64, "note": "فروشگاه فرضی بتا"},
    )
    assert r_dup.status_code == 200 and r_dup.json()["id"] != sid

    # Restore brings back exact same row id, note, amount
    res = client.post(
        f"/profile/spends/{sid}/restore",
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    )
    assert res.status_code == 200 and res.json()["id"] == sid
    ids = [s["id"] for s in _api_spends_rows(client)]
    assert sid in ids

    # Already active -> 409
    assert client.post(
        f"/profile/spends/{sid}/restore",
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    ).status_code == 409

    # Soft delete again, test <24h vs >24h cleanup
    client.post(f"/profile/spends/{sid}/delete", data={"csrf": csrf}, headers={"Accept": "application/json"})
    with SessionLocal() as db:
        row = db.query(DailySpend).filter(DailySpend.id == sid).one()
        row.deleted_at = utcnow() - timedelta(hours=23)
        db.commit()
        assert cleanup_deleted_spends(db) == 0

        row = db.query(DailySpend).filter(DailySpend.id == sid).one()
        row.deleted_at = utcnow() - timedelta(hours=25)
        db.commit()
        assert cleanup_deleted_spends(db) == 1

    # After cleanup, restore returns 409
    assert client.post(
        f"/profile/spends/{sid}/restore",
        headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
    ).status_code == 409


def test_spending_page_js_copy_and_no_confirm_dialog():
    js = (ROOT / "app" / "static" / "spending-page.js").read_text(encoding="utf-8")
    tpl = (ROOT / "app" / "templates" / "partials" / "daily_spend.html").read_text(encoding="utf-8")
    assert "confirmDelete" not in js
    assert "حذف…" not in tpl
    assert ">حذف<" in tpl
    assert "دسته عوض شد" in js
    assert "خرج حذف شد" in js
    assert "بازگرداندن" in js
    assert "ذخیره نشد؛ دوباره بزنید" in js
    assert "برای «" in js and "همیشه همین دسته" in js
    assert "kids[0]" not in js
