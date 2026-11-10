"""Add nullable debts.reminder_days_before (one new column only; existing rows untouched).

NULL = the default (1 day before), 0 = on the due day, -1 = no upcoming reminder (the overdue notice
still goes out), N > 0 = N days before. Idempotent: skipped if the column already exists.

Revision ID: 0008_debt_reminder_days
Revises: 0007_global_categories
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0008_debt_reminder_days"
down_revision = "0007_global_categories"
branch_labels = None
depends_on = None


def _has_column(conn) -> bool:
    return any(c["name"] == "reminder_days_before" for c in inspect(conn).get_columns("debts"))


def upgrade() -> None:
    conn = op.get_bind()
    if _has_column(conn):
        return
    # SQLite ADD COLUMN with NULL default: metadata-only, no row is rewritten.
    conn.execute(text("ALTER TABLE debts ADD COLUMN reminder_days_before INTEGER NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn):
        return
    # SQLite >= 3.35 supports DROP COLUMN; only this column is removed (no index or constraint uses it).
    conn.execute(text("ALTER TABLE debts DROP COLUMN reminder_days_before"))
