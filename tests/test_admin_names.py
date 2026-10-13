import re


def _csrf(client, path):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def _reg(client, name):
    t = _csrf(client, "/register")
    return client.post("/register", data={"username": name, "password": "password123",
                                          "password_confirm": "password123", "csrf": t})


def _names():
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        return {u.username for u in db.query(User)}
    finally:
        db.close()


def _admins(monkeypatch, *names):
    import app.security as s
    monkeypatch.setattr(s, "ADMIN_USERNAMES", frozenset(names))


def test_signup_with_admin_name_blocked_once_users_exist(client, monkeypatch):
    _admins(monkeypatch, "boss")
    _reg(client, "alice")
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    _reg(client, "Boss")
    assert "boss" not in _names()


def test_first_signup_may_bootstrap_admin(client, monkeypatch):
    _admins(monkeypatch, "boss")
    _reg(client, "boss")
    assert "boss" in _names()


def test_admin_name_change_rules():
    import app.security as s
    s.ADMIN_USERNAMES = frozenset({"boss"})
    try:
        assert s.admin_name_change_error("alice", "BOSS")  # into admin name
        assert s.admin_name_change_error("boss", "bob")  # out of admin name
        assert s.admin_name_change_error("boss", "boss") is None
        assert s.admin_name_change_error("alice", "alice2") is None
        assert s.admin_name_change_error(None, "boss")  # new user via editor
    finally:
        s.ADMIN_USERNAMES = frozenset()


def test_profile_rename_into_admin_name_blocked(client, monkeypatch):
    _admins(monkeypatch, "boss")
    _reg(client, "alice")
    t = _csrf(client, "/profile")
    client.post("/profile/account", data={"username": "boss", "full_name": "", "mobile": "",
                                          "salary_toman": "0", "csrf": t})
    assert _names() == {"alice"}
