"""Seed the FAKE demo account for the landing screenshots (spec /workspace/mockups/landing-shots/spec.md §3).

Never run against a real database: scripts/landing_shots.py calls this with DATA_DIR/DATABASE_URL pointing
at a fresh temporary SQLite file and checks that before and after. Every number here is made up.
Usage (normally via landing_shots.py): DATA_DIR=$tmp DATABASE_URL=sqlite:///$tmp/demo.db DEMO_PASSWORD=... \
    python scripts/seed_demo.py
"""
from __future__ import annotations

import json
import os
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

DEMO_USERNAME = "demo_nemoone"
# 2026-10-20 12:00 Tehran = 08:30Z: the fixed clock for every regeneration.
FROZEN_NOW = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)

PRICES = {  # تومان
    "gold": 7_400_000,
    "coin_emami": 82_000_000,
    "coin_quarter": 26_000_000,
    "btc": 6_900_000_000,
    "usd": 98_000,
    # not held by the demo user; priced so the page shows no «قیمت در دسترس نیست» warning
    "coin_bahar": 80_000_000,
    "coin_half": 44_000_000,
    "coin_gram": 13_000_000,
    "silver": 95_000,
    "ada": 70_000,
    "eth": 260_000_000,
    "sol": 15_000_000,
    "doge": 19_000,
    "matic": 40_000,
}
HOLDINGS = {  # User.set_holding keys -> quantity
    "gold_grams": "12",
    "coin_emami": "2",
    "coin_quarter": "3",
    "btc": "0.015",
    "usd": "800",
    "cash_toman": "45000000",
}
EXPECTED_TOTAL = 557_700_000
EXPECTED_DEBT = 4_800_000 * 11  # monthly × months left (app/debts.py debt_rows)
EXPECTED_NET = EXPECTED_TOTAL - EXPECTED_DEBT  # 504,900,000

# (days ago, parent slug, child slug, note, amount, from SMS)
SPENDS = (
    (0, "food", "groceries", "نان و پنیر", 185_000, False),
    (0, "transport", "taxi", "تاکسی", 120_000, False),
    (0, "sms", "sms_bank", "برداشت از کارت **** خرید فروشگاه نمونه", 350_000, True),
    (1, "food", "cafe", "قهوه", 95_000, False),
    (2, "shopping", "home_goods", "سوپرمارکت", 1_240_000, False),
    (3, "bills", "other_bill", "قبض برق", 310_000, False),
    (4, "food", "restaurant", "رستوران", 860_000, False),
    (6, "sms", "sms_bank", "شارژ موبایل", 200_000, True),
)


def assert_temp_db() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    data_dir = Path(os.environ.get("DATA_DIR", "")).resolve()
    if any(os.environ.get(k) for k in ("PROD", "DOKPLOY", "DOKPLOY_APP_NAME")):
        sys.exit("refusing: PROD/DOKPLOY environment")
    if not url.startswith("sqlite:///"):
        sys.exit("refusing: DATABASE_URL must be a temporary sqlite file")
    db_path = Path(url[len("sqlite:///"):]).resolve()
    if not str(data_dir).startswith(("/tmp", os.environ.get("TMPDIR", "/tmp"))) or data_dir not in db_path.parents:
        sys.exit(f"refusing: database {db_path} is not inside the temporary DATA_DIR {data_dir}")
    if db_path.exists() and db_path.stat().st_size:
        sys.exit("refusing: the demo database must start empty")
    return db_path


def _curve(hours_ago: int, rng: random.Random) -> float:
    """Total portfolio value (تومان) hours_ago: 470M a year ago -> 557.7M now; +1.2% over 7 days, +0.4% over 24h."""
    total = EXPECTED_TOTAL
    t7, t1 = total / 1.012, total / 1.004
    if hours_ago <= 24:
        return t1 + (total - t1) * (1 - hours_ago / 24)
    if hours_ago <= 168:
        return t7 + (t1 - t7) * (1 - (hours_ago - 24) / 144)
    span = 365 * 24 - 168
    base = 470_000_000 + (t7 - 470_000_000) * (1 - (hours_ago - 168) / span)
    # steady rise for the landing hero: a slow, small wave plus very little noise (no zigzag in the month view)
    return base * (1 + 0.003 * math.sin(hours_ago / 170) + rng.uniform(-0.0012, 0.0012))


def seed() -> None:
    assert_temp_db()
    password = os.environ.get("DEMO_PASSWORD")
    if not password or len(password) < 8:
        sys.exit("set DEMO_PASSWORD (≥8 chars, never committed)")
    from app.db import SessionLocal, init_db
    from app.daily_spend import ensure_spend_categories
    from app.models import DailySpend, Debt, MarketPrice, MonthlyExpense, PortfolioSnapshot, SpendCategory, User
    from app.portfolio import build_portfolio, load_prices
    from app.security import hash_password

    init_db()
    db = SessionLocal()
    rng = random.Random(1405)
    user = User(username=DEMO_USERNAME, password_hash=hash_password(password), created_at=FROZEN_NOW - timedelta(days=366))
    db.add(user)
    db.commit()
    for key, qty in HOLDINGS.items():
        user.set_holding(key, qty)
    for symbol, price in PRICES.items():
        db.merge(MarketPrice(symbol=symbol, price_toman=Decimal(price), fetched_at=FROZEN_NOW - timedelta(minutes=12)))
    db.commit()
    view = build_portfolio(user, load_prices(db))
    if int(view.total_toman) != EXPECTED_TOTAL:
        sys.exit(f"demo total {view.total_toman} != {EXPECTED_TOTAL}")
    fixed = sum(int(r.value_toman) for r in view.rows if r.unit_price is None)
    moving = int(view.total_toman) - fixed
    rows = []
    for h in range(365 * 24, 0, -1):
        f = (_curve(h, rng) - fixed) / moving
        bd, up, tot = {}, {}, 0
        for r in view.rows:
            if r.unit_price is None:
                v = int(r.value_toman)
            else:
                v = int(r.value_toman * Decimal(str(f)))
                up[r.key] = str((r.unit_price * Decimal(str(f))).quantize(Decimal("1")))
            bd[r.key] = str(v)
            tot += v
        bd["total"] = str(tot)
        bd["unit_price"] = up
        rows.append({"user_id": user.id, "taken_at": FROZEN_NOW - timedelta(hours=h),
                     "total_toman": Decimal(tot), "breakdown_json": json.dumps(bd)})
    db.bulk_insert_mappings(PortfolioSnapshot, rows)
    db.add(Debt(user_id=user.id, title="قسط خودرو", monthly_toman=Decimal(4_800_000), months_left=11,
                due_year=1405, due_month=8, due_day=20))
    db.add(MonthlyExpense(user_id=user.id, title="اجاره", amount_toman=Decimal(12_000_000), due_day=1))
    db.commit()
    ensure_spend_categories(db, user)
    by_slug = {c.slug: c for c in db.query(SpendCategory).filter(SpendCategory.user_id == user.id)}
    today = FROZEN_NOW.astimezone(timezone(timedelta(hours=3, minutes=30))).date()
    for days, _parent, child, note, amount, from_sms in SPENDS:
        cat = by_slug[child]
        if from_sms:  # exactly what /api/sms-spend stores: the app's idempotency key in front of the note
            note = f"[{rng.getrandbits(256):064x}] {note}"
        db.add(DailySpend(user_id=user.id, category_id=cat.id, amount_toman=Decimal(amount),
                          spent_on=today - timedelta(days=days), note=note,
                          created_at=FROZEN_NOW - timedelta(days=days, hours=1)))
    db.commit()
    names = [u.username for u in db.query(User).all()]
    if names != [DEMO_USERNAME]:
        sys.exit(f"refusing: unexpected users in the demo DB: {names}")
    db.close()
    print(json.dumps({"user": DEMO_USERNAME, "snapshots": len(rows), "total": EXPECTED_TOTAL, "net": EXPECTED_NET}))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    seed()
