"""Sanjeh token encrypted at rest: HKDF(SECRET_KEY) -> Fernet, "enc1:" prefix, migration 0005 up/down on a FAKE DB."""
import sqlite3
import subprocess
import sys

from tests.test_sanjeh_migration import ALEMBIC, _fake_db_at_0003, _insert

KEY = "fake-secret-key-for-migration-tests"


def _alembic(db, action, rev, key=KEY):
    env = {"DATA_DIR": str(db.parent), "PATH": "/usr/bin:/bin"}
    if key is not None:
        env["SECRET_KEY"] = key
    return subprocess.run([sys.executable, "-c", ALEMBIC, str(db), action, rev], env=env,
                          capture_output=True, text=True)


def _tokens(db):
    return dict(sqlite3.connect(db).execute("select id, sanjeh_token from users order by id").fetchall())


def _fake_db_at_0004(tmp_path):
    db = _fake_db_at_0003(tmp_path)  # user 1: plaintext FAKE-TOKEN-1, user 2: no token
    assert _alembic(db, "upgrade", "0004_sanjeh_status").returncode == 0
    c = sqlite3.connect(db)
    _insert(c, "users", id=3, username="fake_c", sanjeh_token="")
    c.commit(); c.close()
    return db


def test_roundtrip_prefix_and_key_derivation():
    from app.token_crypto import decrypt_token, encrypt_token, is_encrypted

    stored = encrypt_token("FAKE-TOKEN", KEY)
    assert stored.startswith("enc1:") and "FAKE-TOKEN" not in stored and is_encrypted(stored)
    assert decrypt_token(stored, KEY) == "FAKE-TOKEN"
    assert encrypt_token(stored, KEY) == stored  # never double-encrypted
    assert decrypt_token("legacy-plain", KEY) == "legacy-plain"  # rollout: old rows still readable
    assert len(encrypt_token("x" * 128, KEY)) <= 512


def test_rotated_secret_key_reads_as_none_never_raises():
    from app.token_crypto import decrypt_token, encrypt_token

    stored = encrypt_token("FAKE-TOKEN", KEY)
    assert decrypt_token(stored, "another-key") is None
    assert decrypt_token("enc1:garbage", KEY) is None
    assert decrypt_token(stored, "") is None


def test_migration_up_encrypts_is_idempotent_and_down_decrypts(tmp_path):
    from app.token_crypto import decrypt_token

    db = _fake_db_at_0004(tmp_path)
    assert _alembic(db, "upgrade", "head").returncode == 0
    t = _tokens(db)
    assert t[1].startswith("enc1:") and decrypt_token(t[1], KEY) == "FAKE-TOKEN-1"
    assert t[2] is None and t[3] == ""
    # re-run: the encrypted row is skipped (byte-identical), not double-encrypted
    assert _alembic(db, "stamp", "0004_sanjeh_status").returncode == 0
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _tokens(db) == t
    assert _alembic(db, "downgrade", "0004_sanjeh_status").returncode == 0
    assert _tokens(db) == {1: "FAKE-TOKEN-1", 2: None, 3: ""}


def test_downgrade_with_wrong_key_leaves_row_and_does_not_fail(tmp_path):
    db = _fake_db_at_0004(tmp_path)
    assert _alembic(db, "upgrade", "head").returncode == 0
    enc = _tokens(db)[1]
    assert _alembic(db, "downgrade", "0004_sanjeh_status", key="rotated-key").returncode == 0
    assert _tokens(db)[1] == enc


def test_migration_without_secret_key_refuses_to_store_plain_tokens(tmp_path):
    db = _fake_db_at_0004(tmp_path)
    r = _alembic(db, "upgrade", "head", key=None)
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr
    assert _tokens(db)[1] == "FAKE-TOKEN-1"  # transaction rolled back, nothing half-written


def test_orm_writes_encrypted_and_reads_plain(client):
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.add(User(username="fake_enc", password_hash="h", sanjeh_token="FAKE-ORM-TOKEN"))
        db.commit()
    with SessionLocal() as db:
        raw = db.execute(__import__("sqlalchemy").text("select sanjeh_token from users where username='fake_enc'")).scalar()
        assert raw.startswith("enc1:") and "FAKE-ORM-TOKEN" not in raw
        user = db.query(User).filter_by(username="fake_enc").one()
        assert user.sanjeh_token == "FAKE-ORM-TOKEN"
        assert db.query(User).filter(User.sanjeh_token.isnot(None), User.sanjeh_token != "").count() == 1


def test_unreadable_token_shows_reconnect_not_crash(client, monkeypatch):
    from sqlalchemy import text

    from app.car_routes import car_state
    from app.db import SessionLocal
    from app.models import User
    from app.token_crypto import encrypt_token

    with SessionLocal() as db:
        db.add(User(username="fake_rot", password_hash="h"))
        db.commit()
        db.execute(text("update users set sanjeh_token=:t where username='fake_rot'"),
                   {"t": encrypt_token("FAKE", "the-old-secret-key")})
        db.commit()
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="fake_rot").one()
        assert user.sanjeh_token is None
        assert car_state(user) == "none"  # the connect sheet asks for the token again
