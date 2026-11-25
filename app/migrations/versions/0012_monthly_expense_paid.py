"""Add nullable monthly_expenses.paid_jy and paid_jm (per-month paid mark).

No backfill: existing rows stay NULL and show as unpaid for the current Jalali month.
Idempotent: skips any column that already exists.

Revision ID: 0012_monthly_expense_paid
Revises: 0010_debt_last_paid_on
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0012_monthly_expense_paid"
down_revision = "0010_debt_last_paid_on"
branch_labels = None
depends_on = None


def _columns(conn) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns("monthly_expenses")}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _columns(conn)
    for name in ("paid_jy", "paid_jm"):
        if name not in cols:
            conn.execute(text(f"ALTER TABLE monthly_expenses ADD COLUMN {name} INTEGER NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _columns(conn)
    for name in ("paid_jm", "paid_jy"):
        if name in cols:
            conn.execute(text(f"ALTER TABLE monthly_expenses DROP COLUMN {name}"))
