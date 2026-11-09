"""Global spend categories: one shared list instead of a copy per user.

Revision ID: 0007_global_categories
Revises: 0006_due_reminders

Upgrade:
- per-user rows are merged into one global row per (parent, normalized name); the kept row is the
  lowest id of each group, so its id never changes
- daily_spends.category_id and spend_categories.parent_id are repointed to the kept rows, then the
  merged copies are deleted and user_id is dropped
- new columns: archived, icon, color, name_key; slug becomes globally unique;
  (COALESCE(parent_id, 0), name_key) is unique
- the default tree is completed once here (users who never opened the spend page had no copy);
  later an empty table gets it, a non-empty one is left alone so admin deletions stay deleted
- a database that is already global is left as is (re-run is a no-op)

Downgrade (reversible, with known loss):
- every user who has spends gets back a private copy of each category (and its parent) they use and
  their spends are repointed to it; the original ids stay with one user, the others get new ids
- default (seed) categories no spend uses are dropped: the old code adds them back per user on demand
- other categories no spend uses go to the lowest user id (dropped when there are no users)
- archived, icon, color and name_key are dropped (archived categories become ordinary ones)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0007_global_categories"
down_revision = "0006_due_reminders"
branch_labels = None
depends_on = None

NAME_INDEX = "uq_spend_categories_parent_name"
SLUG_UNIQUE = "uq_spend_categories_slug"

DEFAULT_TREE = (
    ("food", "خوراک", (("restaurant", "رستوران"), ("cafe", "کافه"), ("fast_food", "فست‌فود"),
                       ("groceries", "خواربار"), ("delivery", "پیک"))),
    ("transport", "حمل‌ونقل", (("fuel", "بنزین"), ("taxi", "تاکسی و اسنپ"), ("transit", "حمل‌ونقل عمومی"),
                               ("parking", "پارکینگ"), ("car_repair", "تعمیر خودرو"))),
    ("gifts", "هدیه", (("gift", "هدیه"), ("donation", "کمک"), ("ceremony", "مراسم"))),
    ("shopping", "خرید", (("clothes", "لباس"), ("home_goods", "لوازم خانه"), ("electronics", "لوازم دیجیتال"))),
    ("health", "سلامت", (("pharmacy", "داروخانه"), ("doctor", "پزشک"), ("personal_care", "بهداشت شخصی"))),
    ("fun", "تفریح", (("entertainment", "سرگرمی"), ("hobby", "علاقه"), ("travel", "سفر"))),
    ("bills", "قبض", (("mobile", "شارژ موبایل"), ("other_bill", "سایر قبض"))),
    ("other", "سایر", (("other_misc", "سایر"),)),
    ("sms", "پیامک", (("sms_bank", "بانک"),)),
)


class MergeConflict(RuntimeError):
    """Rows cannot be merged without a decision; nothing is changed."""


def name_key(name: str | None) -> str:
    """Matching key: Arabic ي/ك as Persian ی/ک, no ZWNJ, trimmed, inner spaces collapsed, case-folded."""
    text_ = (name or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u200c", "")
    return re.sub(r"\s+", " ", text_).strip().casefold()


def _cols(conn) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns("spend_categories")}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _add_defaults(conn) -> None:
    """Add every default category that is missing (by slug, else by parent and name); existing rows are not changed."""
    now = _now()

    def find_or_add(parent_id, slug, name, order):
        found = conn.execute(text("SELECT id FROM spend_categories WHERE slug = :s"), {"s": slug}).scalar()
        if found is None:
            found = conn.execute(text(
                "SELECT id FROM spend_categories WHERE COALESCE(parent_id, 0) = :p AND name_key = :k"),
                {"p": parent_id or 0, "k": name_key(name)}).scalar()
        if found is None:
            conn.execute(text(
                "INSERT INTO spend_categories (parent_id, name, name_key, slug, is_seed, sort_order, archived, created_at) "
                "VALUES (:p, :n, :k, :s, 1, :o, 0, :t)"),
                {"p": parent_id, "n": name, "k": name_key(name), "s": slug, "o": order, "t": now})
            found = conn.execute(text("SELECT id FROM spend_categories WHERE slug = :s"), {"s": slug}).scalar()
        return found

    for p_index, (p_slug, p_name, children) in enumerate(DEFAULT_TREE):
        pid = find_or_add(None, p_slug, p_name, p_index)
        for c_index, (c_slug, c_name) in enumerate(children):
            find_or_add(pid, c_slug, c_name, c_index)


def _seed_if_empty(conn) -> None:
    if not conn.execute(text("SELECT count(*) FROM spend_categories")).scalar():
        _add_defaults(conn)


def _ensure_name_index(conn) -> None:
    conn.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {NAME_INDEX} ON spend_categories (COALESCE(parent_id, 0), name_key)"))


def plan_merge(rows: list[dict]) -> tuple[dict[int, int], dict[int, str | None]]:
    """old id -> kept id, and kept id -> slug. Raises MergeConflict instead of guessing."""
    by_id = {r["id"]: r for r in rows}
    keep: dict[int, int] = {}
    groups: dict[tuple, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["parent_id"] is None:
            groups.setdefault((None, name_key(r["name"])), []).append(r)
    for (_, _key), members in groups.items():
        for m in members:
            keep[m["id"]] = members[0]["id"]
    child_groups: dict[tuple, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["parent_id"] is None:
            continue
        parent = by_id.get(r["parent_id"])
        if parent is None:
            raise MergeConflict(f"category {r['id']} points to missing parent {r['parent_id']}")
        if parent["parent_id"] is not None:
            raise MergeConflict(f"category {r['id']} is nested more than one level")
        if parent["user_id"] != r["user_id"]:
            raise MergeConflict(f"category {r['id']} has a parent of another user")
        child_groups.setdefault((keep[parent["id"]], name_key(r["name"])), []).append(r)
    for members in child_groups.values():
        for m in members:
            keep[m["id"]] = members[0]["id"]
    groups.update(child_groups)
    slugs: dict[int, str | None] = {}
    seen_slug: dict[str, int] = {}
    for members in groups.values():
        kept = members[0]["id"]
        distinct = sorted({m["slug"] for m in members if m["slug"]})
        if len(distinct) > 1:
            raise MergeConflict(f"categories {[m['id'] for m in members]} share a name but have slugs {distinct}")
        slug = distinct[0] if distinct else None
        if slug is not None:
            if slug in seen_slug and seen_slug[slug] != kept:
                raise MergeConflict(f"slug {slug!r} is used by two different categories ({seen_slug[slug]}, {kept})")
            seen_slug[slug] = kept
        slugs[kept] = slug
    return keep, slugs


def _open_transaction(conn) -> None:
    """pysqlite starts a transaction only before DML; without this the DDL below would autocommit one by one."""
    conn.execute(text("UPDATE alembic_version SET version_num = version_num"))


def upgrade() -> None:
    conn = op.get_bind()
    _open_transaction(conn)
    if "user_id" not in _cols(conn):
        _ensure_name_index(conn)
        _seed_if_empty(conn)
        return
    rows = [dict(r._mapping) for r in conn.execute(text(
        "SELECT id, user_id, parent_id, name, slug, is_seed FROM spend_categories ORDER BY id"))]
    keep, slugs = plan_merge(rows)
    seeded = {keep[r["id"]] for r in rows if r["is_seed"]}
    orphans = conn.execute(text(
        "SELECT count(*) FROM daily_spends WHERE category_id NOT IN (SELECT id FROM spend_categories)")).scalar()
    if orphans:
        raise MergeConflict(f"{orphans} daily spends point to a missing category")
    moved = [(new, old) for old, new in keep.items() if old != new]
    for new, old in moved:
        conn.execute(text("UPDATE daily_spends SET category_id = :n WHERE category_id = :o"), {"n": new, "o": old})
        conn.execute(text("UPDATE spend_categories SET parent_id = :n WHERE parent_id = :o"), {"n": new, "o": old})
    for _new, old in moved:
        conn.execute(text("DELETE FROM spend_categories WHERE id = :o"), {"o": old})
    for kept, slug in slugs.items():
        conn.execute(text("UPDATE spend_categories SET slug = :s, is_seed = :seed WHERE id = :i"),
                     {"s": slug, "seed": kept in seeded, "i": kept})

    conn.execute(text("DROP INDEX IF EXISTS ix_spend_categories_user_id"))
    with op.batch_alter_table("spend_categories", recreate="always") as batch:
        batch.drop_constraint("uq_spend_category_user_slug", type_="unique")
        batch.drop_column("user_id")
        batch.add_column(sa.Column("name_key", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("icon", sa.String(16), nullable=True))
        batch.add_column(sa.Column("color", sa.String(16), nullable=True))
        batch.create_unique_constraint(SLUG_UNIQUE, ["slug"])
    for r in conn.execute(text("SELECT id, name FROM spend_categories")).fetchall():
        conn.execute(text("UPDATE spend_categories SET name_key = :k WHERE id = :i"), {"k": name_key(r.name), "i": r.id})
    _ensure_name_index(conn)
    _add_defaults(conn)


def downgrade() -> None:
    conn = op.get_bind()
    _open_transaction(conn)
    if "user_id" in _cols(conn):
        return
    conn.execute(text(f"DROP INDEX IF EXISTS {NAME_INDEX}"))
    with op.batch_alter_table("spend_categories", recreate="always") as batch:
        batch.drop_constraint(SLUG_UNIQUE, type_="unique")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    cats = {r.id: dict(r._mapping) for r in conn.execute(text(
        "SELECT id, parent_id, name, slug, is_seed, sort_order, created_at FROM spend_categories ORDER BY id"))}
    needs: dict[int, set[int]] = {}
    for uid, cid in conn.execute(text("SELECT DISTINCT user_id, category_id FROM daily_spends")).fetchall():
        if cid not in cats:
            continue
        needs.setdefault(cid, set()).add(uid)
        pid = cats[cid]["parent_id"]
        if pid is not None:
            needs.setdefault(pid, set()).add(uid)
    for cid in sorted(cats, key=lambda i: cats[i]["parent_id"] is None):
        c = cats[cid]
        has_child = any(o["parent_id"] == cid for o in cats.values())
        if c["is_seed"] and cid not in needs and not has_child:
            conn.execute(text("DELETE FROM spend_categories WHERE id = :i"), {"i": cid})
            del cats[cid]
    default_uid = conn.execute(text("SELECT min(id) FROM users")).scalar()
    owner: dict[int, int | None] = {}
    for cid, c in cats.items():
        if c["parent_id"] is None:
            owner[cid] = min(needs[cid]) if needs.get(cid) else default_uid
    for cid, c in cats.items():
        if c["parent_id"] is not None:
            owner[cid] = owner.get(c["parent_id"], default_uid)
    for cid, uid in owner.items():
        conn.execute(text("UPDATE spend_categories SET user_id = :u WHERE id = :i"), {"u": uid, "i": cid})

    copies: dict[tuple[int, int], int] = {}

    def copy_for(uid: int, cid: int) -> int:
        if owner[cid] == uid:
            return cid
        if (uid, cid) in copies:
            return copies[(uid, cid)]
        c = cats[cid]
        parent = copy_for(uid, c["parent_id"]) if c["parent_id"] is not None else None
        conn.execute(text(
            "INSERT INTO spend_categories (user_id, parent_id, name, slug, is_seed, sort_order, created_at) "
            "VALUES (:u, :p, :n, :s, :seed, :o, :t)"),
            {"u": uid, "p": parent, "n": c["name"], "s": c["slug"], "seed": c["is_seed"], "o": c["sort_order"],
             "t": c["created_at"]})
        new_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
        copies[(uid, cid)] = new_id
        return new_id

    for cid in sorted(needs):
        for uid in sorted(needs[cid]):
            new_id = copy_for(uid, cid)
            if new_id != cid:
                conn.execute(text("UPDATE daily_spends SET category_id = :n WHERE user_id = :u AND category_id = :o"),
                             {"n": new_id, "u": uid, "o": cid})
    if default_uid is None:
        conn.execute(text("DELETE FROM spend_categories WHERE user_id IS NULL AND parent_id IS NOT NULL"))
        conn.execute(text("DELETE FROM spend_categories WHERE user_id IS NULL"))

    order = ("id", "user_id", "parent_id", "name", "slug", "is_seed", "sort_order", "created_at")
    with op.batch_alter_table("spend_categories", recreate="always", partial_reordering=[order]) as batch:
        batch.drop_column("name_key")
        batch.drop_column("archived")
        batch.drop_column("icon")
        batch.drop_column("color")
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch.create_unique_constraint("uq_spend_category_user_slug", ["user_id", "slug"])
        batch.create_foreign_key("fk_spend_categories_user_id_users", "users", ["user_id"], ["id"])
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_spend_categories_user_id ON spend_categories (user_id)"))
