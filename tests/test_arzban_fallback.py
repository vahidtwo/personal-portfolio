"""Chande → Arzban price fallback."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx


def _fm5_payload():
    return {
        "ok": True,
        "data": [
            {"symbol": "USD", "quote": "TMN", "price": 271905, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "GOLD18", "quote": "TMN", "price": 27223100, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SEKE_EMAMI", "quote": "TMN", "price": 273965000, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SEKE_BAHAR", "quote": "TMN", "price": 265040000, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SEKE_NIM", "quote": "TMN", "price": 143980000, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SEKE_ROB", "quote": "TMN", "price": 76520000, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SEKE_GERAMI", "quote": "TMN", "price": 39000000, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "XAG", "quote": "USD", "price": 53.88, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "BTC_TMN", "quote": "TMN", "price": 21743060002, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "ETH_TMN", "quote": "TMN", "price": 641588967, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "SOL", "quote": "USD", "price": 102.36, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "ADA", "quote": "USD", "price": 0.21, "updated_at": "2026-10-24 10:00:00"},
            {"symbol": "DOGE", "quote": "USD", "price": 0.07825, "updated_at": "2026-10-24 10:00:00"},
        ],
    }


def test_fetch_chande_falls_back_to_arzban_on_502(client):
    from app.chande import CHANDE_SYMBOLS, fetch_chande_prices
    from app.db import SessionLocal
    from app.models import MarketPrice, utcnow

    db = SessionLocal()
    db.merge(MarketPrice(symbol="matic", price_toman=Decimal("34340"), fetched_at=utcnow()))
    db.commit()
    db.close()

    chande_resp = httpx.Response(502, request=httpx.Request("GET", "https://chande.net/"))
    fm5_resp = httpx.Response(200, json=_fm5_payload(), request=httpx.Request("GET", "https://fm5.ir/"))

    async def fake_get(url, **kwargs):
        if "chande.net" in str(url):
            return chande_resp
        if "fm5.ir" in str(url):
            return fm5_resp
        raise AssertionError(url)

    mock_client = AsyncMock()
    mock_client.get = fake_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.chande.httpx.AsyncClient", return_value=mock_client), patch(
        "app.arzban.httpx.AsyncClient", return_value=mock_client
    ):
        prices = asyncio.run(fetch_chande_prices())

    by_key = {p.key: p for p in prices}
    assert set(by_key) == set(CHANDE_SYMBOLS)
    assert by_key["usd"].price_toman == Decimal("271905")
    assert by_key["gold"].price_toman == Decimal("27223100")
    assert by_key["sol"].price_toman == (Decimal("102.36") * Decimal("271905")).quantize(Decimal("1"))
    assert by_key["matic"].price_toman == Decimal("34340")
