"""Add nullable debts.last_paid_on (one new column only; existing rows stay NULL).

Tehran calendar date of the last «پرداخت شد». No backfill: a loan paid before this
revision keeps NULL until it is paid again. Idempotent: skipped if the column already exists.

Revision ID: 0010_debt_last_paid_on
Revises: 0009_default_group_icons
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0010_debt_last_paid_on"
down_revision = "0009_default_group_icons"
branch_labels = None
depends_on = None


def _has_column(conn) -> bool:
    return any(c["name"] == "last_paid_on" for c in inspect(conn).get_columns("debts"))


def upgrade() -> None:
    conn = op.get_bind()
    if _has_column(conn):
        return
    # SQLite ADD COLUMN with NULL default: metadata-only, no row is rewritten.
    conn.execute(text("ALTER TABLE debts ADD COLUMN last_paid_on DATE NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn):
        return
    # SQLite >= 3.35 supports DROP COLUMN; only this column is removed (no index or constraint uses it).
    conn.execute(text("ALTER TABLE debts DROP COLUMN last_paid_on"))
