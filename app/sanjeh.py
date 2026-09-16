from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

KHODRO45_PROFILE_URL = "https://khodro45.com/api/v1/portfolio/profile/"


class SanjehError(Exception):
    pass


class SanjehAuthError(SanjehError):
    pass


@dataclass(frozen=True)
class SanjehPortfolio:
    total_toman: Decimal
    car_count: int


def _rial_to_toman(rial: int | float | str) -> Decimal:
    return (Decimal(str(rial)) / Decimal("10")).quantize(Decimal("1"))


def parse_portfolio_payload(payload: dict) -> SanjehPortfolio:
    total_rial = None
    block = payload.get("latest_price_sum")
    if isinstance(block, dict) and block.get("price") is not None:
        total_rial = block["price"]
    if total_rial is None:
        total_rial = 0
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            latest = item.get("latest_price") or {}
            if isinstance(latest, dict) and latest.get("price"):
                total_rial += latest["price"]
    results = payload.get("results") or []
    count = len(results) if isinstance(results, list) else 0
    return SanjehPortfolio(total_toman=_rial_to_toman(total_rial), car_count=count)


async def fetch_sanjeh_portfolio(token: str) -> SanjehPortfolio:
    token = (token or "").strip()
    if not token:
        raise SanjehError("توکن خالی است")
    headers = {
        "Authorization": f"Token {token}",
        "accept": "*/*",
        "origin": "https://sanjeh.app",
        "referer": "https://sanjeh.app/",
        "User-Agent": "my-inventory/1.0",
    }
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        response = await client.get(KHODRO45_PROFILE_URL, headers=headers)
    if response.status_code in (401, 403):
        raise SanjehAuthError("توکن سنجه نامعتبر است")
    if response.status_code >= 400:
        raise SanjehError(f"خطا از سنجه: {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SanjehError("پاسخ سنجه نامعتبر است") from exc
    if not isinstance(payload, dict):
        raise SanjehError("پاسخ سنجه نامعتبر است")
    return parse_portfolio_payload(payload)
