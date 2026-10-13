import re
from datetime import datetime, timezone
from decimal import Decimal


def _csrf(client, path):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def _setup(client, monkeypatch):
    import app.config as config
    import app.admin_users as au
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, User
    from app.security import hash_password

    db = SessionLocal()
    admin = User(username="boss", password_hash=hash_password("password123"))
    victim = User(username="victim", password_hash=hash_password("password123"))
    empty = User(username="empty", password_hash=hash_password("password123"))
    db.add_all([admin, victim, empty]); db.commit()
    db.add(PortfolioSnapshot(user_id=victim.id, taken_at=datetime.now(timezone.utc), total_toman=Decimal("0"), breakdown_json="{}"))
    db.commit()
    ids = (victim.id, empty.id); db.close()
    monkeypatch.setattr("app.security.ADMIN_USERNAMES", frozenset({"boss"}), raising=False)
    for mod in ("app.admin_users", "app.db_admin", "app.config"):
        import importlib; m = importlib.import_module(mod)
        if hasattr(m, "ADMIN_USERNAMES"):
            monkeypatch.setattr(m, "ADMIN_USERNAMES", frozenset({"boss"}))
    t = _csrf(client, "/login")
    client.post("/login", data={"username": "boss", "password": "password123", "csrf": t})
    return ids


def _exists(uid):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        return db.get(User, uid) is not None
    finally:
        db.close()


def test_admin_cannot_delete_user_with_data(client, monkeypatch):
    victim, empty = _setup(client, monkeypatch)
    t = _csrf(client, "/admin")
    client.post(f"/admin/users/{victim}/delete", data={"csrf": t})
    assert _exists(victim)
    client.post(f"/admin/db/users/{victim}/delete", data={"csrf": t})
    assert _exists(victim)


def test_admin_can_still_delete_empty_user(client, monkeypatch):
    victim, empty = _setup(client, monkeypatch)
    t = _csrf(client, "/admin")
    client.post(f"/admin/users/{empty}/delete", data={"csrf": t})
    assert not _exists(empty)


def test_db_editor_user_data_tables_are_read_only(client, monkeypatch):
    victim, empty = _setup(client, monkeypatch)
    from app.db import SessionLocal
    from app.models import PortfolioSnapshot, SpendCategory
    db = SessionLocal()
    snap = db.query(PortfolioSnapshot).filter_by(user_id=victim).first()
    db.add(SpendCategory(user_id=victim, name="x")); db.commit()
    cat = db.query(SpendCategory).filter_by(user_id=victim).first()
    sid, cid = snap.id, cat.id; db.close()
    t = _csrf(client, "/admin")
    for path in (f"/admin/db/snapshots/{sid}/delete", f"/admin/db/spend-categories/{cid}/delete",
                 f"/admin/db/snapshots/{sid}", f"/admin/db/spend-categories/{cid}",
                 "/admin/db/snapshots/new", "/admin/db/spend-categories/new"):
        client.post(path, data={"csrf": t, "total_toman": "0", "user_id": str(empty), "name": "y",
                                "taken_at": "2026-01-01T00:00"})
    db = SessionLocal()
    s = db.get(PortfolioSnapshot, sid); c = db.get(SpendCategory, cid)
    assert s is not None and s.user_id == victim
    assert c is not None and c.user_id == victim and c.name == "x"
    assert db.query(PortfolioSnapshot).count() == 1
    db.close()


def test_db_editor_cannot_change_user_assets(client, monkeypatch):
    victim, empty = _setup(client, monkeypatch)
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal(); u = db.get(User, victim); u.btc = 2; db.commit(); db.close()
    t = _csrf(client, "/admin")
    client.post(f"/admin/db/users/{victim}", data={"csrf": t, "username": "victim", "btc": "0", "car_count": "0"})
    db = SessionLocal(); assert db.get(User, victim).btc == 2; db.close()
