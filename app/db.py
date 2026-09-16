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
)


def _migrate_user_holdings() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("users")}
    with engine.begin() as conn:
        for name, ddl in _USER_HOLDING_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_user_holdings()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
