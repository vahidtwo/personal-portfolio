"""Default spend groups get an emoji icon (data only; no schema change).

Only the 9 default groups (matched by slug, top level) whose icon is empty get one; any icon an admin set is
left alone, and no other row or column is touched. Re-running is a no-op.
Downgrade clears exactly these emoji again (only where the icon is still the one written here).

Revision ID: 0009_default_group_icons
Revises: 0008_debt_reminder_days
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0009_default_group_icons"
down_revision = "0008_debt_reminder_days"
branch_labels = None
depends_on = None

# Frozen copy of app.category_style.DEFAULT_GROUP_ICONS at the time of this migration.
ICONS = {
    "food": "🍽️",
    "transport": "🚗",
    "gifts": "🎁",
    "shopping": "🛍️",
    "health": "💊",
    "fun": "🎉",
    "bills": "🧾",
    "other": "📦",
    "sms": "💬",
}


def _ready(conn) -> bool:
    insp = inspect(conn)
    return "spend_categories" in insp.get_table_names() and any(
        c["name"] == "icon" for c in insp.get_columns("spend_categories"))


def upgrade() -> None:
    conn = op.get_bind()
    if not _ready(conn):
        return
    for slug, icon in ICONS.items():
        conn.execute(text(
            "UPDATE spend_categories SET icon = :icon "
            "WHERE slug = :slug AND parent_id IS NULL AND (icon IS NULL OR TRIM(icon) = '')"
        ), {"icon": icon, "slug": slug})


def downgrade() -> None:
    conn = op.get_bind()
    if not _ready(conn):
        return
    for slug, icon in ICONS.items():
        conn.execute(text(
            "UPDATE spend_categories SET icon = NULL WHERE slug = :slug AND parent_id IS NULL AND icon = :icon"
        ), {"icon": icon, "slug": slug})
