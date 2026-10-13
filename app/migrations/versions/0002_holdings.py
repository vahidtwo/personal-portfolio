"""Move per-asset quantities from users columns into a holdings table.

Copies every non-zero amount (one row per user per asset). Legacy columns
are kept and still written by the app during the transition; 0003 drops them.

Revision ID: 0002_holdings
Revises: 0001_baseline
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0002_holdings"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# Frozen list as of this migration; do not import from app.models.
KEYS = (
    "gold_grams", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram",
    "silver_grams", "btc", "ada", "eth", "sol", "doge", "matic", "usd", "cash_toman", "car_count",
)


def upgrade() -> None:
    conn = op.get_bind()
    if "holdings" not in inspect(conn).get_table_names():
        conn.execute(text(
            "CREATE TABLE holdings ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "user_id INTEGER NOT NULL REFERENCES users (id), "
            "asset_key VARCHAR(32) NOT NULL, "
            "quantity NUMERIC(20, 8) NOT NULL, "
            "updated_at DATETIME NOT NULL, "
            "CONSTRAINT uq_holdings_user_asset UNIQUE (user_id, asset_key))"
        ))
        conn.execute(text("CREATE INDEX ix_holdings_user_id ON holdings (user_id)"))
    for key in KEYS:
        # Copy as TEXT-faithful value; skip zero/NULL (absence means 0).
        conn.execute(text(
            f"INSERT OR IGNORE INTO holdings (user_id, asset_key, quantity, updated_at) "
            f"SELECT id, :key, {key}, CURRENT_TIMESTAMP FROM users "
            f"WHERE {key} IS NOT NULL AND CAST({key} AS REAL) != 0"
        ), {"key": key})


def downgrade() -> None:
    conn = op.get_bind()
    # Write current holdings back into the legacy columns before dropping.
    for key in KEYS:
        conn.execute(text(
            f"UPDATE users SET {key} = COALESCE((SELECT quantity FROM holdings h "
            f"WHERE h.user_id = users.id AND h.asset_key = :key), 0)"
        ), {"key": key})
    conn.execute(text("DROP TABLE holdings"))
