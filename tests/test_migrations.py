import sqlite3
import subprocess
import sys

from sqlalchemy import create_engine, inspect


def _upgrade(tmp_path):
    env = {"DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    subprocess.run([sys.executable, "-c", "from app.db import init_db; init_db(); init_db()"],
                   env=env, check=True)
    return tmp_path / "inventory.db"


def test_upgrade_head_on_empty_db_matches_models(tmp_path):
    from app.db import Base
    from app import models  # noqa: F401

    db = _upgrade(tmp_path)
    insp = inspect(create_engine(f"sqlite:///{db}"))
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}, name


def test_upgrade_keeps_unknown_tables_and_rows(tmp_path):
    db = tmp_path / "inventory.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE monthly_incomes (id INTEGER PRIMARY KEY, v TEXT)")
    c.execute("INSERT INTO monthly_incomes VALUES (1, 'keep')")
    c.commit(); c.close()
    _upgrade(tmp_path)
    assert sqlite3.connect(db).execute("select * from monthly_incomes").fetchall() == [(1, "keep")]
