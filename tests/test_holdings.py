import re
import sqlite3
from decimal import Decimal

import pytest


def _csrf(client, path="/profile"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def _register(client, username="alice"):
    t = _csrf(client, "/register")
    client.post("/register", data={"username": username, "password": "password123",
                                   "password_confirm": "password123", "csrf": t})


@pytest.fixture()
def no_network(monkeypatch):
    import app.profile as profile

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(profile, "refresh_prices_and_snapshot_user", _noop)
    return profile


def _raw(username, col):
    from app.config import DATA_DIR
    c = sqlite3.connect(DATA_DIR / "inventory.db")
    uid = c.execute("select id from users where username=?", (username,)).fetchone()[0]
    legacy = c.execute(f"select {col} from users where id=?", (uid,)).fetchone()[0]
    h = c.execute("select quantity from holdings where user_id=? and asset_key=?", (uid, col)).fetchone()
    return legacy, (h[0] if h else None)


def test_profile_save_writes_holdings_and_legacy_and_zero_sticks(client, no_network):
    _register(client)
    client.post("/profile", data={"btc": "0.5", "cash_toman": "1000", "csrf": _csrf(client)})
    assert _raw("alice", "btc") == (0.5, 0.5)
    assert _raw("alice", "cash_toman")[1] == 1000
    client.post("/profile", data={"btc": "0", "cash_toman": "1000", "csrf": _csrf(client)})
    legacy, holding = _raw("alice", "btc")
    assert legacy == 0 and holding == 0  # no resurrection of the old value


def test_sanjeh_failure_still_saves_other_assets(client, no_network, monkeypatch):
    async def boom(user):
        raise RuntimeError("sanjeh down")

    monkeypatch.setattr(no_network, "refresh_user_sanjeh_car", boom)
    _register(client)
    r = client.post("/profile", data={"gold_grams": "3", "sanjeh_token": "tok", "csrf": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _raw("alice", "gold_grams") == (3, 3)


def test_user_properties_read_holdings():
    from app.models import User

    u = User(username="x", password_hash="h")
    assert u.btc == Decimal("0") and u.car_count == 0
    u.btc = Decimal("1.25")
    u.car_count = 2
    assert u.btc == Decimal("1.25") and u._legacy_btc == Decimal("1.25")
    assert u.car_count == 2 and isinstance(u.car_count, int)


def test_0002_copies_existing_amounts(tmp_path):
    import subprocess, sys
    db = tmp_path / "inventory.db"
    env = {"DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    code = ("from alembic import command; from alembic.config import Config; from pathlib import Path;"
            "import app.db as d; cfg=Config(); cfg.set_main_option('script_location', str(Path(d.__file__).parent/'migrations'));"
            "import sys; command.upgrade(cfg, sys.argv[1])")
    subprocess.run([sys.executable, "-c", code, "0001_baseline"], env=env, check=True)
    c = sqlite3.connect(db)
    vals = {"id": 1, "username": "a", "password_hash": "h", "btc": 0.12345678, "usd": 0,
            "gold_grams": 2.5, "car_count": 1, "created_at": "2026-01-01"}
    for _, name, typ, notnull, default, _pk in c.execute("pragma table_info(users)").fetchall():
        if notnull and default is None and name not in vals:
            vals[name] = "" if "CHAR" in typ.upper() else 0
    c.execute(f"insert into users ({','.join(vals)}) values ({','.join('?' * len(vals))})", list(vals.values()))
    c.commit(); c.close()
    subprocess.run([sys.executable, "-c", code, "head"], env=env, check=True)
    rows = dict(sqlite3.connect(db).execute("select asset_key, quantity from holdings where user_id=1"))
    assert rows["gold_grams"] == 2.5 and rows["car_count"] == 1 and "usd" not in rows
    assert abs(rows["btc"] - 0.12345678) < 1e-9  # NUMERIC(20, 8): 8 decimal places
