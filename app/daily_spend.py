"""One-off daily spends. Separate from recurring monthly expenses and مانده."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DailySpend, SpendCategory, User

# slug, Persian label, subcategories (slug, label)
DAILY_SPEND_TREE: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "food",
        "خوراک",
        (
            ("restaurant", "رستوران"),
            ("cafe", "کافه"),
            ("fast_food", "فست‌فود"),
            ("groceries", "خواربار"),
            ("delivery", "پیک"),
        ),
    ),
    (
        "transport",
        "حمل‌ونقل",
        (
            ("fuel", "بنزین"),
            ("taxi", "تاکسی و اسنپ"),
            ("transit", "حمل‌ونقل عمومی"),
            ("parking", "پارکینگ"),
            ("car_repair", "تعمیر خودرو"),
        ),
    ),
    (
        "gifts",
        "هدیه",
        (
            ("gift", "هدیه"),
            ("donation", "کمک"),
            ("ceremony", "مراسم"),
        ),
    ),
    (
        "shopping",
        "خرید",
        (
            ("clothes", "لباس"),
            ("home_goods", "لوازم خانه"),
            ("electronics", "لوازم دیجیتال"),
        ),
    ),
    (
        "health",
        "سلامت",
        (
            ("pharmacy", "داروخانه"),
            ("doctor", "پزشک"),
            ("personal_care", "بهداشت شخصی"),
        ),
    ),
    (
        "fun",
        "تفریح",
        (
            ("entertainment", "سرگرمی"),
            ("hobby", "علاقه"),
            ("travel", "سفر"),
        ),
    ),
    (
        "bills",
        "قبض",
        (
            ("mobile", "شارژ موبایل"),
            ("other_bill", "سایر قبض"),
        ),
    ),
    (
        "other",
        "سایر",
        (("other_misc", "سایر"),),
    ),
    (
        "sms",
        "پیامک",
        (("sms_bank", "بانک"),),
    ),
)

PARENT_COLORS = {
    # Darkened so a white initial reaches >=4.5:1; «قبض» and «پیامک» no longer share a colour.
    "food": "#c2410c",
    "transport": "#1d4ed8",
    "gifts": "#be185d",
    "shopping": "#7c3aed",
    "health": "#047857",
    "fun": "#b45309",
    "bills": "#0f766e",
    "other": "#475569",
    "sms": "#0e7490",
}
_EXTRA_COLORS = ("#0369a1", "#b45309", "#4d7c0f", "#9333ea", "#be123c", "#0e7490")

JALALI_MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)


def ensure_spend_categories(db: Session, user: User | None = None) -> None:
    """Categories are global: the default tree is added once, only when there are no categories at all."""
    if db.query(SpendCategory.id).first() is not None:
        return
    for parent_index, (parent_slug, parent_name, children) in enumerate(DAILY_SPEND_TREE):
        parent = SpendCategory(parent_id=None, name=parent_name, slug=parent_slug, is_seed=True, sort_order=parent_index)
        db.add(parent)
        db.flush()
        for child_index, (child_slug, child_name) in enumerate(children):
            db.add(
                SpendCategory(
                    parent_id=parent.id, name=child_name, slug=child_slug, is_seed=True, sort_order=child_index
                )
            )
    db.commit()


def shift_jalali_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def jalali_month_bounds(year: int, month: int) -> tuple[date, date]:
    import jdatetime

    start = jdatetime.date(year, month, 1).togregorian()
    next_year, next_month = shift_jalali_month(year, month, 1)
    end = jdatetime.date(next_year, next_month, 1).togregorian()
    return start, end


def _color_for(parent: SpendCategory, index: int) -> str:
    if parent.color:
        return parent.color
    if parent.slug and parent.slug in PARENT_COLORS:
        return PARENT_COLORS[parent.slug]
    return _EXTRA_COLORS[index % len(_EXTRA_COLORS)]


def categories_for_user(db: Session, user: User | None = None) -> tuple[list[SpendCategory], list[SpendCategory]]:
    """Every global category, archived ones included, so old spends keep their names."""
    rows = (
        db.query(SpendCategory)
        .order_by(SpendCategory.sort_order.asc(), SpendCategory.id.asc())
        .all()
    )
    parents = [row for row in rows if row.parent_id is None]
    children = [row for row in rows if row.parent_id is not None]
    return parents, children


def picker_categories(
    parents: list[SpendCategory], children: list[SpendCategory], keep_id: int | None = None
) -> tuple[list[SpendCategory], list[SpendCategory]]:
    """Pickers hide archived categories; keep_id (the spend being edited) stays selectable with its parent."""
    keep_parent = next((c.parent_id for c in children if c.id == keep_id), None)
    active_parents = {p.id for p in parents if not p.archived}
    shown_children = [c for c in children if c.id == keep_id or (not c.archived and c.parent_id in active_parents)]
    shown_parents = [p for p in parents if p.id in active_parents or p.id == keep_parent]
    return shown_parents, shown_children


def month_chart(db: Session, user: User, year: int, month: int) -> tuple[list[dict], Decimal]:
    start, end = jalali_month_bounds(year, month)
    spends = (
        db.query(DailySpend)
        .filter(DailySpend.user_id == user.id, DailySpend.spent_on >= start, DailySpend.spent_on < end)
        .all()
    )
    parents, children = categories_for_user(db, user)
    child_parent = {child.id: child.parent_id for child in children}
    parent_by_id = {parent.id: parent for parent in parents}
    totals: dict[int, Decimal] = {parent.id: Decimal("0") for parent in parents}
    for spend in spends:
        parent_id = child_parent.get(spend.category_id, spend.category_id)
        if parent_id in totals:
            totals[parent_id] += Decimal(spend.amount_toman)
    slices = []
    month_total = Decimal("0")
    for index, parent in enumerate(parents):
        amount = totals.get(parent.id, Decimal("0"))
        if amount <= 0:
            continue
        month_total += amount
        slices.append(
            {
                "label": parent.name,
                "amount": float(amount),
                "color": _color_for(parent, index),
                "parent_id": parent.id,
            }
        )
    return slices, month_total
