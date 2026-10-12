from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, DATABASE_URL


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


_USER_HOLDING_COLUMNS = (
    ("sol", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("doge", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("matic", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("cash_toman", "NUMERIC(20, 2) NOT NULL DEFAULT 0"),
    ("silver_grams", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("coin_emami", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("coin_bahar", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("coin_half", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("coin_quarter", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("coin_gram", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ("car_count", "INTEGER NOT NULL DEFAULT 0"),
    ("sanjeh_token", "VARCHAR(128)"),
    ("mcp_token_hash", "VARCHAR(64)"),
    ("car_fetched_at", "DATETIME"),
    ("last_login_at", "DATETIME"),
    ("full_name", "VARCHAR(80) NOT NULL DEFAULT ''"),
    ("mobile", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("salary_toman", "NUMERIC(20, 2) NOT NULL DEFAULT 0"),
)


def legacy_column_migrations(conn) -> None:
    """Pre-Alembic ad-hoc column adds. Idempotent; used by the baseline migration."""
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "users" in tables:
        existing = {c["name"] for c in inspector.get_columns("users")}
        for name, ddl in _USER_HOLDING_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_mcp_token_hash "
                "ON users (mcp_token_hash)"
            )
        )
    if "debts" in tables:
        existing = {c["name"] for c in inspector.get_columns("debts")}
        if "title" not in existing:
            conn.execute(text("ALTER TABLE debts ADD COLUMN title VARCHAR(64) NOT NULL DEFAULT ''"))


def init_db() -> None:
    """Bring the database to the latest schema via Alembic (safe on existing DBs)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app import models  # noqa: F401

    root = Path(__file__).resolve().parent
    cfg = Config()
    cfg.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
