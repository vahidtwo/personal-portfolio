from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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
from app.jobs import run_hourly_job
from app.models import User
from app.portfolio import ASSET_META, build_portfolio, load_prices
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
            error="این نام کاربری قبلاً ثبت شده / Username already taken",
            form={"username": username},
        )
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    flash(request, "حساب ساخته شد. موجودی را در پروفایل وارد کنید / Account created. Add holdings in Profile.")
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
            error="نام کاربری یا رمز عبور نادرست است / Invalid username or password",
            form={"username": username},
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf: str = Form("")):
    require_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    prices = load_prices(db)
    view = build_portfolio(user, prices)
    rows = []
    for row in view.rows:
        places = ASSET_META[row.key]["qty_places"]
        rows.append(
            {
                **row.__dict__,
                "quantity_label": format_qty(row.quantity, places if row.key != "car" else 0),
                "unit_price_label": format_toman(row.unit_price),
                "value_label": format_toman(row.value_toman),
            }
        )
    return render(
        request,
        "dashboard.html",
        db,
        view=view,
        rows=rows,
        total_label=format_toman(view.total_toman),
        fetched_label=format_when(view.prices_fetched_at),
        flash=pop_flash(request),
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return render(request, "profile.html", db, error=None, flash=pop_flash(request), form=_holdings_form(user))


@app.post("/profile")
async def profile_save(
    request: Request,
    gold_grams: str = Form("0"),
    btc: str = Form("0"),
    ada: str = Form("0"),
    eth: str = Form("0"),
    usd: str = Form("0"),
    car_toman: str = Form("0"),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = {
        "gold_grams": gold_grams,
        "btc": btc,
        "ada": ada,
        "eth": eth,
        "usd": usd,
        "car_toman": car_toman,
    }
    try:
        user.gold_grams = parse_decimal(gold_grams, field="gold")
        user.btc = parse_decimal(btc, field="btc")
        user.ada = parse_decimal(ada, field="ada")
        user.eth = parse_decimal(eth, field="eth")
        user.usd = parse_decimal(usd, field="usd")
        user.car_toman = parse_decimal(car_toman, field="car")
    except Exception:
        return render(
            request,
            "profile.html",
            db,
            error="یکی از مقدارها نامعتبر است / One of the values is invalid",
            flash=None,
            form=form,
        )
    db.commit()
    flash(request, "موجودی ذخیره شد / Holdings saved")
    return RedirectResponse("/dashboard", status_code=303)


def _holdings_form(user: User) -> dict[str, str]:
    return {
        "gold_grams": format_qty(Decimal(user.gold_grams or 0), 4),
        "btc": format_qty(Decimal(user.btc or 0), 8),
        "ada": format_qty(Decimal(user.ada or 0), 4),
        "eth": format_qty(Decimal(user.eth or 0), 8),
        "usd": format_qty(Decimal(user.usd or 0), 2),
        "car_toman": format_qty(Decimal(user.car_toman or 0), 0),
    }
