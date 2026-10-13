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
