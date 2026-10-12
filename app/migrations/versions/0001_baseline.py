"""Baseline: frozen snapshot of the schema as it existed before Alembic (Oct 12 2026).

Do NOT import models here. Every statement is IF NOT EXISTS, so on an existing
database it only adds what is missing, then runs the legacy column adds.
Unknown tables (e.g. monthly_incomes on prod) are left untouched.

Revision ID: 0001_baseline
Revises:
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

_STATEMENTS = (
    'CREATE TABLE IF NOT EXISTS market_prices (\n\tsymbol VARCHAR(32) NOT NULL, \n\tprice_toman NUMERIC(24, 4) NOT NULL, \n\tsource_updated_at VARCHAR(64), \n\tfetched_at DATETIME NOT NULL, \n\tPRIMARY KEY (symbol)\n)',
    'CREATE TABLE IF NOT EXISTS users (\n\tid INTEGER NOT NULL, \n\tusername VARCHAR(32) NOT NULL, \n\tpassword_hash VARCHAR(128) NOT NULL, \n\tfull_name VARCHAR(80) NOT NULL, \n\tmobile VARCHAR(20) NOT NULL, \n\tsalary_toman NUMERIC(20, 2) NOT NULL, \n\tgold_grams NUMERIC(20, 8) NOT NULL, \n\tcoin_emami NUMERIC(20, 8) NOT NULL, \n\tcoin_bahar NUMERIC(20, 8) NOT NULL, \n\tcoin_half NUMERIC(20, 8) NOT NULL, \n\tcoin_quarter NUMERIC(20, 8) NOT NULL, \n\tcoin_gram NUMERIC(20, 8) NOT NULL, \n\tsilver_grams NUMERIC(20, 8) NOT NULL, \n\tbtc NUMERIC(20, 8) NOT NULL, \n\tada NUMERIC(20, 8) NOT NULL, \n\teth NUMERIC(20, 8) NOT NULL, \n\tsol NUMERIC(20, 8) NOT NULL, \n\tdoge NUMERIC(20, 8) NOT NULL, \n\tmatic NUMERIC(20, 8) NOT NULL, \n\tusd NUMERIC(20, 8) NOT NULL, \n\tcash_toman NUMERIC(20, 2) NOT NULL, \n\tcar_toman NUMERIC(20, 2) NOT NULL, \n\tcar_count INTEGER NOT NULL, \n\tsanjeh_token VARCHAR(128), \n\tmcp_token_hash VARCHAR(64), \n\tcar_fetched_at DATETIME, \n\tlast_login_at DATETIME, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (mcp_token_hash)\n)',
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)',
    'CREATE TABLE IF NOT EXISTS debts (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\ttitle VARCHAR(64) NOT NULL, \n\tmonthly_toman NUMERIC(20, 2) NOT NULL, \n\tmonths_left INTEGER NOT NULL, \n\tdue_year INTEGER NOT NULL, \n\tdue_month INTEGER NOT NULL, \n\tdue_day INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_debts_user_id ON debts (user_id)',
    'CREATE TABLE IF NOT EXISTS monthly_expenses (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\ttitle VARCHAR(64) NOT NULL, \n\tamount_toman NUMERIC(20, 2) NOT NULL, \n\tdue_day INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_monthly_expenses_user_id ON monthly_expenses (user_id)',
    'CREATE TABLE IF NOT EXISTS portfolio_snapshots (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\ttaken_at DATETIME NOT NULL, \n\ttotal_toman NUMERIC(24, 2) NOT NULL, \n\tbreakdown_json TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_user_id ON portfolio_snapshots (user_id)',
    'CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_taken_at ON portfolio_snapshots (taken_at)',
    'CREATE TABLE IF NOT EXISTS push_device_tokens (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\ttoken VARCHAR(512) NOT NULL, \n\tplatform VARCHAR(16) NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_push_device_tokens_user_id ON push_device_tokens (user_id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_push_device_tokens_token ON push_device_tokens (token)',
    'CREATE TABLE IF NOT EXISTS spend_categories (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tparent_id INTEGER, \n\tname VARCHAR(64) NOT NULL, \n\tslug VARCHAR(32), \n\tis_seed BOOLEAN NOT NULL, \n\tsort_order INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_spend_category_user_slug UNIQUE (user_id, slug), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(parent_id) REFERENCES spend_categories (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_spend_categories_user_id ON spend_categories (user_id)',
    'CREATE INDEX IF NOT EXISTS ix_spend_categories_parent_id ON spend_categories (parent_id)',
    'CREATE TABLE IF NOT EXISTS daily_spends (\n\tid INTEGER NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tcategory_id INTEGER NOT NULL, \n\tamount_toman NUMERIC(20, 2) NOT NULL, \n\tspent_on DATE NOT NULL, \n\tnote VARCHAR(120) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(category_id) REFERENCES spend_categories (id)\n)',
    'CREATE INDEX IF NOT EXISTS ix_daily_spends_user_id ON daily_spends (user_id)',
    'CREATE INDEX IF NOT EXISTS ix_daily_spends_spent_on ON daily_spends (spent_on)',
    'CREATE INDEX IF NOT EXISTS ix_daily_spends_category_id ON daily_spends (category_id)',
)

_USER_COLUMNS = (
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


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "users" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("users")}
        for name, ddl in _USER_COLUMNS:
            if name not in have:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
    if "debts" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("debts")}
        if "title" not in have:
            conn.execute(text("ALTER TABLE debts ADD COLUMN title VARCHAR(64) NOT NULL DEFAULT ''"))
    for stmt in _STATEMENTS:
        conn.execute(text(stmt))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_mcp_token_hash ON users (mcp_token_hash)"))


def downgrade() -> None:
    raise RuntimeError("baseline migration has no downgrade")
