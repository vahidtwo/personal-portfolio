"""Add due_reminders (new table only; existing tables and rows untouched).

Revision ID: 0006_due_reminders
Revises: 0004_sanjeh_status
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0006_due_reminders"
down_revision = "0004_sanjeh_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if "due_reminders" in inspect(conn).get_table_names():
        return
    conn.execute(text(
        "CREATE TABLE due_reminders ("
        "id INTEGER NOT NULL PRIMARY KEY, "
        "user_id INTEGER NOT NULL, "
        "debt_id INTEGER NOT NULL, "
        "kind VARCHAR(16) NOT NULL, "
        "due_date VARCHAR(10) NOT NULL, "
        "sent_at DATETIME NOT NULL, "
        "CONSTRAINT uq_due_reminders_once UNIQUE (debt_id, kind, due_date))"
    ))
    conn.execute(text("CREATE INDEX ix_due_reminders_user_id ON due_reminders (user_id)"))
    conn.execute(text("CREATE INDEX ix_due_reminders_debt_id ON due_reminders (debt_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    if "due_reminders" in inspect(conn).get_table_names():
        conn.execute(text("DROP TABLE due_reminders"))
