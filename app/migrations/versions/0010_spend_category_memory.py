"""Add spend_merchant_categories table and daily_spends.deleted_at + category_source.

Idempotent migration on top of 0009_default_group_icons. No backfill: existing spends stay
visible (deleted_at IS NULL) with category_source NULL, and no merchant memories are invented.

Revision ID: 0010_spend_category_memory
Revises: 0009_default_group_icons
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0010_spend_category_memory"
down_revision = "0009_default_group_icons"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return name in inspect(conn).get_table_names()


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set[str]:
    return {idx["name"] for idx in inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "spend_merchant_categories"):
        conn.execute(
            text(
                """
                CREATE TABLE spend_merchant_categories (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    merchant_key VARCHAR(80) NOT NULL,
                    merchant_label VARCHAR(80) NOT NULL,
                    category_id INTEGER NOT NULL REFERENCES spend_categories(id),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_spend_merchant_user_key UNIQUE (user_id, merchant_key)
                )
                """
            )
        )
    idx = _indexes(conn, "spend_merchant_categories")
    if "ix_spend_merchant_categories_user_id" not in idx:
        conn.execute(text("CREATE INDEX ix_spend_merchant_categories_user_id ON spend_merchant_categories (user_id)"))
    if "ix_spend_merchant_categories_category_id" not in idx:
        conn.execute(text("CREATE INDEX ix_spend_merchant_categories_category_id ON spend_merchant_categories (category_id)"))

    cols = _columns(conn, "daily_spends")
    if "deleted_at" not in cols:
        conn.execute(text("ALTER TABLE daily_spends ADD COLUMN deleted_at DATETIME NULL"))
    if "category_source" not in cols:
        conn.execute(text("ALTER TABLE daily_spends ADD COLUMN category_source VARCHAR(16) NULL"))
    if "ix_daily_spends_deleted_at" not in _indexes(conn, "daily_spends"):
        conn.execute(text("CREATE INDEX ix_daily_spends_deleted_at ON daily_spends (deleted_at)"))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _columns(conn, "daily_spends")
    if "deleted_at" in cols:
        remaining = conn.execute(text("SELECT COUNT(*) FROM daily_spends WHERE deleted_at IS NOT NULL")).scalar() or 0
        if remaining:
            raise RuntimeError("Cannot downgrade while soft-deleted daily_spends rows exist; run cleanup first")
    if "ix_daily_spends_deleted_at" in _indexes(conn, "daily_spends"):
        conn.execute(text("DROP INDEX ix_daily_spends_deleted_at"))
    cols = _columns(conn, "daily_spends")
    if "category_source" in cols:
        conn.execute(text("ALTER TABLE daily_spends DROP COLUMN category_source"))
    if "deleted_at" in cols:
        conn.execute(text("ALTER TABLE daily_spends DROP COLUMN deleted_at"))
    if _has_table(conn, "spend_merchant_categories"):
        conn.execute(text("DROP TABLE spend_merchant_categories"))
