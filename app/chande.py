from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import httpx

from app.config import CHANDE_URL
from app.models import utcnow

CHANDE_SYMBOLS = {
    "gold": "GOLD_18K",
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
        result.append(
            FetchedPrice(
                key=key,
                symbol=symbol,
                price_toman=Decimal(str(raw)),
                source_updated_at=str(row.get("updatedAt") or "") or None,
                fetched_at=fetched_at,
            )
        )
    if missing:
        raise ValueError("Missing symbols from chande.net: " + ", ".join(missing))
    return result
