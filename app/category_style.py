"""Icons (emoji) and colours a spend-category group may use; shared by the admin page and the spend list."""

from __future__ import annotations

# slug of a default group -> its emoji (also written by migration 0009 where the icon was empty)
DEFAULT_GROUP_ICONS: dict[str, str] = {
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

# (emoji, Persian name) offered in the picker; an empty icon means «حرف اول» (first letter of the name).
ICON_CHOICES: tuple[tuple[str, str], ...] = (
    ("🍽️", "غذا"),
    ("🚗", "خودرو"),
    ("🎁", "هدیه"),
    ("🛍️", "خرید"),
    ("💊", "دارو"),
    ("🎉", "تفریح"),
    ("🧾", "قبض"),
    ("📦", "بسته"),
    ("💬", "پیام"),
    ("☕", "قهوه"),
    ("🏠", "خانه"),
    ("✈️", "سفر"),
    ("📚", "کتاب"),
    ("📱", "موبایل"),
    ("🎓", "آموزش"),
    ("🐾", "حیوان خانگی"),
)
ICON_SET = frozenset(icon for icon, _ in ICON_CHOICES)

# (hex, Persian name): every one keeps a white icon or letter at >= 4.5:1.
PALETTE: tuple[tuple[str, str], ...] = (
    ("#c2410c", "نارنجی سوخته"),
    ("#b45309", "کهربایی"),
    ("#4d7c0f", "زیتونی"),
    ("#15803d", "سبز"),
    ("#047857", "زمردی"),
    ("#0f766e", "سبزآبی"),
    ("#0e7490", "فیروزه‌ای"),
    ("#0369a1", "آبی آسمانی"),
    ("#1d4ed8", "آبی"),
    ("#7c3aed", "بنفش"),
    ("#9333ea", "ارغوانی"),
    ("#be185d", "سرخابی"),
    ("#be123c", "قرمز"),
    ("#475569", "خاکستری"),
)
PALETTE_SET = frozenset(hex_ for hex_, _ in PALETTE)
MIN_WHITE_CONTRAST = 4.5


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def white_contrast(hex_color: str) -> float:
    """WCAG contrast ratio of white on this colour."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    lum = 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)
    return 1.05 / (lum + 0.05)


def group_badge(icon: str | None, name: str | None) -> str:
    """What the round badge of a spend shows: the group's emoji, else the first letter of its name."""
    icon = (icon or "").strip()
    if icon:
        return icon
    text = (name or "").strip().replace("\u200c", "")
    return text[:1]
