"""Arzban public API (fm5.ir) — backup market prices when chande.net is unavailable."""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx

from app.config import ARZBAN_PRICES_URL
from app.chande import CHANDE_SYMBOLS, FetchedPrice, normalize_price_toman
from app.db import SessionLocal
from app.models import utcnow
from app.portfolio import load_prices

logger = logging.getLogger(__name__)

# Internal portfolio key → fm5.ir symbol on GET /api/v1/prices (quote TMN unless noted).
_ARZBAN_TMN = {
    "gold": "GOLD18",
    "coin_emami": "SEKE_EMAMI",
    "coin_bahar": "SEKE_BAHAR",
    "coin_half": "SEKE_NIM",
    "coin_quarter": "SEKE_ROB",
    "coin_gram": "SEKE_GERAMI",
    "usd": "USD",
    "btc": "BTC_TMN",
    "eth": "ETH_TMN",
}
# USD quote on fm5; converted to toman with the USD row.
_ARZBAN_USD = {
    "sol": "SOL",
    "ada": "ADA",
    "doge": "DOGE",
}
_SILVER_OUNCE_USD = "XAG"


def _toman_price(row: dict) -> Decimal | None:
    raw = row.get("price")
    if raw is None:
        return None
    quote = str(row.get("quote") or "TMN").upper()
    if quote != "TMN":
        return None
    return Decimal(str(raw))


def _usd_price(row: dict) -> Decimal | None:
    raw = row.get("price")
    if raw is None:
        return None
    if str(row.get("quote") or "").upper() != "USD":
        return None
    return Decimal(str(raw))


async def fetch_arzban_prices() -> list[FetchedPrice]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "my-inventory/1.0 (+https://fm5.ir/)",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(ARZBAN_PRICES_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Unexpected fm5.ir payload")

    by_symbol = {str(row.get("symbol")): row for row in items if isinstance(row, dict) and row.get("symbol")}
    usd_row = by_symbol.get("USD")
    usd_toman = _toman_price(usd_row) if usd_row else None
    if usd_toman is None or usd_toman <= 0:
        raise ValueError("fm5.ir USD price missing")

    fetched_at = utcnow()
    result: list[FetchedPrice] = []
    missing: list[str] = []

    for key, chande_symbol in CHANDE_SYMBOLS.items():
        price: Decimal | None = None
        source_updated_at: str | None = None

        if key in _ARZBAN_TMN:
            row = by_symbol.get(_ARZBAN_TMN[key])
            if row:
                price = _toman_price(row)
                source_updated_at = str(row.get("updated_at") or "") or None
        elif key in _ARZBAN_USD:
            row = by_symbol.get(_ARZBAN_USD[key])
            if row:
                usd = _usd_price(row)
                if usd is not None:
                    price = (usd * usd_toman).quantize(Decimal("1"))
                    source_updated_at = str(row.get("updated_at") or "") or None
        elif key == "silver":
            row = by_symbol.get(_SILVER_OUNCE_USD)
            if row:
                usd = _usd_price(row)
                if usd is not None:
                    ounce_toman = (usd * usd_toman).quantize(Decimal("1"))
                    price = normalize_price_toman("silver", ounce_toman)
                    source_updated_at = str(row.get("updated_at") or "") or None
        elif key == "matic":
            pass  # not listed on fm5; filled from DB below if possible
        else:
            missing.append(chande_symbol)
            continue

        if price is None:
            missing.append(chande_symbol)
            continue
        result.append(
            FetchedPrice(
                key=key,
                symbol=chande_symbol,
                price_toman=price,
                source_updated_at=source_updated_at,
                fetched_at=fetched_at,
            )
        )

    if missing:
        db = SessionLocal()
        try:
            stored = load_prices(db)
            for chande_symbol in list(missing):
                key = next((k for k, sym in CHANDE_SYMBOLS.items() if sym == chande_symbol), None)
                if key is None:
                    continue
                row = stored.get(key)
                if row is None or row.price_toman is None:
                    continue
                result.append(
                    FetchedPrice(
                        key=key,
                        symbol=chande_symbol,
                        price_toman=Decimal(row.price_toman),
                        source_updated_at=row.source_updated_at,
                        fetched_at=fetched_at,
                    )
                )
                missing.remove(chande_symbol)
                logger.info("Arzban backup: kept stored price for %s", key)
        finally:
            db.close()

    if missing:
        raise ValueError("Missing symbols from fm5.ir backup: " + ", ".join(missing))
    return result
