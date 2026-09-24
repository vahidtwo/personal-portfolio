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
)

PARENT_COLORS = {
    "food": "#e85d04",
    "transport": "#1d4ed8",
    "gifts": "#be185d",
    "shopping": "#7c3aed",
    "health": "#059669",
    "fun": "#d97706",
    "bills": "#0f766e",
    "other": "#64748b",
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


def ensure_spend_categories(db: Session, user: User) -> None:
    existing = {
        row.slug: row
        for row in db.query(SpendCategory).filter(SpendCategory.user_id == user.id).all()
        if row.slug
    }
    changed = False
    for parent_index, (parent_slug, parent_name, children) in enumerate(DAILY_SPEND_TREE):
        parent = existing.get(parent_slug)
        if parent is None:
            parent = SpendCategory(
                user_id=user.id,
                parent_id=None,
                name=parent_name,
                slug=parent_slug,
                is_seed=True,
                sort_order=parent_index,
            )
            db.add(parent)
            db.flush()
            existing[parent_slug] = parent
            changed = True
        for child_index, (child_slug, child_name) in enumerate(children):
            if child_slug in existing:
                continue
            db.add(
                SpendCategory(
                    user_id=user.id,
                    parent_id=parent.id,
                    name=child_name,
                    slug=child_slug,
                    is_seed=True,
                    sort_order=child_index,
                )
            )
            changed = True
    if changed:
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
    if parent.slug and parent.slug in PARENT_COLORS:
        return PARENT_COLORS[parent.slug]
    return _EXTRA_COLORS[index % len(_EXTRA_COLORS)]


def categories_for_user(db: Session, user: User) -> tuple[list[SpendCategory], list[SpendCategory]]:
    rows = (
        db.query(SpendCategory)
        .filter(SpendCategory.user_id == user.id)
        .order_by(SpendCategory.sort_order.asc(), SpendCategory.id.asc())
        .all()
    )
    parents = [row for row in rows if row.parent_id is None]
    children = [row for row in rows if row.parent_id is not None]
    return parents, children


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
