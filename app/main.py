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
from app.models import Debt, MonthlyExpense, PortfolioSnapshot, User, utcnow
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
    sign = "−" if quantized < 0 else ""
    formatted = f"{abs(int(quantized)):,}".replace(",", "٬")
    return sign + persian_digits(formatted)


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


def next_jalali_due(day: int, today: jdatetime.date | None = None) -> jdatetime.date | None:
    """First Jalali date on or after today whose day-of-month is `day`."""
    today = today or jdatetime.date.today()
    year, month = today.year, today.month
    for _ in range(26):
        try:
            candidate = jdatetime.date(year, month, day)
        except ValueError:
            candidate = None
        if candidate is not None and candidate >= today:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return None


def format_jalali_date(value: jdatetime.date) -> str:
    return persian_digits(f"{value.year}/{value.month:02d}/{value.day:02d}")


def debt_rows(debts: list[Debt]) -> tuple[list[dict], Decimal, str]:
    rows = []
    total = Decimal("0")
    soonest: jdatetime.date | None = None
    for debt in debts:
        amount = Decimal(debt.monthly_toman) * Decimal(debt.months_left)
        total += amount
        nxt = next_jalali_due(debt.due_day)
        if nxt is not None and (soonest is None or nxt < soonest):
            soonest = nxt
        rows.append(
            {
                "id": debt.id,
                "title": (debt.title or "").strip(),
                "monthly_raw": format(Decimal(debt.monthly_toman), "f").rstrip("0").rstrip("."),
                "months_raw": str(debt.months_left),
                "due_year": str(debt.due_year),
                "due_month": str(debt.due_month),
                "due_day": str(debt.due_day),
                "monthly_label": format_toman(debt.monthly_toman),
                "months_label": persian_digits(str(debt.months_left)),
                "entered_label": format_jalali_date(
                    jdatetime.date(debt.due_year, debt.due_month, debt.due_day)
                ),
                "total_label": format_toman(amount),
                "next_label": format_jalali_date(nxt) if nxt else "—",
            }
        )
    return rows, total, format_jalali_date(soonest) if soonest else "—"


def _monthly_view(
    db: Session,
    user: User,
    expense_form: dict | None = None,
    editing_expense_id: int | None = None,
) -> dict:
    """Monthly cash report. Salary comes only from the profile account field."""
    loans = db.query(Debt).filter(Debt.user_id == user.id).all()
    installment = sum((Decimal(row.monthly_toman) for row in loans), Decimal("0"))
    income_total = Decimal(user.salary_toman or 0)
    items = (
        db.query(MonthlyExpense)
        .filter(MonthlyExpense.user_id == user.id)
        .order_by(MonthlyExpense.id.asc())
        .all()
    )
    rows = []
    expense_total = Decimal("0")
    for item in items:
        amount = Decimal(item.amount_toman)
        expense_total += amount
        nxt = next_jalali_due(item.due_day)
        rows.append(
            {
                "id": item.id,
                "title": (item.title or "").strip(),
                "amount_raw": format(amount, "f").rstrip("0").rstrip("."),
                "due_day": str(item.due_day),
                "amount_label": format_toman(amount),
                "day_label": persian_digits(str(item.due_day)),
                "next_label": format_jalali_date(nxt) if nxt else "—",
            }
        )
    outflow = installment + expense_total
    return {
        "expenses": rows,
        "installment_month_label": format_toman(installment),
        "expense_month_label": format_toman(expense_total),
        "income_month_label": format_toman(income_total),
        "monthly_pay_label": format_toman(outflow),
        "monthly_left_label": format_toman(income_total - outflow),
        "expense_form": expense_form or {"title": "", "amount_toman": "", "due_day": ""},
        "editing_expense_id": editing_expense_id,
    }


def _expense_form_for_request(db: Session, user: User, request: Request) -> dict:
    view = _monthly_view(db, user)
    spend = request.query_params.get("spend", "")
    editing = next((row for row in view["expenses"] if spend.isdigit() and row["id"] == int(spend)), None)
    if editing is not None:
        view["editing_expense_id"] = editing["id"]
        view["expense_form"] = {
            "title": editing["title"],
            "amount_toman": editing["amount_raw"],
            "due_day": editing["due_day"],
        }
    return view


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
    monthly = _monthly_view(db, user)
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
    db.query(Debt).filter(Debt.user_id == user_id).delete(synchronize_session=False)
    db.query(MonthlyExpense).filter(MonthlyExpense.user_id == user_id).delete(synchronize_session=False)
    db.delete(target)
    db.commit()
    flash(request, f"کاربر «{username}» و تمام داده‌هایش حذف شد.")
    return RedirectResponse("/admin", status_code=303)


from app.db_admin import router as db_admin_router
from app.mcp_http import hash_mcp_token, router as mcp_router

app.include_router(db_admin_router)
app.include_router(mcp_router)


@app.get("/profile", response_class=HTMLResponse)
async def profile_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    tab = request.query_params.get("tab", "assets")
    if tab not in ("assets", "debts"):
        tab = "assets"
    debts, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
    )
    edit_raw = request.query_params.get("edit", "")
    editing = next((row for row in debts if edit_raw.isdigit() and row["id"] == int(edit_raw)), None)
    debt_form = (
        {
            "title": editing["title"],
            "monthly_toman": editing["monthly_raw"],
            "months_left": editing["months_raw"],
            "due_year": editing["due_year"],
            "due_month": editing["due_month"],
            "due_day": editing["due_day"],
        }
        if editing
        else {"title": "", "monthly_toman": "", "months_left": "", "due_year": "", "due_month": "", "due_day": ""}
    )
    flash_message, flash_error = pop_flash(request)
    mcp_token = request.session.pop("mcp_token_once", None)
    mcp_cursor_config = None
    if mcp_token:
        mcp_url = str(request.base_url).rstrip("/") + "/mcp"
        mcp_cursor_config = json.dumps(
            {
                "mcpServers": {
                    "my-inventory": {
                        "url": mcp_url,
                        "headers": {"Authorization": f"Bearer {mcp_token}"},
                    }
                }
            },
            indent=2,
            ensure_ascii=False,
        )
    return render(
        request,
        "profile.html",
        db,
        mcp_token=mcp_token,
        mcp_cursor_config=mcp_cursor_config,
        error=None,
        flash=flash_message,
        flash_error=flash_error,
        form=_holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab=tab,
        debts=debts,
        debt_total_label=format_toman(debt_total),
        next_debt_label=next_debt_label,
        editing_id=editing["id"] if editing else None,
        debt_form=debt_form,
        account=_account_form(user),
        account_error=None,
        **_expense_form_for_request(db, user, request),
    )


@app.post("/profile/mcp-token")
async def issue_mcp_token(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    raw = secrets.token_urlsafe(32)
    user.mcp_token_hash = hash_mcp_token(raw)
    db.commit()
    request.session["mcp_token_once"] = raw
    flash(request, "توکن MCP ساخته شد. همین حالا کپی کنید.")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/mcp-token/revoke")
async def revoke_mcp_token(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    user.mcp_token_hash = None
    db.commit()
    flash(request, "توکن MCP حذف شد.")
    return RedirectResponse("/profile", status_code=303)


def _parse_months_left(raw: str) -> tuple[int | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    try:
        value = int(text)
    except ValueError:
        return None, "تعداد ماه مانده باید عدد باشد"
    if value < 1:
        return None, "تعداد ماه مانده باید حداقل ۱ باشد"
    return value, None


def _parse_jalali_parts(year: str, month: str, day: str) -> tuple[jdatetime.date | None, str | None]:
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    try:
        parsed = jdatetime.date(int(year.strip().translate(trans)), int(month.strip().translate(trans)), int(day.strip().translate(trans)))
    except (TypeError, ValueError):
        return None, "تاریخ جلالی نامعتبر است"
    return parsed, None


@app.post("/profile/debts")
async def profile_add_debt(
    request: Request,
    title: str = Form(""),
    monthly_toman: str = Form(""),
    months_left: str = Form(""),
    due_year: str = Form(""),
    due_month: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = {
        "title": title.strip()[:64],
        "monthly_toman": monthly_toman,
        "months_left": months_left,
        "due_year": due_year,
        "due_month": due_month,
        "due_day": due_day,
    }
    try:
        monthly = parse_decimal(monthly_toman, field="مبلغ ماهانه")
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
        monthly = None
    else:
        error = "مبلغ ماهانه باید بیشتر از صفر باشد" if monthly <= 0 else None
    months, months_error = _parse_months_left(months_left)
    due, due_error = _parse_jalali_parts(due_year, due_month, due_day)
    error = error or months_error or due_error
    if error or monthly is None or months is None or due is None:
        debts, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
    )
        return render(
            request,
            "profile.html",
            db,
            error=error,
            flash=None,
            form=_holdings_form(user),
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            tab="debts",
            debts=debts,
            debt_total_label=format_toman(debt_total),
            next_debt_label=next_debt_label,
            editing_id=None,
            debt_form=form,
            **_monthly_view(db, user),
        )
    db.add(
        Debt(
            user_id=user.id,
            title=form["title"],
            monthly_toman=monthly,
            months_left=months,
            due_year=due.year,
            due_month=due.month,
            due_day=due.day,
        )
    )
    db.commit()
    flash(request, "بدهی ذخیره شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@app.post("/profile/debts/{debt_id}")
async def profile_update_debt(
    debt_id: int,
    request: Request,
    title: str = Form(""),
    monthly_toman: str = Form(""),
    months_left: str = Form(""),
    due_year: str = Form(""),
    due_month: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    debt = db.get(Debt, debt_id)
    if debt is None or debt.user_id != user.id:
        flash(request, "بدهی پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    form = {
        "title": title.strip()[:64],
        "monthly_toman": monthly_toman,
        "months_left": months_left,
        "due_year": due_year,
        "due_month": due_month,
        "due_day": due_day,
    }
    try:
        monthly = parse_decimal(monthly_toman, field="مبلغ ماهانه")
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
        monthly = None
    else:
        error = "مبلغ ماهانه باید بیشتر از صفر باشد" if monthly <= 0 else None
    months, months_error = _parse_months_left(months_left)
    due, due_error = _parse_jalali_parts(due_year, due_month, due_day)
    error = error or months_error or due_error
    if error or monthly is None or months is None or due is None:
        debts, debt_total, next_debt_label = debt_rows(
            db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
        )
        return render(
            request,
            "profile.html",
            db,
            error=error,
            flash=None,
            form=_holdings_form(user),
            has_sanjeh_token=bool(user.sanjeh_token),
            car_fetched_label=format_when(user.car_fetched_at),
            car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
            tab="debts",
            debts=debts,
            debt_total_label=format_toman(debt_total),
            next_debt_label=next_debt_label,
            editing_id=debt_id,
            debt_form=form,
            **_monthly_view(db, user),
        )
    debt.title = form["title"]
    debt.monthly_toman = monthly
    debt.months_left = months
    debt.due_year = due.year
    debt.due_month = due.month
    debt.due_day = due.day
    db.commit()
    flash(request, "بدهی به‌روز شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@app.post("/profile/debts/{debt_id}/delete")
async def profile_delete_debt(
    debt_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    debt = db.get(Debt, debt_id)
    if debt is None or debt.user_id != user.id:
        flash(request, "بدهی پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    db.delete(debt)
    db.commit()
    flash(request, "بدهی حذف شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


def _parse_due_day(raw: str) -> tuple[int | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    try:
        day = int(text)
    except ValueError:
        return None, "روز ماه باید عدد باشد"
    if day < 1 or day > 31:
        return None, "روز ماه باید بین ۱ و ۳۱ باشد"
    return day, None


def _read_expense_fields(title: str, amount_toman: str, due_day: str):
    form = {"title": title.strip()[:64], "amount_toman": amount_toman, "due_day": due_day}
    try:
        amount = parse_decimal(amount_toman, field="مبلغ ماهانه")
    except Exception as exc:
        return form, None, None, str(getattr(exc, "detail", None) or "مبلغ ماهانه نامعتبر است")
    if amount <= 0:
        return form, None, None, "مبلغ ماهانه باید بیشتر از صفر باشد"
    day, day_error = _parse_due_day(due_day)
    return form, amount, day, day_error


def _render_expense_error(request, db, user, error, form, editing_expense_id):
    debts, debt_total, next_debt_label = debt_rows(
        db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all()
    )
    return render(
        request,
        "profile.html",
        db,
        error=error,
        flash=None,
        form=_holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab="debts",
        debts=debts,
        debt_total_label=format_toman(debt_total),
        next_debt_label=next_debt_label,
        editing_id=None,
        debt_form={"title": "", "monthly_toman": "", "months_left": "", "due_year": "", "due_month": "", "due_day": ""},
        **_monthly_view(db, user, expense_form=form, editing_expense_id=editing_expense_id),
    )


@app.post("/profile/expenses")
async def profile_add_expense(
    request: Request,
    title: str = Form(""),
    amount_toman: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form, amount, day, error = _read_expense_fields(title, amount_toman, due_day)
    if error or amount is None or day is None:
        return _render_expense_error(request, db, user, error or "مقادیر نامعتبر است", form, None)
    db.add(MonthlyExpense(user_id=user.id, title=form["title"], amount_toman=amount, due_day=day))
    db.commit()
    flash(request, "خرج ماهانه ذخیره شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@app.post("/profile/expenses/{expense_id}")
async def profile_update_expense(
    expense_id: int,
    request: Request,
    title: str = Form(""),
    amount_toman: str = Form(""),
    due_day: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        flash(request, "خرج ماهانه پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    form, amount, day, error = _read_expense_fields(title, amount_toman, due_day)
    if error or amount is None or day is None:
        return _render_expense_error(request, db, user, error or "مقادیر نامعتبر است", form, expense_id)
    item.title = form["title"]
    item.amount_toman = amount
    item.due_day = day
    db.commit()
    flash(request, "خرج ماهانه به‌روز شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


@app.post("/profile/expenses/{expense_id}/delete")
async def profile_delete_expense(
    expense_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    item = db.get(MonthlyExpense, expense_id)
    if item is None or item.user_id != user.id:
        flash(request, "خرج ماهانه پیدا نشد.", error=True)
        return RedirectResponse("/profile?tab=debts", status_code=303)
    db.delete(item)
    db.commit()
    flash(request, "خرج ماهانه حذف شد")
    return RedirectResponse("/profile?tab=debts", status_code=303)


def _account_form(user: User, **overrides: str) -> dict[str, str]:
    salary = Decimal(getattr(user, "salary_toman", 0) or 0)
    text = format(salary, "f").rstrip("0").rstrip(".")
    data = {
        "full_name": user.full_name or "",
        "username": user.username,
        "mobile": user.mobile or "",
        "salary_toman": text,
    }
    data.update(overrides)
    return data


def _parse_mobile(raw: str) -> tuple[str | None, str | None]:
    text = (raw or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits == "":
        return "", None
    if not 10 <= len(digits) <= 15:
        return None, "شماره موبایل باید ۱۰ تا ۱۵ رقم باشد"
    return digits, None


def _render_account_error(request, db, user, message: str, account: dict):
    return render(
        request,
        "profile.html",
        db,
        error=None,
        flash=None,
        form=_holdings_form(user),
        has_sanjeh_token=bool(user.sanjeh_token),
        car_fetched_label=format_when(user.car_fetched_at),
        car_value_label=format_toman(Decimal(user.car_toman or 0)) if user.sanjeh_token else None,
        tab="assets",
        account=account,
        account_error=message,
    )


@app.post("/profile/account")
async def profile_account(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    mobile: str = Form(""),
    salary_toman: str = Form("0"),
    current_password: str = Form(""),
    new_password: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    account = {
        "full_name": full_name.strip()[:80],
        "username": username,
        "mobile": mobile,
        "salary_toman": salary_toman,
    }
    name = normalize_username(username)
    name_error = validate_username(name)
    if name_error:
        return _render_account_error(request, db, user, name_error, account)
    taken = db.query(User).filter(User.username == name, User.id != user.id).first()
    if taken is not None:
        return _render_account_error(request, db, user, "این نام کاربری قبلاً ثبت شده", account)
    phone, phone_error = _parse_mobile(mobile)
    if phone_error:
        return _render_account_error(request, db, user, phone_error, account)
    try:
        salary = parse_decimal(salary_toman, field="حقوق ماهانه")
    except Exception as exc:
        return _render_account_error(
            request,
            db,
            user,
            str(getattr(exc, "detail", None) or "حقوق ماهانه نامعتبر است"),
            account,
        )
    password_change = new_password != ""
    username_change = name != user.username
    if password_change or username_change:
        if not verify_password(current_password, user.password_hash):
            return _render_account_error(request, db, user, "رمز فعلی نادرست است", account)
    if password_change:
        password_error = validate_password(new_password)
        if password_error:
            return _render_account_error(request, db, user, password_error, account)
        user.password_hash = hash_password(new_password)
    user.full_name = account["full_name"]
    user.username = name
    user.mobile = phone or ""
    user.salary_toman = salary
    db.commit()
    flash(request, "حساب ذخیره شد")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile")
async def profile_save(
    request: Request,
    gold_grams: str = Form("0"),
    coin_emami: str = Form("0"),
    coin_bahar: str = Form("0"),
    coin_half: str = Form("0"),
    coin_quarter: str = Form("0"),
    coin_gram: str = Form("0"),
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
        "coin_emami": coin_emami,
        "coin_bahar": coin_bahar,
        "coin_half": coin_half,
        "coin_quarter": coin_quarter,
        "coin_gram": coin_gram,
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
        user.coin_emami = parse_decimal(coin_emami, field="coin_emami")
        user.coin_bahar = parse_decimal(coin_bahar, field="coin_bahar")
        user.coin_half = parse_decimal(coin_half, field="coin_half")
        user.coin_quarter = parse_decimal(coin_quarter, field="coin_quarter")
        user.coin_gram = parse_decimal(coin_gram, field="coin_gram")
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
            account=_account_form(user),
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
            account=_account_form(user),
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
            account=_account_form(user),
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
        "coin_emami": format_qty(Decimal(user.coin_emami or 0), 2),
        "coin_bahar": format_qty(Decimal(user.coin_bahar or 0), 2),
        "coin_half": format_qty(Decimal(user.coin_half or 0), 2),
        "coin_quarter": format_qty(Decimal(user.coin_quarter or 0), 2),
        "coin_gram": format_qty(Decimal(user.coin_gram or 0), 2),
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
