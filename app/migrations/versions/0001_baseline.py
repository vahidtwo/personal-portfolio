"""Baseline: the schema as it existed before Alembic.

Idempotent on purpose. On an existing database it only adds what is
missing (same as the old init_db), and never drops or rewrites data.
Tables not in the models (e.g. monthly_incomes on prod) are left alone.

Revision ID: 0001_baseline
Revises:
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db import Base, legacy_column_migrations
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    legacy_column_migrations(bind)


def downgrade() -> None:
    # Baseline cannot be downgraded: that would mean deleting user data.
    raise RuntimeError("baseline migration has no downgrade")
