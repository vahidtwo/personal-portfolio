"""Add debts.deleted_at (soft delete) and debt_payments table (loan payment history).

No backfill: existing loans keep deleted_at = NULL and start with an empty payment history.
debt_payments.debt_id intentionally has NO ON DELETE CASCADE so payment rows survive loan soft-delete.
Idempotent: skips existing columns/tables.

Revision ID: 0013_debt_payments
Revises: 0012_monthly_expense_paid
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0013_debt_payments"
down_revision = "0012_monthly_expense_paid"
branch_labels = None
depends_on = None


def _debt_columns(conn) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns("debts")}


def upgrade() -> None:
    conn = op.get_bind()
    if "deleted_at" not in _debt_columns(conn):
        conn.execute(text("ALTER TABLE debts ADD COLUMN deleted_at DATETIME NULL"))
    if "debt_payments" not in inspect(conn).get_table_names():
        conn.execute(text(
            "CREATE TABLE debt_payments ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "debt_id INTEGER NOT NULL REFERENCES debts (id), "
            "user_id INTEGER NOT NULL REFERENCES users (id), "
            "paid_on DATE NOT NULL, "
            "amount_toman NUMERIC(20, 2) NOT NULL, "
            "kind VARCHAR(16) NOT NULL DEFAULT 'full', "
            "period_jy INTEGER NOT NULL, "
            "period_jm INTEGER NOT NULL, "
            "before_months_left INTEGER NOT NULL, "
            "before_due_year INTEGER NOT NULL, "
            "before_due_month INTEGER NOT NULL, "
            "before_due_day INTEGER NOT NULL, "
            "before_last_paid_on DATE NULL, "
            "created_at DATETIME NOT NULL)"
        ))
        conn.execute(text("CREATE INDEX ix_debt_payments_debt_id ON debt_payments (debt_id)"))
        conn.execute(text("CREATE INDEX ix_debt_payments_user_id ON debt_payments (user_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    if "debt_payments" in inspect(conn).get_table_names():
        conn.execute(text("DROP TABLE debt_payments"))
    if "deleted_at" in _debt_columns(conn):
        conn.execute(text("ALTER TABLE debts DROP COLUMN deleted_at"))
