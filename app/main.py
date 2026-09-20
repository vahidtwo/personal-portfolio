from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import jdatetime
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import (
    DATA_DIR,
    ENABLE_INTERNAL_SCHEDULER,
    HTTPS_ONLY,
    PRICE_MANUAL_REFRESH_MINUTES,
    SECRET_KEY,
)
from app.db import get_db, init_db
from app.jobs import (
    refresh_market_prices_for_user,
    refresh_prices_and_snapshot_user,
    refresh_user_sanjeh_car,
    run_hourly_job,
)
from app.scheduler import start_hourly_scheduler, stop_hourly_scheduler
from app.sanjeh import SanjehAuthError
from app.models import PortfolioSnapshot, User, utcnow
from app.portfolio import (
    ASSET_LABEL_FA,
    ASSET_META,
    ASSET_ORDER,
    build_portfolio,
    latest_market_prices_fetched_at,
    load_prices,
)
from app.security import (
    csrf_token,
    get_current_user,
    hash_password,
    is_admin,
    normalize_username,
    parse_decimal,
    require_csrf,
    validate_password,
    validate_username,
    verify_password,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _secret_key() -> str:
    if SECRET_KEY:
        return SECRET_KEY
    secret_path = DATA_DIR / "secret_key"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    generated = secrets.token_urlsafe(48)
    secret_path.write_text(generated, encoding="utf-8")
    logger.warning("SECRET_KEY was not set; generated %s", secret_path)
    return generated


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(text: str) -> str:
    return str(text).translate(_PERSIAN_DIGITS)


def format_toman(value: Decimal | None) -> str:
    if value is None:
        return "—"
    quantized = Decimal(value).quantize(Decimal("1"))
    formatted = f"{int(quantized):,}".replace(",", "٬")
    return persian_digits(formatted)


def format_qty(value: Decimal, places: int) -> str:
    quantized = Decimal(value).quantize(Decimal("1") if places == 0 else Decimal("0." + "0" * (places - 1) + "1"))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return persian_digits(text or "0")


def format_share_label(share: Decimal) -> str:
    text = format(share, "f").rstrip("0").rstrip(".")
    return persian_digits(text)


def format_when(value: datetime | None) -> str:
    if value is None:
        return "—"
    return format_chart_jalali(value)


def _to_tehran(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def format_chart_jalali(value: datetime) -> str:
    """Jalali date-time (Tehran) with Persian digits."""
    local = _to_tehran(value)
    j = jdatetime.datetime.fromgregorian(
        year=local.year,
        month=local.month,
        day=local.day,
        hour=local.hour,
        minute=local.minute,
    )
    return persian_digits(j.strftime("%Y/%m/%d %H:%M"))


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
    asset_options = [{"key": row.key, "label": row.name_fa} for row in view.rows]
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


def build_asset_value_history(
    db: Session,
    user_id: int,
    view,
    *,
    days: int | None = None,
    max_snaps: int = 720,
) -> dict[str, list[float]]:
    """Per-asset value (toman), chronological snapshots + current."""
    q = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user_id)
    if days is not None:
        q = q.filter(PortfolioSnapshot.taken_at >= utcnow() - timedelta(days=days))
    snaps = q.order_by(PortfolioSnapshot.taken_at.asc()).limit(max_snaps).all()
    current = {row.key: float(row.value_toman) for row in view.rows}
    trends: dict[str, list[float]] = {key: [] for key in ASSET_ORDER}
    for snap in snaps:
        bd = json.loads(snap.breakdown_json)
        for key in ASSET_ORDER:
            trends[key].append(float(bd.get(key, 0)))
    for key in ASSET_ORDER:
        trends[key].append(current.get(key, 0.0))
    return trends


def build_week_asset_trends(db: Session, user_id: int, view) -> dict[str, list[float]]:
    return build_asset_value_history(db, user_id, view, days=7)


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


templates.env.filters["toman"] = format_toman
templates.env.filters["when"] = format_when
templates.env.filters["fa"] = persian_digits


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await run_hourly_job(take_snapshots=False)
    if ENABLE_INTERNAL_SCHEDULER:
        start_hourly_scheduler()
    else:
        logger.info("Internal hourly scheduler disabled (use external cron + scripts/create_snapshot.py)")
    yield
    await stop_hourly_scheduler()


app = FastAPI(title="My Inventory", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key(),
    session_cookie="inventory_session",
    same_site="lax",
    https_only=HTTPS_ONLY,
    max_age=60 * 60 * 24 * 30,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def render(request: Request, name: str, db: Session, **context) -> HTMLResponse:
    current = get_current_user(request, db)
    context.update(
        {
            "request": request,
            "user": current,
            "is_admin": is_admin(current),
            "csrf": csrf_token(request),
        }
    )
    return templates.TemplateResponse(request, name, context)


def flash(request: Request, message: str, *, error: bool = False) -> None:
    request.session["flash"] = message
    request.session["flash_error"] = error


def pop_flash(request: Request) -> tuple[str | None, bool]:
    message = request.session.pop("flash", None)
    is_error = bool(request.session.pop("flash_error", False))
    return message, is_error


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


@app.get("/health")
async def health():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "landing.html", db)


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "register.html", db, error=None, form={"username": ""})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    username = normalize_username(username)
    error = validate_username(username) or validate_password(password)
    if error:
        return render(request, "register.html", db, error=error, form={"username": username})
    if db.query(User).filter(User.username == username).first():
        return render(
            request,
            "register.html",
            db,
            error="این نام کاربری قبلاً ثبت شده است",
            form={"username": username},
        )
    user = User(username=username, password_hash=hash_password(password), last_login_at=utcnow())
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    flash(request, "حساب شما ساخته شد. موجودی را در پروفایل وارد کنید.")
    return RedirectResponse("/profile", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html", db, error=None, form={"username": ""})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    username = normalize_username(username)
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        return render(
            request,
            "login.html",
            db,
            error="نام کاربری یا رمز عبور نادرست است",
            form={"username": username},
        )
    user.last_login_at = utcnow()
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf: str = Form("")):
    require_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


CAR_REFRESH = timedelta(hours=1)


@app.get("/dashboard", response_class=HTMLResponse)
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
    chart_asset_options = [{"key": row.key, "name_fa": row.name_fa} for row in view.rows]
    default_chart_asset_key = view.rows[0].key if view.rows else None
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
    return render(
        request,
        "dashboard.html",
        db,
        view=view,
        rows=rows,
        total_label=format_toman(view.total_toman),
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
    )


@app.post("/dashboard/refresh-prices")
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


def _build_admin_user_rows(
    db: Session, users: list[User], prices, *, current_user_id: int
) -> list[dict]:
    snapshot_counts = dict(
        db.query(PortfolioSnapshot.user_id, func.count(PortfolioSnapshot.id))
        .group_by(PortfolioSnapshot.user_id)
        .all()
    )
    rows: list[dict] = []
    for account in users:
        view = build_portfolio(account, prices)
        values = {row.key: row.value_toman for row in view.rows}
        rows.append(
            {
                "id": account.id,
                "username": account.username,
                "created_label": format_when(account.created_at),
                "last_login_label": format_when(account.last_login_at),
                "total_label": format_toman(view.total_toman),
                "snapshot_count": persian_digits(str(snapshot_counts.get(account.id, 0))),
                "sanjeh_label": "بله" if account.sanjeh_token else "—",
                "can_delete": account.id != current_user_id,
                "assets": {key: format_toman(values.get(key, Decimal("0"))) for key in ASSET_ORDER},
                "sort_user": account.username,
                "sort_created": account.created_at.isoformat() if account.created_at else "",
                "sort_last_login": account.last_login_at.isoformat() if account.last_login_at else "",
                "sort_total": str(view.total_toman),
                "sort_snapshots": str(snapshot_counts.get(account.id, 0)),
                "sort_sanjeh": "1" if account.sanjeh_token else "0",
                **{f"sort_{key}": str(values.get(key, Decimal("0"))) for key in ASSET_ORDER},
            }
        )
    return rows


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not is_admin(user):
        flash(request, "دسترسی مدیریت ندارید.", error=True)
        return RedirectResponse("/dashboard", status_code=303)

    prices = load_prices(db)
    users = db.query(User).order_by(User.id.asc()).all()
    user_rows = _build_admin_user_rows(db, users, prices, current_user_id=user.id)
    total_aum = sum(Decimal(r["sort_total"]) for r in user_rows)

    price_rows = []
    for symbol in ASSET_ORDER:
        row = prices.get(symbol)
        if row is None:
            continue
        price_rows.append(
            {
                "symbol": symbol,
                "name_fa": ASSET_LABEL_FA.get(symbol, symbol),
                "price_label": format_toman(row.price_toman),
                "fetched_label": format_when(row.fetched_at),
                "sort_symbol": symbol,
                "sort_price": str(row.price_toman),
                "sort_fetched": row.fetched_at.isoformat() if row.fetched_at else "",
            }
        )

    flash_message, flash_error = pop_flash(request)
    asset_columns = [(key, ASSET_LABEL_FA.get(key, key)) for key in ASSET_ORDER]
    return render(
        request,
        "admin.html",
        db,
        user_rows=user_rows,
        price_rows=price_rows,
        asset_columns=asset_columns,
        user_count=persian_digits(str(len(users))),
        total_aum_label=format_toman(total_aum),
        prices_fetched_label=format_when(latest_market_prices_fetched_at(prices)),
        flash=flash_message,
        flash_error=flash_error,
    )


@app.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    admin = get_current_user(request, db)
    if admin is None:
        return RedirectResponse("/login", status_code=303)
    if not is_admin(admin):
        flash(request, "دسترسی مدیریت ندارید.", error=True)
        return RedirectResponse("/dashboard", status_code=303)
    if user_id == admin.id:
        flash(request, "نمی‌توانید حساب خودتان را حذف کنید.", error=True)
        return RedirectResponse("/admin", status_code=303)

    target = db.get(User, user_id)
    if target is None:
        flash(request, "کاربر پیدا نشد.", error=True)
        return RedirectResponse("/admin", status_code=303)

    username = target.username
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user_id).delete(
        synchronize_session=False
    )
    db.delete(target)
    db.commit()
    flash(request, f"کاربر «{username}» و تمام داده‌هایش حذف شد.")
    return RedirectResponse("/admin", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return render(
        request,
        "profile.html",
        db,
        error=None,
        flash=pop_flash(request)[0],
        form=_holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
    )


@app.post("/profile")
async def profile_save(
    request: Request,
    gold_grams: str = Form("0"),
    silver_grams: str = Form("0"),
    btc: str = Form("0"),
    ada: str = Form("0"),
    eth: str = Form("0"),
    sol: str = Form("0"),
    doge: str = Form("0"),
    matic: str = Form("0"),
    usd: str = Form("0"),
    cash_toman: str = Form("0"),
    sanjeh_token: str = Form(""),
    clear_sanjeh: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = {
        "gold_grams": gold_grams,
        "silver_grams": silver_grams,
        "btc": btc,
        "ada": ada,
        "eth": eth,
        "sol": sol,
        "doge": doge,
        "matic": matic,
        "usd": usd,
        "cash_toman": cash_toman,
        "sanjeh_token": "",
    }
    try:
        user.gold_grams = parse_decimal(gold_grams, field="gold")
        user.silver_grams = parse_decimal(silver_grams, field="silver")
        user.btc = parse_decimal(btc, field="btc")
        user.ada = parse_decimal(ada, field="ada")
        user.eth = parse_decimal(eth, field="eth")
        user.sol = parse_decimal(sol, field="sol")
        user.doge = parse_decimal(doge, field="doge")
        user.matic = parse_decimal(matic, field="matic")
        user.usd = parse_decimal(usd, field="usd")
        user.cash_toman = parse_decimal(cash_toman, field="cash")
    except Exception:
        return render(
            request,
            "profile.html",
            db,
            error="یکی از مقادیر وارد شده نامعتبر است",
            flash=None,
            form=form,
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        )
    if clear_sanjeh == "1":
        user.sanjeh_token = None
        user.car_toman = Decimal("0")
        user.car_count = 0
        user.car_fetched_at = None
    elif sanjeh_token.strip():
        user.sanjeh_token = sanjeh_token.strip()
    if user.sanjeh_token:
        try:
            await refresh_user_sanjeh_car(user)
        except SanjehAuthError:
            return render(
                request,
                "profile.html",
                db,
                error="توکن سنجه نامعتبر است. در sanjeh.app پروفایل را تکمیل کنید و توکن درست را وارد کنید.",
                flash=None,
                form=form,
                has_sanjeh_token=bool(user.sanjeh_token),
                car_fetched_label=format_when(user.car_fetched_at),
                car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            )
        except Exception:
            logger.exception("Sanjeh fetch failed on profile save")
            return render(
                request,
                "profile.html",
                db,
                error="دریافت قیمت خودرو از سنجه ممکن نشد. بعداً دوباره تلاش کنید.",
                flash=None,
                form=form,
                has_sanjeh_token=bool(user.sanjeh_token),
                car_fetched_label=format_when(user.car_fetched_at),
                car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            )
    db.commit()
    await refresh_prices_and_snapshot_user(user.id)
    flash(request, "موجودی ذخیره شد")
    return RedirectResponse("/dashboard", status_code=303)


def _holdings_form(user: User) -> dict[str, str]:
    return {
        "gold_grams": format_qty(Decimal(user.gold_grams or 0), 4),
        "silver_grams": format_qty(Decimal(user.silver_grams or 0), 4),
        "btc": format_qty(Decimal(user.btc or 0), 8),
        "ada": format_qty(Decimal(user.ada or 0), 4),
        "eth": format_qty(Decimal(user.eth or 0), 8),
        "sol": format_qty(Decimal(user.sol or 0), 4),
        "doge": format_qty(Decimal(user.doge or 0), 4),
        "matic": format_qty(Decimal(user.matic or 0), 4),
        "usd": format_qty(Decimal(user.usd or 0), 2),
        "cash_toman": format_qty(Decimal(user.cash_toman or 0), 0),
    }
