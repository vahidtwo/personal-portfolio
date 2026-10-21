"""Add nullable users.sanjeh_status (one new column only; existing rows untouched, NULL = connected/unknown).

Values written by the app: 'ok' | 'rejected' | 'failed'. Idempotent: skipped if the column already exists.

Revision ID: 0004_sanjeh_status
Revises: 0003_admin_audit_log
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0004_sanjeh_status"
down_revision = "0003_admin_audit_log"
branch_labels = None
depends_on = None


def _has_column(conn) -> bool:
    return any(c["name"] == "sanjeh_status" for c in inspect(conn).get_columns("users"))


def upgrade() -> None:
    conn = op.get_bind()
    if _has_column(conn):
        return
    # SQLite ADD COLUMN with NULL default: metadata-only, no row is rewritten.
    conn.execute(text("ALTER TABLE users ADD COLUMN sanjeh_status VARCHAR(16) NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn):
        return
    # SQLite >= 3.35 supports DROP COLUMN; only this column is removed.
    conn.execute(text("ALTER TABLE users DROP COLUMN sanjeh_status"))
