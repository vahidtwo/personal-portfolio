"""Add admin_audit_log (new table only; existing tables and rows untouched).

Revision ID: 0003_admin_audit_log
Revises: 0002_holdings
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0003_admin_audit_log"
down_revision = "0002_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if "admin_audit_log" in inspect(conn).get_table_names():
        return
    conn.execute(text(
        "CREATE TABLE admin_audit_log ("
        "id INTEGER NOT NULL PRIMARY KEY, "
        "actor_username VARCHAR(32) NOT NULL, "
        "action VARCHAR(32) NOT NULL, "
        "targets_json TEXT NOT NULL, "
        "counts_json TEXT NOT NULL, "
        "backup_filename VARCHAR(128) NOT NULL, "
        "created_at DATETIME NOT NULL)"
    ))
    conn.execute(text("CREATE INDEX ix_admin_audit_log_created_at ON admin_audit_log (created_at)"))


def downgrade() -> None:
    op.get_bind().execute(text("DROP TABLE IF EXISTS admin_audit_log"))
