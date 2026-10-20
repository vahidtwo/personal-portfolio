"""Portfolio dashboard, charts, and manual price refresh."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import PRICE_MANUAL_REFRESH_MINUTES
from app.db import get_db
from app.debts import debt_rows
from app.expenses import monthly_view
from app.daily_spend import JALALI_MONTHS, month_chart
from app.formatting import (
    MILLION, MONEY_DECIMALS, TEHRAN, format_chart_jalali, format_millions, format_number, format_qty,
    format_share_label, format_toman, format_usd, format_when, next_jalali_due, persian_digits, tehran_today,
)
from app.jobs import refresh_market_prices_for_user, refresh_user_sanjeh_car
from app.models import DailySpend, Debt, PortfolioSnapshot, User, utcnow
from app.portfolio import (
    ASSET_LABEL_FA,
    ASSET_META,
    ASSET_ORDER,
    build_portfolio,
    latest_market_prices_fetched_at,
    load_prices,
)
from app.sanjeh import SanjehAuthError
from app.security import get_authenticated_user, redirect_to_login, require_csrf
from app.spends import daily_view
from app.web import flash, pop_flash, render

logger = logging.getLogger(__name__)
router = APIRouter()


def _format_usd(value: Decimal) -> str:
    return format_usd(value, fixed=True)


# Chart points: last snapshot per Tehran day for the week/month/3-month ranges (sent for the last
# 92 days only), last snapshot per week for year/all. Stored values are never changed.
CHART_DAILY_SPAN = timedelta(days=92)


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; they are stored as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def chart_snapshots(snaps: list, now: datetime, granularity: str = "day", since: timedelta | None = None) -> list:
    """Chart points, oldest first: the last snapshot per Tehran day (``"day"``) or per ISO week
    of the Tehran date (``"week"``). No hourly points (Arabi, batch 1).

    The bucket that contains ``now`` is dropped, because the live portfolio value is appended as the
    final point for that bucket. ``since`` limits how far back to go. Every kept point is a real
    snapshot with its stored values. Works on anything with ``taken_at``.
    """
    def key(at_utc: datetime):
        d = at_utc.astimezone(TEHRAN).date()
        return d if granularity == "day" else d.isocalendar()[:2]

    now_key = key(_as_utc(now))
    cutoff = now - since if since is not None else None
    buckets: dict = {}
    for snap in snaps:
        at = _as_utc(snap.taken_at)
        if cutoff is not None and at < cutoff:
            continue
        k = key(at)
        if k == now_key:
            continue
        buckets[k] = snap  # ascending input: last one in the bucket wins
    return sorted(buckets.values(), key=lambda s: _as_utc(s.taken_at))


def _chart_number(value) -> int | float:
    """Stored toman value as JSON number; integers without a trailing «.0» (same value)."""
    d = Decimal(str(value))
    return int(d) if d == d.to_integral_value() else float(d)


def _chart_points(db: Session, picked: list, view, now: datetime) -> dict:
    """Labels, times and per-asset series for the picked snapshots plus the live value at ``now``."""
    ids = [row.id for row in picked]
    loaded: dict[int, PortfolioSnapshot] = {}
    for i in range(0, len(ids), 500):
        for snap in db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id.in_(ids[i:i + 500])):
            loaded[snap.id] = snap
    snaps = [loaded[i] for i in ids if i in loaded]
    stamps = [_as_utc(s.taken_at) for s in snaps] + [now]
    labels = [format_chart_jalali(at) for at in stamps]
    times = [int(at.timestamp() * 1000) for at in stamps]
    breakdowns = [json.loads(s.breakdown_json) for s in snaps]

    current: dict[str, Decimal] = {row.key: row.value_toman for row in view.rows}
    current["total"] = view.total_toman

    series: list[dict] = [
        {
            "key": "total",
            "label": "جمع کل",
            "data": [_chart_number(bd.get("total", s.total_toman)) for s, bd in zip(snaps, breakdowns)]
            + [_chart_number(current["total"])],
        }
    ]
    # Only assets the picker can show (the current rows); others were never sent to the UI.
    shown = {row.key for row in view.rows}
    for key in ASSET_ORDER:
        if key not in shown:
            continue
        series.append(
            {
                "key": key,
                "label": ASSET_LABEL_FA.get(key, key),
                "data": [_chart_number(bd.get(key, 0)) for bd in breakdowns] + [_chart_number(current.get(key, 0))],
            }
        )
    return {"labels": labels, "times": times, "series": series}


def build_chart_data(db: Session, user_id: int, view, now: datetime | None = None) -> dict:
    """Labels + per-asset series; chronological left→right, last point is live portfolio."""
    now = _as_utc(now or utcnow())
    # Pick the points from (id, taken_at) only, then load the breakdowns of the kept ones.
    index = (
        db.query(PortfolioSnapshot.id, PortfolioSnapshot.taken_at)
        .filter(PortfolioSnapshot.user_id == user_id)
        .order_by(PortfolioSnapshot.taken_at.asc(), PortfolioSnapshot.id.asc())
        .all()
    )
    daily = _chart_points(db, chart_snapshots(index, now, "day", since=CHART_DAILY_SPAN), view, now)
    weekly = _chart_points(db, chart_snapshots(index, now, "week"), view, now)
    asset_options = [{"key": "total", "label": "جمع کل"}] + [
        {"key": row.key, "label": row.name_fa} for row in view.rows
    ]
    return {
        **daily,
        "now": daily["times"][-1],
        "weekly": weekly,
        "assetOptions": asset_options,
    }


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
                "share_label": format_number(share_q, 1),
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


def format_percent_label(pct: float) -> str:
    sign = "+" if pct > 0 else "−" if pct < 0 else ""
    return sign + format_number(abs(pct), MONEY_DECIMALS) + "٪"


# --- Net-worth change from price moves only (Phase 2) -------------------------------------
# Today's holdings are valued at the unit prices stored in an older snapshot. Quantities,
# added/removed assets and debts are the same on both sides, so only prices move the number.
# Windows are Tehran wall-clock (24h / 7 days before now in Asia/Tehran). The reference is the
# newest snapshot at or before that moment, but not older than the tolerance; no such
# snapshot (or one without stored unit prices) means «—».
CHANGE_WINDOWS: tuple[tuple[str, timedelta, timedelta, str], ...] = (
    ("24h", timedelta(hours=24), timedelta(hours=3), "۲۴ ساعت"),
    ("7d", timedelta(days=7), timedelta(hours=12), "۷ روز"),
)
CHANGE_LOOKBACK = timedelta(days=7, hours=12)
NO_PRICE_MOVE_KEYS = frozenset({"cash"})  # manual toman: its price never moves


def change_reference_time(now: datetime, window: timedelta) -> datetime:
    """`window` before `now` on the Tehran wall clock, as an aware UTC datetime."""
    local = _as_utc(now).astimezone(TEHRAN)
    return (local - window).astimezone(timezone.utc)


def reference_snapshot(snaps, now: datetime, window: timedelta, tolerance: timedelta):
    target = change_reference_time(now, window)
    best = None
    best_at = None
    for snap in snaps:
        at = _as_utc(snap.taken_at)
        if target - tolerance <= at <= target and (best_at is None or at >= best_at):
            best, best_at = snap, at
    return best


def snapshot_unit_prices(snap) -> dict[str, Decimal] | None:
    """Unit prices stored with a snapshot, or None when it has none (older snapshot format)."""
    if snap is None:
        return None
    try:
        stored = json.loads(snap.breakdown_json or "{}").get("unit_price")
    except (ValueError, AttributeError):
        return None
    if not isinstance(stored, dict) or not stored:
        return None
    prices: dict[str, Decimal] = {}
    for key, raw in stored.items():
        if raw in (None, ""):
            continue
        try:
            prices[key] = Decimal(str(raw))
        except Exception:
            continue
    return prices or None


def value_at_prices(view, then_prices: dict[str, Decimal]) -> Decimal:
    """Today's holdings valued at older unit prices (assets with no older price: unchanged)."""
    total = Decimal("0")
    for row in view.rows:
        then = then_prices.get(row.key)
        if row.key in NO_PRICE_MOVE_KEYS or row.unit_price is None or then is None:
            total += row.value_toman
            continue
        total += (row.value_toman - row.quantity * (row.unit_price - then)).quantize(Decimal("1"))
    return total


def _chip(pct: Decimal | None, flat_label: str = "۰٪") -> dict:
    if pct is None:
        return {"kind": "none", "label": "—"}
    rounded = pct.quantize(Decimal("0.01"))
    if rounded > 0:
        return {"kind": "up", "label": "▲ " + format_number(rounded, MONEY_DECIMALS) + "٪"}
    if rounded < 0:
        return {"kind": "down", "label": "▼ " + format_number(-rounded, MONEY_DECIMALS) + "٪"}
    return {"kind": "flat", "label": flat_label}


def net_worth_changes(snaps, view, debt_total: Decimal, now: datetime) -> dict:
    """24h / 7d change chips for the hero. snaps: this user's snapshots (any order)."""
    out: dict = {"windows": [], "has_history": False}
    for key, window, tolerance, period in CHANGE_WINDOWS:
        then_prices = snapshot_unit_prices(reference_snapshot(snaps, now, window, tolerance))
        item = {"key": key, "period": period, "delta": None, "pct": None}
        if then_prices is not None:
            out["has_history"] = True
            past_assets = value_at_prices(view, then_prices)
            delta = view.total_toman - past_assets
            past_net = past_assets - debt_total
            item["delta"] = delta
            item["pct"] = (delta / abs(past_net) * Decimal("100")) if past_net != 0 else None
        item.update(_chip(item["pct"]))
        if item["delta"] is not None and item["pct"] is None:
            item.update(_chip(Decimal("0") if item["delta"] == 0 else None))
        out["windows"].append(item)
        out[key] = item
    day = out["24h"]
    if day["delta"] is not None:
        amount = format_toman(abs(day["delta"]))
        if day["delta"] > 0:
            out["note"] = (amount, "تومان بیشتر از دیروز")
        elif day["delta"] < 0:
            out["note"] = (amount, "تومان کمتر از دیروز")
        else:
            out["note"] = (None, "بدون تغییر نسبت به دیروز")
    elif out["has_history"]:
        out["note"] = (None, "برای ۲۴ ساعت پیش قیمتی ثبت نشده")
    else:
        out["note"] = None
    return out


def asset_week_change(row, then_prices: dict[str, Decimal] | None) -> tuple[dict, str]:
    """Unit-price change of one asset vs the 7-day reference snapshot: chip + sort key."""
    if row.key in NO_PRICE_MOVE_KEYS:
        return {"kind": "flat", "label": "بدون تغییر"}, "0"
    then = (then_prices or {}).get(row.key)
    if row.unit_price is None or then is None or then == 0:
        return {"kind": "none", "label": "—"}, ""
    pct = (Decimal(row.unit_price) - then) / then * Decimal("100")
    return _chip(pct, "بدون تغییر"), str(pct)


def big_toman(value: Decimal) -> dict:
    """Big amounts in «میلیون تومان» (≈ when rounded); under a million stays in تومان."""
    value = Decimal(value)
    if abs(value) < MILLION:
        return {"label": format_toman(value), "unit": "تومان", "approx": False}
    decimals = 0 if abs(value) >= MILLION * 1000 else 1
    label, approx = format_millions(value, decimals)
    return {"label": label, "unit": "میلیون تومان", "approx": approx}


def next_instalment(debts: list[Debt], today: jdatetime.date) -> dict | None:
    """Soonest instalment over all ACTIVE debts (same due-date rule as the debts page; 0-left debts are out)."""
    from app.debt_schedule import soonest

    nearest = soonest(debts, today)
    if nearest is None:
        return None
    return {k: nearest[k] for k in ("amount_label", "title", "date_label", "chip", "days")}


def month_spend_tile(db: Session, user: User, today: jdatetime.date) -> dict:
    """This Jalali month's daily spends and today's, same sums as the spending page."""
    _slices, month_total = month_chart(db, user, today.year, today.month)
    today_g = today.togregorian()
    today_total = sum(
        (
            Decimal(row.amount_toman)
            for row in db.query(DailySpend)
            .filter(DailySpend.user_id == user.id, DailySpend.spent_on == today_g)
            .all()
        ),
        Decimal("0"),
    )
    return {
        "month_label": format_toman(month_total),
        "today_label": format_toman(today_total),
        "month_title": f"{JALALI_MONTHS[today.month - 1]} {persian_digits(str(today.year))}",
    }


USD_EQUIV_KEYS = frozenset({"btc", "eth", "ada", "sol", "doge", "matic"})



PRICE_STALE_AFTER = timedelta(hours=2)  # the scheduler runs hourly; 2h = at least one missed run (Arabi, home v2)


def age_label_fa(delta: timedelta) -> str:
    """«۴ دقیقه» / «۳ ساعت» / «۲ روز»; under a minute: «لحظاتی»."""
    sec = max(0, int(delta.total_seconds()))
    if sec < 60:
        return "لحظاتی"
    if sec < 3600:
        return f"{persian_digits(str(sec // 60))} دقیقه"
    if sec < 86400:
        return f"{persian_digits(str(sec // 3600))} ساعت"
    return f"{persian_digits(str(sec // 86400))} روز"


def price_status(fetched_at, now) -> dict:
    """Home price line: state fresh | stale | error (last fetch failed after the newest stored price)."""
    from app import price_fetch_state

    if fetched_at is not None and fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = (now - fetched_at) if fetched_at is not None else None
    last = price_fetch_state.last()
    failed = bool(last and not last[0] and (fetched_at is None or last[1] >= fetched_at))
    if failed:
        state = "error"
    elif age is None or age >= PRICE_STALE_AFTER:
        state = "stale"
    else:
        state = "fresh"
    old = age is None or age >= PRICE_STALE_AFTER
    return {"state": state, "old": old, "age": age_label_fa(age) if age is not None else None}


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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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
    now = utcnow()
    total = view.total_toman if view.total_toman > 0 else Decimal("1")
    debts = db.query(Debt).filter(Debt.user_id == user.id).all()
    _debt_list, debt_total, next_debt_label = debt_rows(debts)
    recent_snaps = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.taken_at >= now - CHANGE_LOOKBACK - timedelta(days=1),
        )
        .all()
    )
    changes = net_worth_changes(recent_snaps, view, debt_total, now)
    week_prices = snapshot_unit_prices(
        reference_snapshot(recent_snaps, now, CHANGE_WINDOWS[1][1], CHANGE_WINDOWS[1][2])
    )
    usd_row = next((row for row in view.rows if row.key == "usd"), None)
    usd_price = usd_row.unit_price if usd_row is not None else None
    rows = []
    for row in view.rows:
        places = ASSET_META[row.key]["qty_places"]
        share = (row.value_toman / total * Decimal("100")).quantize(Decimal("0.1"))
        week_chip, sort_week = asset_week_change(row, week_prices)
        if row.key == "usd":
            quantity_label = format_usd(row.quantity, fixed=True)
        else:
            quantity_label = format_qty(row.quantity, places if row.key not in ("car", "cash") else 0)
        usd_equiv_label = None
        if row.key in USD_EQUIV_KEYS and usd_price and row.value_toman > 0:
            usd_equiv_label = format_usd(row.value_toman / usd_price, fixed=True)
        rows.append(
            {
                "key": row.key,
                "name_fa": row.name_fa,
                "color": ASSET_SPARKLINE_COLORS.get(row.key, "#9aa3b2"),
                "week_chip": week_chip,
                "quantity_label": quantity_label,
                "unit_fa": "دلار" if row.key == "usd" else row.unit_fa,
                "unit_price_label": format_toman(row.unit_price),
                "value_label": format_toman(row.value_toman),
                "usd_equiv_label": usd_equiv_label,
                "share_label": format_share_label(share),
                "share_width": str(min(max(share, Decimal("0")), Decimal("100"))),
                "manual": row.manual,
                "sanjeh": row.sanjeh,
                "sort_qty": str(row.quantity),
                "sort_unit_price": str(row.unit_price) if row.unit_price is not None else "",
                "sort_value": str(row.value_toman),
                "value_num": float(row.value_toman),
                "sort_share": str(share),
                "sort_max_gain": sort_week,
            }
        )
    missing_fa = [ASSET_LABEL_FA.get(k, k) for k in view.missing_prices]
    chart_data = build_chart_data(db, user.id, view, now)
    chart_json = json.dumps(chart_data, ensure_ascii=False)
    chart_asset_options = [{"key": "total", "name_fa": "جمع کل"}] + [
        {"key": row.key, "name_fa": row.name_fa} for row in view.rows
    ]
    default_chart_asset_key = "total"
    pie_data = build_pie_data(view)
    for slice_ in pie_data["slices"]:
        slice_["color"] = ASSET_SPARKLINE_COLORS.get(slice_["key"], "#9aa3b2")
    pie_json = json.dumps(pie_data, ensure_ascii=False)
    flash_message, flash_error = pop_flash(request)
    refresh_wait_sec = market_price_refresh_wait_seconds(db)
    refresh_wait_label = None
    if refresh_wait_sec > 0:
        minutes = max(1, (refresh_wait_sec + 59) // 60)
        refresh_wait_label = f"دوباره تا {persian_digits(str(minutes))} دقیقه"
    monthly = monthly_view(db, user)
    if usd_price is not None and usd_price > 0:
        usd_portfolio_label = _format_usd(view.total_toman / usd_price)
    else:
        usd_portfolio_label = "—"
    today_j = tehran_today()  # same "today" as the debts and spending pages
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
        total_big=big_toman(view.total_toman),
        debt_total_label=format_toman(debt_total),
        has_debt=debt_total != 0,
        debt_big=big_toman(debt_total),
        next_debt_label=next_debt_label,
        next_instalment=next_instalment(debts, today_j),
        month_spend=month_spend_tile(db, user, today_j) if tab != "daily" else None,
        net_label=format_toman(view.total_toman - debt_total),
        usd_portfolio_label=usd_portfolio_label,
        changes=changes,
        income_month_label=monthly["income_month_label"],
        installment_month_label=monthly["installment_month_label"],
        expense_month_label=monthly["expense_month_label"],
        monthly_left_label=monthly["monthly_left_label"],
        total_week_chip=changes["7d"],
        fetched_label=format_when(view.prices_fetched_at),
        price=price_status(view.prices_fetched_at, utcnow()),
        missing_fa=missing_fa,
        chart_json=chart_json,
        chart_asset_options=chart_asset_options,
        default_chart_asset_key=default_chart_asset_key,
        pie_json=pie_json,
        pie_slices=pie_data["slices"],
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
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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
        # no flash: the home page shows the «قیمت تازه از چنده نرسید» banner from price_fetch_state
        return RedirectResponse("/dashboard", status_code=303)
    flash(request, "قیمت بازار و پرتفوی به‌روز شد")
    return RedirectResponse("/dashboard", status_code=303)
