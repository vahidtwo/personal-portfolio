from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import httpx

from app.config import CHANDE_URL
from app.models import utcnow

# chande.net SILVER priceToman is per troy ounce; portfolio silver is held in grams.
TROY_OUNCE_GRAMS = Decimal("31.1034768")

CHANDE_SYMBOLS = {
    "gold": "GOLD_18K",
    "coin_emami": "COIN_EMAMI",
    "coin_bahar": "COIN_BAHAR",
    "coin_half": "COIN_HALF",
    "coin_quarter": "COIN_QUARTER",
    "coin_gram": "COIN_GRAM",
    "silver": "SILVER",
    "btc": "BTC",
    "ada": "ADA",
    "eth": "ETH",
    "sol": "SOL",
    "doge": "DOGE",
    "matic": "MATIC",
    "usd": "USD",
}


@dataclass(frozen=True)
class FetchedPrice:
    key: str
    symbol: str
    price_toman: Decimal
    source_updated_at: str | None
    fetched_at: datetime


def normalize_price_toman(key: str, raw: Decimal) -> Decimal:
    if key == "silver":
        return (raw / TROY_OUNCE_GRAMS).quantize(Decimal("1"))
    return raw


async def fetch_chande_prices() -> list[FetchedPrice]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "my-inventory/1.0 (+https://chande.net/)",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(CHANDE_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("prices") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("Unexpected chande.net payload")

    by_symbol = {row.get("symbol"): row for row in items if isinstance(row, dict)}
    fetched_at = utcnow()
    result: list[FetchedPrice] = []
    missing: list[str] = []
    for key, symbol in CHANDE_SYMBOLS.items():
        row = by_symbol.get(symbol)
        if not row:
            missing.append(symbol)
            continue
        raw = row.get("priceToman")
        if raw is None:
            missing.append(symbol)
            continue
        price = normalize_price_toman(key, Decimal(str(raw)))
        result.append(
            FetchedPrice(
                key=key,
                symbol=symbol,
                price_toman=price,
                source_updated_at=str(row.get("updatedAt") or "") or None,
                fetched_at=fetched_at,
            )
        )
    if missing:
        raise ValueError("Missing symbols from chande.net: " + ", ".join(missing))
    return result


def _num(value: object) -> str | None:
    if value is None or value == "":
        return None
    return format(Decimal(str(value)), "f")


async def fetch_chande_currencies() -> dict:
    """Live currency rows from Chande. price_toman is priceToman, not divided."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "my-inventory/1.0 (+https://chande.net/)",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(CHANDE_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Unexpected chande.net payload")

    rows = []
    for row in items:
        if not isinstance(row, dict) or row.get("category") != "currency":
            continue
        raw = row.get("priceToman")
        if raw is None:
            continue
        rows.append(
            {
                "symbol": row.get("symbol"),
                "name_en": row.get("nameEn"),
                "name_fa": row.get("nameFa"),
                "price_toman": _num(raw),
                "price_usd": _num(row.get("priceUsd")),
                "price_buy": _num(row.get("priceBuy")),
                "price_sell": _num(row.get("priceSell")),
                "bubble": _num(row.get("bubble")),
                "bubble_toman": _num(row.get("bubbleToman")),
                "change_24h": _num(row.get("change24h")),
                "change_direction": row.get("changeDirection"),
                "updated_at": row.get("updatedAt"),
                "source": row.get("source"),
            }
        )
    rows.sort(key=lambda item: (item.get("symbol") or ""))
    updated_at = payload.get("updated_at") if isinstance(payload, dict) else None
    return {"updated_at": updated_at, "count": len(rows), "currencies": rows}
