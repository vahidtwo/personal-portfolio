"""Phase 1: dedicated Assets page (/assets).

Read-only view over the same data the old profile «دارایی‌ها» tab edited. The form still posts to the
existing POST /profile handler (app.profile.profile_save), so parsing (app.number_input) and saving are
unchanged. No schema changes.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_toman, format_when
from app.portfolio import ASSET_META, build_portfolio, load_prices
from app.security import get_authenticated_user, redirect_to_login
from app.web import pop_flash, render

router = APIRouter()

# Groups shown as cards, in display order. Keys are app.portfolio asset keys; every quantity field of
# the old profile assets form appears exactly once (tests/test_assets_page.py checks this).
ASSET_GROUPS = (
    ("gold", "طلا و سکه", ("gold", "coin_emami", "coin_bahar", "coin_half", "coin_quarter", "coin_gram", "silver")),
    ("fx", "ارز و نقد", ("usd", "cash")),
    ("crypto", "رمزارز", ("btc", "ada", "eth", "sol", "doge", "matic")),
)
# Unit shown inside the quantity box (the dashboard keeps ASSET_META units).
_UNIT_OVERRIDE = {"usd": "دلار"}
_LATIN_UNIT = frozenset({"btc", "ada", "eth", "sol", "doge", "matic"})


def _plain(value: Decimal | None) -> str:
    """Plain Latin decimal text for data-* attributes (JS live values only)."""
    if value is None:
        return ""
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def assets_context(user, db: Session, form: dict[str, str]) -> dict:
    view = build_portfolio(user, load_prices(db))
    by_key = {row.key: row for row in view.rows}
    groups = []
    for gkey, title, keys in ASSET_GROUPS:
        rows = []
        subtotal = Decimal("0")
        for key in keys:
            meta = ASSET_META[key]
            field = meta["qty_attr"]
            row = by_key[key]
            value_text = form.get(field, "") or ""
            manual = key == "cash"
            price = Decimal("1") if manual else row.unit_price
            subtotal += row.value_toman
            rows.append(
                {
                    "key": key,
                    "field": field,
                    "name": meta["name_fa"],
                    "symbol": meta["unit_en"] if key in _LATIN_UNIT else "",
                    "unit": _UNIT_OVERRIDE.get(key, meta["unit_fa"]),
                    "unit_latin": key in _LATIN_UNIT,
                    "value": value_text,
                    "held": value_text.strip() != "",
                    "manual": manual,
                    "thousands": manual,
                    "price_plain": _plain(price),
                    "value_plain": _plain(row.value_toman),
                    "value_label": format_toman(row.value_toman) if price is not None else None,
                }
            )
        groups.append(
            {
                "key": gkey,
                "title": title,
                "rows": rows,
                "subtotal_plain": _plain(subtotal),
                "subtotal_label": format_toman(subtotal),
            }
        )
    car = by_key["car"]
    return {
        "asset_groups": groups,
        "assets_total_plain": _plain(view.total_toman),
        "assets_total_label": format_toman(view.total_toman),
        "car_value_plain": _plain(car.value_toman),
        "car_group_label": format_toman(car.value_toman) if car.value_toman > 0 else None,
        "missing_prices": bool(view.missing_prices),
        # unchanged Sanjeh (car) fields, exactly as the old profile assets tab showed them
        "has_sanjeh_token": bool(user.sanjeh_token),
        "car_fetched_label": format_when(user.car_fetched_at),
        "car_value_label": format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
    }


def render_assets(request: Request, db: Session, user, *, form: dict[str, str] | None = None, error: str | None = None,
                  flash_message: str | None = None, flash_error: bool = False):
    from app.profile import holdings_form

    if form is None:
        form = holdings_form(user)
    return render(
        request,
        "assets.html",
        db,
        error=error,
        flash=flash_message,
        flash_error=flash_error,
        form=form,
        **assets_context(user, db, form),
    )


@router.get("/assets", response_class=HTMLResponse)
async def assets_page(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
    flash_message, flash_error = pop_flash(request)
    return render_assets(request, db, user, flash_message=flash_message, flash_error=flash_error)
