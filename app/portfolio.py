from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import MarketPrice, PortfolioSnapshot, User, utcnow

ASSET_ORDER = ("gold", "btc", "ada", "eth", "sol", "doge", "matic", "usd", "car")

ASSET_LABEL_FA = {
    "gold": "طلا ۱۸ عیار",
    "btc": "بیت‌کوین",
    "ada": "کاردانو",
    "eth": "اتریوم",
    "sol": "سولانا",
    "doge": "دوج‌کوین",
    "matic": "پالیگان",
    "usd": "دلار",
    "car": "خودرو",
}

ASSET_META = {
    "gold": {
        "name_fa": "طلا ۱۸ عیار",
        "name_en": "18k Gold",
        "unit_fa": "گرم",
        "unit_en": "g",
        "qty_attr": "gold_grams",
        "qty_places": 4,
    },
    "btc": {
        "name_fa": "بیت‌کوین",
        "name_en": "Bitcoin",
        "unit_fa": "BTC",
        "unit_en": "BTC",
        "qty_attr": "btc",
        "qty_places": 8,
    },
    "ada": {
        "name_fa": "کاردانو",
        "name_en": "Cardano",
        "unit_fa": "ADA",
        "unit_en": "ADA",
        "qty_attr": "ada",
        "qty_places": 4,
    },
    "eth": {
        "name_fa": "اتریوم",
        "name_en": "Ethereum",
        "unit_fa": "ETH",
        "unit_en": "ETH",
        "qty_attr": "eth",
        "qty_places": 8,
    },
    "sol": {
        "name_fa": "سولانا",
        "name_en": "Solana",
        "unit_fa": "SOL",
        "unit_en": "SOL",
        "qty_attr": "sol",
        "qty_places": 4,
    },
    "doge": {
        "name_fa": "دوج‌کوین",
        "name_en": "Dogecoin",
        "unit_fa": "DOGE",
        "unit_en": "DOGE",
        "qty_attr": "doge",
        "qty_places": 4,
    },
    "matic": {
        "name_fa": "پالیگان",
        "name_en": "Polygon",
        "unit_fa": "MATIC",
        "unit_en": "MATIC",
        "qty_attr": "matic",
        "qty_places": 4,
    },
    "usd": {
        "name_fa": "دلار آمریکا",
        "name_en": "US Dollar",
        "unit_fa": "USD",
        "unit_en": "USD",
        "qty_attr": "usd",
        "qty_places": 2,
    },
    "car": {
        "name_fa": "خودرو",
        "name_en": "Car",
        "unit_fa": "دستگاه",
        "unit_en": "unit",
        "qty_attr": "car_toman",
        "qty_places": 0,
    },
}


@dataclass
class AssetRow:
    key: str
    name_fa: str
    name_en: str
    quantity: Decimal
    unit_fa: str
    unit_en: str
    unit_price: Decimal | None
    value_toman: Decimal
    manual: bool


@dataclass
class PortfolioView:
    rows: list[AssetRow]
    total_toman: Decimal
    prices_fetched_at: datetime | None
    missing_prices: list[str]


def load_prices(db: Session) -> dict[str, MarketPrice]:
    return {row.symbol: row for row in db.query(MarketPrice).all()}


def _qty(user: User, key: str) -> Decimal:
    attr = ASSET_META[key]["qty_attr"]
    return Decimal(getattr(user, attr) or 0)


def build_portfolio(user: User, prices: dict[str, MarketPrice]) -> PortfolioView:
    rows: list[AssetRow] = []
    missing: list[str] = []
    total = Decimal("0")
    fetched_at = None
    for key in ASSET_ORDER:
        meta = ASSET_META[key]
        if key == "car":
            amount = Decimal(user.car_toman or 0).quantize(Decimal("1"))
            quantity = Decimal("1") if amount > 0 else Decimal("0")
            value = amount
            rows.append(
                AssetRow(
                    key=key,
                    name_fa=meta["name_fa"],
                    name_en=meta["name_en"],
                    quantity=quantity,
                    unit_fa=meta["unit_fa"],
                    unit_en=meta["unit_en"],
                    unit_price=amount if amount > 0 else None,
                    value_toman=value,
                    manual=True,
                )
            )
            total += value
            continue

        market = prices.get(key)
        quantity = _qty(user, key)
        unit_price = Decimal(market.price_toman) if market else None
        if market and (fetched_at is None or market.fetched_at > fetched_at):
            fetched_at = market.fetched_at
        if unit_price is None:
            missing.append(key)
            value = Decimal("0")
        else:
            value = (quantity * unit_price).quantize(Decimal("1"))
        rows.append(
            AssetRow(
                key=key,
                name_fa=meta["name_fa"],
                name_en=meta["name_en"],
                quantity=quantity,
                unit_fa=meta["unit_fa"],
                unit_en=meta["unit_en"],
                unit_price=unit_price,
                value_toman=value,
                manual=False,
            )
        )
        total += value

    return PortfolioView(
        rows=rows,
        total_toman=total.quantize(Decimal("1")),
        prices_fetched_at=fetched_at,
        missing_prices=missing,
    )


def snapshot_user(db: Session, user: User, prices: dict[str, MarketPrice], taken_at: datetime) -> None:
    view = build_portfolio(user, prices)
    breakdown = {
        row.key: str(row.value_toman) for row in view.rows
    }
    breakdown["total"] = str(view.total_toman)
    db.add(
        PortfolioSnapshot(
            user_id=user.id,
            taken_at=taken_at,
            total_toman=view.total_toman,
            breakdown_json=json.dumps(breakdown, ensure_ascii=False),
        )
    )


def snapshot_all_users(db: Session, prices: dict[str, MarketPrice]) -> int:
    taken_at = utcnow()
    users = db.query(User).all()
    for user in users:
        snapshot_user(db, user, prices, taken_at)
    return len(users)
