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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import DATA_DIR, HTTPS_ONLY, PRICE_REFRESH_HOURS, SECRET_KEY
from app.db import get_db, init_db
from app.jobs import refresh_prices_and_snapshot_user, refresh_user_sanjeh_car, run_hourly_job
from app.sanjeh import SanjehAuthError
from app.models import PortfolioSnapshot, User, utcnow
from app.portfolio import ASSET_LABEL_FA, ASSET_META, ASSET_ORDER, build_portfolio, load_prices
from app.security import (
    csrf_token,
    get_current_user,
    hash_password,
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
scheduler = AsyncIOScheduler()


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


def format_toman(value: Decimal | None) -> str:
    if value is None:
        return "—"
    quantized = Decimal(value).quantize(Decimal("1"))
    return f"{int(quantized):,}"


def format_qty(value: Decimal, places: int) -> str:
    quantized = Decimal(value).quantize(Decimal("1") if places == 0 else Decimal("0." + "0" * (places - 1) + "1"))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_when(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M")


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_tehran(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def format_chart_jalali(value: datetime) -> str:
    """Jalali date-time label for chart x-axis (Tehran), Persian digits."""
    local = _to_tehran(value)
    j = jdatetime.datetime.fromgregorian(
        year=local.year,
        month=local.month,
        day=local.day,
        hour=local.hour,
        minute=local.minute,
    )
    text = j.strftime("%Y/%m/%d %H:%M")
    return text.translate(_PERSIAN_DIGITS)


def build_chart_data(db: Session, user_id: int, view) -> dict:
    """Labels + per-asset series; first point is live portfolio, rest are snapshots."""
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user_id)
        .order_by(PortfolioSnapshot.taken_at.desc())
        .limit(720)
        .all()
    )
    snaps.reverse()
    labels = [format_chart_jalali(utcnow())] + [format_chart_jalali(s.taken_at) for s in snaps]

    current: dict[str, float] = {row.key: float(row.value_toman) for row in view.rows}
    current["total"] = float(view.total_toman)

    series: list[dict] = [
        {
            "key": "total",
            "label": "جمع کل",
            "data": [current["total"]]
            + [float(json.loads(s.breakdown_json).get("total", s.total_toman)) for s in snaps],
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
                "data": [current.get(key, 0.0)] + history_vals,
            }
        )
    return {"labels": labels, "series": series}


templates.env.filters["toman"] = format_toman
templates.env.filters["when"] = format_when


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await run_hourly_job(take_snapshots=False)
    scheduler.add_job(
        run_hourly_job,
        IntervalTrigger(hours=PRICE_REFRESH_HOURS),
        id="hourly-portfolio",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


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
    context.update(
        {
            "request": request,
            "user": get_current_user(request, db),
            "csrf": csrf_token(request),
        }
    )
    return templates.TemplateResponse(request, name, context)


def flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def pop_flash(request: Request) -> str | None:
    return request.session.pop("flash", None)


@app.get("/health")
async def health():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


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
    user = User(username=username, password_hash=hash_password(password))
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
    rows = []
    for row in view.rows:
        places = ASSET_META[row.key]["qty_places"]
        share = (row.value_toman / total * Decimal("100")).quantize(Decimal("0.1"))
        rows.append(
            {
                "key": row.key,
                "name_fa": row.name_fa,
                "quantity_label": format_qty(
                    row.quantity,
                    places if row.key not in ("car", "cash") else 0,
                ),
                "unit_fa": row.unit_fa,
                "unit_price_label": format_toman(row.unit_price),
                "value_label": format_toman(row.value_toman),
                "share_label": format(share, "f").rstrip("0").rstrip("."),
                "manual": row.manual,
                "sanjeh": row.sanjeh,
                "sort_qty": str(row.quantity),
                "sort_unit_price": str(row.unit_price) if row.unit_price is not None else "",
                "sort_value": str(row.value_toman),
                "sort_share": str(share),
            }
        )
    missing_fa = [ASSET_LABEL_FA.get(k, k) for k in view.missing_prices]
    chart_data = build_chart_data(db, user.id, view)
    chart_json = json.dumps(chart_data, ensure_ascii=False)
    return render(
        request,
        "dashboard.html",
        db,
        view=view,
        rows=rows,
        total_label=format_toman(view.total_toman),
        fetched_label=format_when(view.prices_fetched_at),
        missing_fa=missing_fa,
        chart_json=chart_json,
        flash=pop_flash(request),
    )


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
        flash=pop_flash(request),
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
