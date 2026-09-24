"""Portfolio dashboard, charts, and manual price refresh."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import PRICE_MANUAL_REFRESH_MINUTES
from app.db import get_db
from app.debts import debt_rows
from app.expenses import monthly_view
from app.formatting import format_chart_jalali, format_qty, format_share_label, format_toman, format_when, persian_digits
from app.jobs import refresh_market_prices_for_user, refresh_user_sanjeh_car
from app.models import Debt, PortfolioSnapshot, User, utcnow
from app.portfolio import (
    ASSET_LABEL_FA,
    ASSET_META,
    ASSET_ORDER,
    build_portfolio,
    latest_market_prices_fetched_at,
    load_prices,
)
from app.sanjeh import SanjehAuthError
from app.security import get_current_user, require_csrf
from app.spends import daily_view
from app.web import flash, pop_flash, render

logger = logging.getLogger(__name__)
router = APIRouter()

def build_chart_data(db: Session, user_id: int, view) -> dict:
    """Labels + per-asset series; chronological left→right, last point is live portfolio."""
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user_id)
        .order_by(PortfolioSnapshot.taken_at.desc())
        .limit(720)
        .all()
    )
    snaps.reverse()
    labels = [format_chart_jalali(s.taken_at) for s in snaps] + [format_chart_jalali(utcnow())]

    current: dict[str, float] = {row.key: float(row.value_toman) for row in view.rows}
    current["total"] = float(view.total_toman)

    series: list[dict] = [
        {
            "key": "total",
            "label": "جمع کل",
            "data": [float(json.loads(s.breakdown_json).get("total", s.total_toman)) for s in snaps]
            + [current["total"]],
        }
    ]
    for key in ASSET_ORDER:
        history_vals = []
        for s in snaps:
            bd = json.loads(s.breakdown_json)
            history_vals.append(float(bd.get(key, 0)))
        series.append(
            {
                "key": key,
                "label": ASSET_LABEL_FA.get(key, key),
                "data": history_vals + [current.get(key, 0.0)],
            }
        )
    asset_options = [{"key": "total", "label": "جمع کل"}] + [
        {"key": row.key, "label": row.name_fa} for row in view.rows
    ]
    return {"labels": labels, "series": series, "assetOptions": asset_options}


def build_pie_data(view) -> dict:
    """Current portfolio share per asset (positive values only)."""
    total = view.total_toman
    slices: list[dict] = []
    for row in view.rows:
        val = row.value_toman
        if val <= 0:
            continue
        share = (val / total * Decimal("100")) if total > 0 else Decimal("0")
        share_q = share.quantize(Decimal("0.1"))
        slices.append(
            {
                "key": row.key,
                "label": row.name_fa,
                "value": float(val),
                "value_label": format_toman(val),
                "share_label": persian_digits(format(share_q, "f").rstrip("0").rstrip(".")),
            }
        )
    slices.sort(key=lambda s: s["value"], reverse=True)
    return {"slices": slices}


ASSET_SPARKLINE_COLORS = {
    "gold": "#f59e0b",
    "coin_emami": "#d97706",
    "coin_bahar": "#fbbf24",
    "coin_half": "#b45309",
    "coin_quarter": "#fcd34d",
    "coin_gram": "#92400e",
    "silver": "#cbd5e1",
    "btc": "#f97316",
    "ada": "#3b82f6",
    "eth": "#8b5cf6",
    "sol": "#14b8a6",
    "doge": "#eab308",
    "matic": "#a855f7",
    "usd": "#22c55e",
    "cash": "#38bdf8",
    "car": "#94a3b8",
}


def _snapshot_unit_price(bd: dict, key: str, quantity: Decimal) -> float | None:
    """Unit price from the snapshot, or holding value ÷ today's quantity."""
    stored = bd.get("unit_price")
    if isinstance(stored, dict) and stored.get(key) not in (None, ""):
        return float(stored[key])
    if key == "cash" or quantity <= 0:
        return None
    try:
        value = Decimal(str(bd.get(key, 0)))
    except Exception:
        return None
    return float(value / quantity)


def build_week_asset_trends(db: Session, user_id: int, view) -> dict[str, list[float]]:
    """Unit price (toman) over 7 days, plus the live unit price."""
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.taken_at >= utcnow() - timedelta(days=7),
        )
        .order_by(PortfolioSnapshot.taken_at.asc())
        .limit(720)
        .all()
    )
    qty = {row.key: row.quantity for row in view.rows}
    live = {row.key: row.unit_price for row in view.rows}
    trends: dict[str, list[float]] = {}
    for key in ASSET_ORDER:
        points: list[float] = []
        for snap in snaps:
            price = _snapshot_unit_price(json.loads(snap.breakdown_json), key, qty.get(key, Decimal("0")))
            if price is not None:
                points.append(price)
        current = live.get(key)
        if current is not None:
            points.append(float(current))
        trends[key] = points
    return trends


def sparkline_path(values: list[float], width: int = 72, height: int = 26) -> str:
    if not values:
        return ""
    series = list(values)
    if len(series) == 1:
        series = [series[0], series[0]]
    vmin = min(series)
    vmax = max(series)
    span = vmax - vmin
    if span <= 0:
        mid = height / 2
        return f"M 1,{mid:.1f} L {width - 1},{mid:.1f}"
    n = len(series)
    parts: list[str] = []
    for i, v in enumerate(series):
        x = 1 + (i / (n - 1)) * (width - 2)
        y = height - 1 - ((v - vmin) / span) * (height - 2)
        parts.append(f"{x:.1f},{y:.1f}")
    return "M " + parts[0] + " L " + " L ".join(parts[1:])


def build_week_total_values(db: Session, user_id: int, view) -> list[float]:
    """Portfolio total (toman) for the last 7 days + current."""
    window_end = utcnow()
    window_start = window_end - timedelta(days=7)
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.taken_at >= window_start,
        )
        .order_by(PortfolioSnapshot.taken_at.asc())
        .all()
    )
    values: list[float] = []
    for snap in snaps:
        bd = json.loads(snap.breakdown_json)
        values.append(float(bd.get("total", snap.total_toman)))
    values.append(float(view.total_toman))
    return values


def build_total_value_history(db: Session, user_id: int, view) -> list[float]:
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user_id)
        .order_by(PortfolioSnapshot.taken_at.asc())
        .limit(720)
        .all()
    )
    values: list[float] = []
    for snap in snaps:
        bd = json.loads(snap.breakdown_json)
        values.append(float(bd.get("total", snap.total_toman)))
    values.append(float(view.total_toman))
    return values


def format_percent_label(pct: float) -> str:
    body = abs(pct)
    text = body if body >= 100 else round(body, 1)
    s = format(text, "f").rstrip("0").rstrip(".")
    sign = "+" if pct > 0 else "−" if pct < 0 else ""
    return sign + persian_digits(s) + "٪"


def week_trend_change_label(values: list[float]) -> str | None:
    if len(values) < 2:
        return None
    first, last = values[0], values[-1]
    if first == 0 and last == 0:
        return persian_digits("0") + "٪"
    if first == 0:
        return None
    return format_percent_label(((last - first) / abs(first)) * 100)


def week_period_change_percent(values: list[float]) -> float | None:
    """Percent change from first point in series to last (start of window → now)."""
    if len(values) < 2:
        return None
    first, last = values[0], values[-1]
    if first == 0 and last == 0:
        return 0.0
    if first == 0:
        return None
    return ((last - first) / abs(first)) * 100.0


def max_gain_labels(values: list[float]) -> tuple[str, str, bool]:
    """Display label, sort key, and whether change is strictly positive."""
    pct = week_period_change_percent(values)
    if pct is None:
        return "—", "", False
    return format_percent_label(pct), str(pct), pct > 0

def market_price_refresh_wait_seconds(db: Session) -> int:
    """Seconds until manual market refresh is allowed; 0 if allowed now."""
    prices = load_prices(db)
    latest = latest_market_prices_fetched_at(prices)
    if latest is None:
        return 0
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    cooldown = timedelta(minutes=max(1, PRICE_MANUAL_REFRESH_MINUTES))
    remaining = cooldown - (utcnow() - latest)
    if remaining.total_seconds() <= 0:
        return 0
    return int(remaining.total_seconds())

CAR_REFRESH = timedelta(hours=1)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user.sanjeh_token:
        fetched = user.car_fetched_at
        if fetched is not None and fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        stale = fetched is None or utcnow() - fetched > CAR_REFRESH
        if stale:
            try:
                await refresh_user_sanjeh_car(user)
                db.commit()
                db.refresh(user)
            except SanjehAuthError:
                pass
            except Exception:
                logger.exception("Sanjeh refresh failed for user %s", user.id)
    prices = load_prices(db)
    view = build_portfolio(user, prices)
    total = view.total_toman if view.total_toman > 0 else Decimal("1")
    week_trends = build_week_asset_trends(db, user.id, view)
    rows = []
    for row in view.rows:
        places = ASSET_META[row.key]["qty_places"]
        share = (row.value_toman / total * Decimal("100")).quantize(Decimal("0.1"))
        trend_vals = week_trends.get(row.key, [float(row.value_toman)])
        trend_change = week_trend_change_label(trend_vals)
        max_gain_label, sort_max_gain, max_gain_positive = max_gain_labels(trend_vals)
        rows.append(
            {
                "key": row.key,
                "name_fa": row.name_fa,
                "sparkline_path": sparkline_path(trend_vals),
                "sparkline_color": ASSET_SPARKLINE_COLORS.get(row.key, "#9aa3b2"),
                "trend_change_label": trend_change,
                "max_gain_label": max_gain_label,
                "max_gain_positive": max_gain_positive,
                "quantity_label": format_qty(
                    row.quantity,
                    places if row.key not in ("car", "cash") else 0,
                ),
                "unit_fa": row.unit_fa,
                "unit_price_label": format_toman(row.unit_price),
                "value_label": format_toman(row.value_toman),
                "share_label": format_share_label(share),
                "manual": row.manual,
                "sanjeh": row.sanjeh,
                "sort_qty": str(row.quantity),
                "sort_unit_price": str(row.unit_price) if row.unit_price is not None else "",
                "sort_value": str(row.value_toman),
                "sort_share": str(share),
                "sort_max_gain": sort_max_gain,
            }
        )
    missing_fa = [ASSET_LABEL_FA.get(k, k) for k in view.missing_prices]
    chart_data = build_chart_data(db, user.id, view)
    chart_json = json.dumps(chart_data, ensure_ascii=False)
    chart_asset_options = [{"key": "total", "name_fa": "جمع کل"}] + [
        {"key": row.key, "name_fa": row.name_fa} for row in view.rows
    ]
    default_chart_asset_key = "total"
    pie_data = build_pie_data(view)
    pie_json = json.dumps(pie_data, ensure_ascii=False)
    flash_message, flash_error = pop_flash(request)
    refresh_wait_sec = market_price_refresh_wait_seconds(db)
    refresh_wait_label = None
    if refresh_wait_sec > 0:
        minutes = max(1, (refresh_wait_sec + 59) // 60)
        refresh_wait_label = f"حدود {persian_digits(str(minutes))} دقیقه دیگر"
    total_max_gain_label, total_max_gain_sort, total_max_gain_positive = max_gain_labels(
        build_week_total_values(db, user.id, view)
    )
    _debt_list, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).all()
    )
    monthly = monthly_view(db, user)
    tab = request.query_params.get("tab", "portfolio")
    if tab not in ("portfolio", "daily"):
        tab = "portfolio"
    return render(
        request,
        "dashboard.html",
        db,
        view=view,
        rows=rows,
        total_label=format_toman(view.total_toman),
        debt_total_label=format_toman(debt_total),
        next_debt_label=next_debt_label,
        net_label=format_toman(view.total_toman - debt_total),
        income_month_label=monthly["income_month_label"],
        installment_month_label=monthly["installment_month_label"],
        expense_month_label=monthly["expense_month_label"],
        monthly_left_label=monthly["monthly_left_label"],
        total_max_gain_label=total_max_gain_label,
        total_max_gain_positive=total_max_gain_positive,
        fetched_label=format_when(view.prices_fetched_at),
        missing_fa=missing_fa,
        chart_json=chart_json,
        chart_asset_options=chart_asset_options,
        default_chart_asset_key=default_chart_asset_key,
        pie_json=pie_json,
        pie_has_data=bool(pie_data["slices"]),
        flash=flash_message,
        flash_error=flash_error,
        refresh_wait_sec=refresh_wait_sec,
        refresh_wait_label=refresh_wait_label,
        price_refresh_minutes=persian_digits(str(PRICE_MANUAL_REFRESH_MINUTES)),
        tab=tab,
        error=None,
        **(daily_view(db, user, request) if tab == "daily" else {}),
    )


@router.post("/dashboard/refresh-prices")
async def dashboard_refresh_prices(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    wait_sec = market_price_refresh_wait_seconds(db)
    if wait_sec > 0:
        minutes = max(1, wait_sec // 60)
        flash(
            request,
            f"حداقل {persian_digits(str(PRICE_MANUAL_REFRESH_MINUTES))} دقیقه بعد از آخرین به‌روزرسانی باید بگذرد. "
            f"حدود {persian_digits(str(minutes))} دقیقه دیگر دوباره تلاش کنید.",
            error=True,
        )
        return RedirectResponse("/dashboard", status_code=303)
    try:
        await refresh_market_prices_for_user(user.id)
    except Exception:
        logger.exception("Manual price refresh failed for user %s", user.id)
        flash(request, "دریافت قیمت از چنده ممکن نشد. بعداً دوباره تلاش کنید.", error=True)
        return RedirectResponse("/dashboard", status_code=303)
    flash(request, "قیمت بازار و پرتفوی به‌روز شد")
    return RedirectResponse("/dashboard", status_code=303)
