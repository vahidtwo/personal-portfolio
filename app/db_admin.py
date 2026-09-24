"""Admin-only editors for users, market prices, portfolio snapshots, and spend categories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.db import get_db
from app.models import DailySpend, MarketPrice, PortfolioSnapshot, SpendCategory, User, utcnow
from app.portfolio import ASSET_LABEL_FA, ASSET_META, ASSET_ORDER
from app.security import (
    get_current_user,
    hash_password,
    is_admin,
    normalize_username,
    parse_decimal,
    require_csrf,
    validate_password,
    validate_username,
)

router = APIRouter()
TEHRAN = ZoneInfo("Asia/Tehran")

HOLDING_FIELDS: tuple[tuple[str, str], ...] = tuple(
    (ASSET_META[key]["qty_attr"], f"{ASSET_META[key]['name_fa']} ({ASSET_META[key]['unit_fa']})")
    for key in ASSET_ORDER
    if key != "car"
)


def _ui():
    import app.main as main

    return main


def _require_admin(request: Request, db: Session) -> User | RedirectResponse:
    user = get_current_user(request, db)
    ui = _ui()
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not is_admin(user):
        ui.flash(request, "دسترسی مدیریت ندارید.", error=True)
        return RedirectResponse("/dashboard", status_code=303)
    return user


def _plain_decimal(value: Decimal | int | None) -> str:
    if value is None:
        return "0"
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _to_tehran(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def _datetime_input(value: datetime | None) -> str:
    if value is None:
        return ""
    return _to_tehran(value).strftime("%Y-%m-%dT%H:%M")


def _parse_datetime(raw: str, *, field: str, required: bool) -> tuple[datetime | None, str | None]:
    text = (raw or "").strip()
    if not text:
        if required:
            return None, f"{field} را وارد کنید"
        return None, None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, f"زمان نامعتبر: {field}"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TEHRAN)
    return parsed.astimezone(timezone.utc), None


def _parse_int(raw: str, *, field: str) -> tuple[int | None, str | None]:
    text = (raw or "0").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    text = text.replace(",", "").replace("٬", "")
    if text == "":
        return 0, None
    try:
        value = int(text)
    except ValueError:
        return None, f"عدد نامعتبر: {field}"
    if value < 0:
        return None, f"مقدار منفی مجاز نیست: {field}"
    return value, None


def _field(
    name: str,
    label: str,
    value: str,
    *,
    kind: str = "text",
    hint: str = "",
    span: bool = False,
    options: list[dict[str, str]] | None = None,
    text_dir: str = "ltr",
) -> dict:
    return {
        "name": name,
        "label": label,
        "value": value,
        "kind": kind,
        "dir": text_dir,
        "hint": hint,
        "span": span,
        "options": options or [],
    }


def _posted(form: FormData, name: str) -> str:
    value = form.get(name)
    if value is None:
        return ""
    return str(value)


def _user_fields(user: User | None, form: FormData | None) -> list[dict]:
    def val(name: str, current: str) -> str:
        if form is not None and name in form:
            return _posted(form, name)
        return current

    fields = [
        _field("username", "نام کاربری", val("username", user.username if user else "")),
        _field(
            "new_password",
            "رمز عبور جدید" if user else "رمز عبور",
            "",
            kind="password",
            hint="برای نگه داشتن رمز فعلی خالی بگذارید" if user else "حداقل ۸ کاراکتر",
        ),
    ]
    for attr, label in HOLDING_FIELDS:
        current = _plain_decimal(getattr(user, attr) if user else 0)
        fields.append(_field(attr, label, val(attr, current), kind="decimal"))
    fields.append(
        _field(
            "car_toman",
            "ارزش خودرو (تومان)",
            val("car_toman", _plain_decimal(user.car_toman if user else 0)),
            kind="decimal",
            hint="اگر توکن سنجه باشد، کار ساعتی این مقدار را دوباره می‌نویسد",
        )
    )
    fields.append(
        _field(
            "car_count",
            "تعداد خودرو",
            val("car_count", str(int(user.car_count or 0) if user else 0)),
            kind="int",
        )
    )
    fields.append(
        _field(
            "sanjeh_token",
            "توکن سنجه",
            val("sanjeh_token", (user.sanjeh_token or "") if user else ""),
            hint="خالی یعنی بدون اتصال به سنجه",
            span=True,
        )
    )
    fields.append(
        _field(
            "car_fetched_at",
            "زمان دریافت خودرو",
            val("car_fetched_at", _datetime_input(user.car_fetched_at if user else None)),
            kind="datetime",
        )
    )
    if user is not None:
        fields.append(_field("created_at", "عضویت", _ui().format_when(user.created_at), kind="readonly"))
        fields.append(_field("last_login_at", "آخرین ورود", _ui().format_when(user.last_login_at), kind="readonly"))
    return fields


def _price_fields(row: MarketPrice | None, form: FormData | None, *, creating: bool) -> list[dict]:
    def val(name: str, current: str) -> str:
        if form is not None and name in form:
            return _posted(form, name)
        return current

    options = [{"value": key, "label": f"{ASSET_LABEL_FA.get(key, key)} ({key})"} for key in ASSET_ORDER]
    fields = []
    if creating:
        fields.append(
            _field(
                "symbol",
                "دارایی",
                val("symbol", ""),
                kind="select",
                options=options,
            )
        )
    else:
        symbol = row.symbol if row else ""
        fields.append(_field("symbol_label", "دارایی", f"{ASSET_LABEL_FA.get(symbol, symbol)} ({symbol})", kind="readonly"))
    fields.append(
        _field(
            "price_toman",
            "قیمت (تومان)",
            val("price_toman", _plain_decimal(row.price_toman if row else 0)),
            kind="decimal",
            hint="کار ساعتی قیمت را از چنده دوباره می‌نویسد",
        )
    )
    fields.append(
        _field(
            "source_updated_at",
            "زمان منبع",
            val("source_updated_at", (row.source_updated_at or "") if row else ""),
        )
    )
    fields.append(
        _field(
            "fetched_at",
            "زمان دریافت",
            val("fetched_at", _datetime_input(row.fetched_at if row else None)),
            kind="datetime",
        )
    )
    return fields


def _snapshot_fields(db: Session, row: PortfolioSnapshot | None, form: FormData | None) -> list[dict]:
    def val(name: str, current: str) -> str:
        if form is not None and name in form:
            return _posted(form, name)
        return current

    users = db.query(User).order_by(User.username.asc()).all()
    options = [{"value": str(account.id), "label": account.username} for account in users]
    breakdown = "{}"
    if row is not None:
        try:
            breakdown = json.dumps(json.loads(row.breakdown_json or "{}"), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            breakdown = row.breakdown_json or "{}"
    return [
        _field(
            "user_id",
            "کاربر",
            val("user_id", str(row.user_id) if row else (options[0]["value"] if options else "")),
            kind="select",
            options=options,
        ),
        _field(
            "taken_at",
            "زمان",
            val("taken_at", _datetime_input(row.taken_at if row else utcnow())),
            kind="datetime",
        ),
        _field(
            "total_toman",
            "ارزش کل (تومان)",
            val("total_toman", _plain_decimal(row.total_toman if row else 0)),
            kind="decimal",
        ),
        _field(
            "breakdown_json",
            "جزئیات (JSON)",
            val("breakdown_json", breakdown),
            kind="textarea",
            hint="شیء JSON با مبلغ هر دارایی و total",
            span=True,
        ),
    ]


def catalog(db: Session) -> list[dict]:
    return [
        {
            "slug": "users",
            "label": "کاربران",
            "description": "نام کاربری، موجودی، توکن سنجه و رمز عبور",
            "count": _ui().persian_digits(str(db.query(User).count())),
        },
        {
            "slug": "market-prices",
            "label": "قیمت‌های بازار",
            "description": "قیمت تومان ذخیره‌شده برای هر دارایی",
            "count": _ui().persian_digits(str(db.query(MarketPrice).count())),
        },
        {
            "slug": "snapshots",
            "label": "اسنپ‌شات‌ها",
            "description": "تاریخچه ارزش پرتفوی",
            "count": _ui().persian_digits(str(db.query(PortfolioSnapshot).count())),
        },
        {
            "slug": "spend-categories",
            "label": "دسته‌های خرج",
            "description": "گروه و زیردسته خرج روزانه",
            "count": _ui().persian_digits(str(db.query(SpendCategory).count())),
        },
    ]


def _known_slug(slug: str) -> bool:
    return slug in {"users", "market-prices", "snapshots", "spend-categories"}


def list_view(db: Session, slug: str, query: str) -> dict:
    ui = _ui()
    needle = query.strip().lower()
    if slug == "users":
        rows = db.query(User).order_by(User.id.asc()).all()
        if needle:
            rows = [row for row in rows if needle in row.username.lower()]
        return {
            "label": "کاربران",
            "columns": ["شناسه", "کاربر", "عضویت", "آخرین ورود"],
            "rows": [
                {
                    "pk": str(row.id),
                    "cells": [
                        ui.persian_digits(str(row.id)),
                        row.username,
                        ui.format_when(row.created_at),
                        ui.format_when(row.last_login_at),
                    ],
                }
                for row in rows
            ],
        }
    if slug == "market-prices":
        rows = db.query(MarketPrice).order_by(MarketPrice.symbol.asc()).all()
        if needle:
            rows = [
                row
                for row in rows
                if needle in row.symbol.lower() or needle in ASSET_LABEL_FA.get(row.symbol, "").lower()
            ]
        return {
            "label": "قیمت‌های بازار",
            "columns": ["نماد", "دارایی", "قیمت", "دریافت"],
            "rows": [
                {
                    "pk": row.symbol,
                    "cells": [
                        row.symbol,
                        ASSET_LABEL_FA.get(row.symbol, row.symbol),
                        ui.format_toman(row.price_toman),
                        ui.format_when(row.fetched_at),
                    ],
                }
                for row in rows
            ],
        }
    if slug == "spend-categories":
        rows = (
            db.query(SpendCategory, User.username)
            .join(User, User.id == SpendCategory.user_id)
            .order_by(User.username.asc(), SpendCategory.parent_id.asc(), SpendCategory.sort_order.asc(), SpendCategory.id.asc())
            .all()
        )
        names = {row.id: row.name for row, _username in rows}
        if needle:
            rows = [
                pair
                for pair in rows
                if needle in pair[1].lower()
                or needle in pair[0].name.lower()
                or needle in names.get(pair[0].parent_id, "").lower()
            ]
        return {
            "label": "دسته‌های خرج",
            "columns": ["شناسه", "کاربر", "نام", "والد", "نوع"],
            "rows": [
                {
                    "pk": str(row.id),
                    "cells": [
                        ui.persian_digits(str(row.id)),
                        username,
                        row.name,
                        names.get(row.parent_id, "—"),
                        "زیردسته" if row.parent_id else "گروه",
                    ],
                }
                for row, username in rows
            ],
        }
    rows = (
        db.query(PortfolioSnapshot, User.username)
        .join(User, User.id == PortfolioSnapshot.user_id)
        .order_by(PortfolioSnapshot.taken_at.desc())
        .all()
    )
    if needle:
        rows = [pair for pair in rows if needle in pair[1].lower() or needle in str(pair[0].id)]
    return {
        "label": "اسنپ‌شات‌ها",
        "columns": ["شناسه", "کاربر", "زمان", "ارزش کل"],
        "rows": [
            {
                "pk": str(snap.id),
                "cells": [
                    ui.persian_digits(str(snap.id)),
                    username,
                    ui.format_when(snap.taken_at),
                    ui.format_toman(snap.total_toman),
                ],
            }
            for snap, username in rows[:300]
        ],
        "truncated": len(rows) > 300,
    }


def _load(db: Session, slug: str, pk: str):
    if slug == "users":
        if not pk.isdigit():
            return None
        return db.get(User, int(pk))
    if slug == "market-prices":
        return db.get(MarketPrice, pk)
    if slug == "spend-categories":
        if not pk.isdigit():
            return None
        return db.get(SpendCategory, int(pk))
    if pk.isdigit():
        return db.get(PortfolioSnapshot, int(pk))
    return None


def fields_for(db: Session, slug: str, obj, form: FormData | None) -> list[dict]:
    if slug == "users":
        return _user_fields(obj, form)
    if slug == "market-prices":
        return _price_fields(obj, form, creating=obj is None)
    if slug == "spend-categories":
        return _category_fields(db, obj, form)
    return _snapshot_fields(db, obj, form)


def _save_user(db: Session, user: User | None, form: FormData) -> str | None:
    username = normalize_username(_posted(form, "username"))
    error = validate_username(username)
    if error:
        return error
    taken = db.query(User).filter(User.username == username).one_or_none()
    if taken is not None and (user is None or taken.id != user.id):
        return "این نام کاربری قبلاً ثبت شده"
    password = _posted(form, "new_password")
    if user is None:
        if not password:
            return "رمز عبور را وارد کنید"
        password_error = validate_password(password)
        if password_error:
            return password_error
        user = User(username=username, password_hash=hash_password(password), created_at=utcnow())
        db.add(user)
    else:
        user.username = username
        if password:
            password_error = validate_password(password)
            if password_error:
                return password_error
            user.password_hash = hash_password(password)
    for attr, label in HOLDING_FIELDS:
        try:
            value = parse_decimal(_posted(form, attr), field=label)
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            return str(detail or f"عدد نامعتبر: {label}")
        setattr(user, attr, value)
    try:
        user.car_toman = parse_decimal(_posted(form, "car_toman"), field="ارزش خودرو")
    except Exception as exc:
        return str(getattr(exc, "detail", None) or "عدد نامعتبر: ارزش خودرو")
    count, count_error = _parse_int(_posted(form, "car_count"), field="تعداد خودرو")
    if count_error:
        return count_error
    user.car_count = count or 0
    token = _posted(form, "sanjeh_token").strip()
    user.sanjeh_token = token or None
    fetched, fetched_error = _parse_datetime(_posted(form, "car_fetched_at"), field="زمان دریافت خودرو", required=False)
    if fetched_error:
        return fetched_error
    user.car_fetched_at = fetched
    return None


def _save_price(db: Session, row: MarketPrice | None, form: FormData) -> str | None:
    if row is None:
        symbol = _posted(form, "symbol").strip()
        if symbol not in ASSET_ORDER:
            return "دارایی نامعتبر است"
        if db.get(MarketPrice, symbol) is not None:
            return "برای این دارایی قبلاً قیمت ثبت شده"
        row = MarketPrice(symbol=symbol, price_toman=Decimal("0"), fetched_at=utcnow())
        db.add(row)
    try:
        row.price_toman = parse_decimal(_posted(form, "price_toman"), field="قیمت")
    except Exception as exc:
        return str(getattr(exc, "detail", None) or "عدد نامعتبر: قیمت")
    source = _posted(form, "source_updated_at").strip()
    row.source_updated_at = source or None
    fetched, fetched_error = _parse_datetime(_posted(form, "fetched_at"), field="زمان دریافت", required=False)
    if fetched_error:
        return fetched_error
    row.fetched_at = fetched or utcnow()
    return None


def _save_snapshot(db: Session, row: PortfolioSnapshot | None, form: FormData) -> str | None:
    user_id_raw = _posted(form, "user_id").strip()
    if not user_id_raw.isdigit() or db.get(User, int(user_id_raw)) is None:
        return "کاربر را انتخاب کنید"
    taken_at, taken_error = _parse_datetime(_posted(form, "taken_at"), field="زمان", required=True)
    if taken_error:
        return taken_error
    try:
        total = parse_decimal(_posted(form, "total_toman"), field="ارزش کل")
    except Exception as exc:
        return str(getattr(exc, "detail", None) or "عدد نامعتبر: ارزش کل")
    raw_json = _posted(form, "breakdown_json").strip() or "{}"
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return "جزئیات باید JSON معتبر باشد"
    if not isinstance(parsed, dict):
        return "جزئیات باید یک شیء JSON باشد"
    if row is None:
        row = PortfolioSnapshot(
            user_id=int(user_id_raw),
            taken_at=taken_at,
            total_toman=total,
            breakdown_json=json.dumps(parsed, ensure_ascii=False),
        )
        db.add(row)
    else:
        row.user_id = int(user_id_raw)
        row.taken_at = taken_at
        row.total_toman = total
        row.breakdown_json = json.dumps(parsed, ensure_ascii=False)
    return None


def _category_fields(db: Session, row: SpendCategory | None, form: FormData | None) -> list[dict]:
    def val(name: str, current: str) -> str:
        if form is not None and name in form:
            return _posted(form, name)
        return current

    users = db.query(User).order_by(User.username.asc()).all()
    user_options = [{"value": str(account.id), "label": account.username} for account in users]
    user_id = val("user_id", str(row.user_id) if row else (user_options[0]["value"] if user_options else ""))
    parents = (
        db.query(SpendCategory)
        .filter(SpendCategory.parent_id.is_(None))
        .order_by(SpendCategory.name.asc())
        .all()
    )
    usernames = {account.id: account.username for account in users}
    parent_options = [{"value": "", "label": "بدون والد (گروه)"}]
    for parent in parents:
        if row is not None and parent.id == row.id:
            continue
        owner = usernames.get(parent.user_id, str(parent.user_id))
        parent_options.append({"value": str(parent.id), "label": f"{owner} — {parent.name}"})
    fields = []
    if row is None:
        fields.append(_field("user_id", "کاربر", user_id, kind="select", options=user_options))
    else:
        fields.append(_field("user_label", "کاربر", usernames.get(row.user_id, str(row.user_id)), kind="readonly"))
    fields.append(
        _field(
            "name",
            "نام",
            val("name", row.name if row else ""),
            text_dir="rtl",
        )
    )
    fields.append(
        _field(
            "parent_id",
            "والد",
            val("parent_id", str(row.parent_id) if row and row.parent_id else ""),
            kind="select",
            options=parent_options,
            hint="خالی یعنی گروه اصلی. والد باید مال همان کاربر باشد.",
        )
    )
    fields.append(
        _field(
            "sort_order",
            "ترتیب",
            val("sort_order", str(row.sort_order) if row else "0"),
            kind="int",
        )
    )
    if row is not None:
        fields.append(_field("seed_label", "دسته آماده", "بله" if row.is_seed else "خیر", kind="readonly"))
    return fields


def _save_category(db: Session, row: SpendCategory | None, form: FormData) -> str | None:
    name = _posted(form, "name").strip()[:64]
    if not name:
        return "نام دسته را بنویسید."
    if row is None:
        user_raw = _posted(form, "user_id").strip()
        if not user_raw.isdigit() or db.get(User, int(user_raw)) is None:
            return "کاربر را انتخاب کنید"
        user_id = int(user_raw)
    else:
        user_id = row.user_id
    parent_raw = _posted(form, "parent_id").strip()
    parent_id = None
    if parent_raw:
        if not parent_raw.isdigit():
            return "والد نامعتبر است"
        parent = db.get(SpendCategory, int(parent_raw))
        if parent is None or parent.user_id != user_id or parent.parent_id is not None:
            return "والد باید یک گروه از همین کاربر باشد"
        if row is not None and parent.id == row.id:
            return "دسته نمی‌تواند والد خودش باشد"
        parent_id = parent.id
    if row is not None and parent_id is not None:
        has_child = db.query(SpendCategory.id).filter(SpendCategory.parent_id == row.id).first() is not None
        if has_child:
            return "این گروه زیردسته دارد و نمی‌تواند زیر گروه دیگری برود"
    sort_order, sort_error = _parse_int(_posted(form, "sort_order"), field="ترتیب")
    if sort_error:
        return sort_error
    if row is None:
        db.add(
            SpendCategory(
                user_id=user_id,
                parent_id=parent_id,
                name=name,
                slug=None,
                is_seed=False,
                sort_order=sort_order or 0,
            )
        )
    else:
        row.name = name
        row.parent_id = parent_id
        row.sort_order = sort_order or 0
    return None


def save_record(db: Session, slug: str, obj, form: FormData) -> str | None:
    if slug == "users":
        return _save_user(db, obj, form)
    if slug == "market-prices":
        return _save_price(db, obj, form)
    if slug == "spend-categories":
        return _save_category(db, obj, form)
    return _save_snapshot(db, obj, form)


def delete_record(db: Session, slug: str, obj, actor_id: int) -> str | None:
    if slug == "users":
        if obj.id == actor_id:
            return "نمی‌توانید حساب خودتان را حذف کنید."
        db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == obj.id).delete(synchronize_session=False)
        db.query(DailySpend).filter(DailySpend.user_id == obj.id).delete(synchronize_session=False)
        db.query(SpendCategory).filter(
            SpendCategory.user_id == obj.id, SpendCategory.parent_id.is_not(None)
        ).delete(synchronize_session=False)
        db.query(SpendCategory).filter(SpendCategory.user_id == obj.id).delete(synchronize_session=False)
    if slug == "spend-categories":
        has_child = db.query(SpendCategory.id).filter(SpendCategory.parent_id == obj.id).first() is not None
        has_spend = db.query(DailySpend.id).filter(DailySpend.category_id == obj.id).first() is not None
        if has_child or has_spend:
            return "این دسته خرج یا زیردسته دارد و حذف نمی‌شود."
    db.delete(obj)
    return None


@router.get("/admin/db", response_class=None)
async def admin_db_index(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    ui = _ui()
    flash_message, flash_error = ui.pop_flash(request)
    return ui.render(
        request,
        "admin_db_index.html",
        db,
        tables=catalog(db),
        flash=flash_message,
        flash_error=flash_error,
    )


@router.get("/admin/db/{slug}")
async def admin_db_list(slug: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    if not _known_slug(slug):
        return RedirectResponse("/admin/db", status_code=303)
    ui = _ui()
    query = request.query_params.get("q", "")
    flash_message, flash_error = ui.pop_flash(request)
    view = list_view(db, slug, query)
    return ui.render(
        request,
        "admin_db_list.html",
        db,
        slug=slug,
        query=query,
        flash=flash_message,
        flash_error=flash_error,
        **view,
    )


@router.get("/admin/db/{slug}/new")
async def admin_db_new(slug: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    if not _known_slug(slug):
        return RedirectResponse("/admin/db", status_code=303)
    ui = _ui()
    return ui.render(
        request,
        "admin_db_form.html",
        db,
        slug=slug,
        pk=None,
        title="رکورد جدید",
        table_label=list_view(db, slug, "")["label"],
        fields=fields_for(db, slug, None, None),
        error=None,
        can_delete=False,
    )


@router.post("/admin/db/{slug}/new")
async def admin_db_create(slug: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    if not _known_slug(slug):
        return RedirectResponse("/admin/db", status_code=303)
    form = await request.form()
    require_csrf(request, str(form.get("csrf") or ""))
    ui = _ui()
    error = save_record(db, slug, None, form)
    if error:
        return ui.render(
            request,
            "admin_db_form.html",
            db,
            slug=slug,
            pk=None,
            title="رکورد جدید",
            table_label=list_view(db, slug, "")["label"],
            fields=fields_for(db, slug, None, form),
            error=error,
            can_delete=False,
        )
    db.commit()
    ui.flash(request, "رکورد ذخیره شد")
    return RedirectResponse(f"/admin/db/{slug}", status_code=303)


@router.get("/admin/db/{slug}/{pk}")
async def admin_db_edit(slug: str, pk: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    if not _known_slug(slug):
        return RedirectResponse("/admin/db", status_code=303)
    obj = _load(db, slug, pk)
    ui = _ui()
    if obj is None:
        ui.flash(request, "رکورد پیدا نشد.", error=True)
        return RedirectResponse(f"/admin/db/{slug}", status_code=303)
    flash_message, flash_error = ui.pop_flash(request)
    return ui.render(
        request,
        "admin_db_form.html",
        db,
        slug=slug,
        pk=pk,
        title="ویرایش رکورد",
        table_label=list_view(db, slug, "")["label"],
        fields=fields_for(db, slug, obj, None),
        error=None,
        flash=flash_message,
        flash_error=flash_error,
        can_delete=not (slug == "users" and obj.id == admin.id),
    )


@router.post("/admin/db/{slug}/{pk}")
async def admin_db_save(slug: str, pk: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    if not _known_slug(slug) or pk == "new":
        return RedirectResponse("/admin/db", status_code=303)
    form = await request.form()
    require_csrf(request, str(form.get("csrf") or ""))
    obj = _load(db, slug, pk)
    ui = _ui()
    if obj is None:
        ui.flash(request, "رکورد پیدا نشد.", error=True)
        return RedirectResponse(f"/admin/db/{slug}", status_code=303)
    error = save_record(db, slug, obj, form)
    if error:
        return ui.render(
            request,
            "admin_db_form.html",
            db,
            slug=slug,
            pk=pk,
            title="ویرایش رکورد",
            table_label=list_view(db, slug, "")["label"],
            fields=fields_for(db, slug, obj, form),
            error=error,
            can_delete=not (slug == "users" and obj.id == admin.id),
        )
    db.commit()
    ui.flash(request, "تغییرات ذخیره شد")
    return RedirectResponse(f"/admin/db/{slug}/{pk}", status_code=303)


@router.post("/admin/db/{slug}/{pk}/delete")
async def admin_db_delete(slug: str, pk: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    form = await request.form()
    require_csrf(request, str(form.get("csrf") or ""))
    ui = _ui()
    if not _known_slug(slug):
        return RedirectResponse("/admin/db", status_code=303)
    obj = _load(db, slug, pk)
    if obj is None:
        ui.flash(request, "رکورد پیدا نشد.", error=True)
        return RedirectResponse(f"/admin/db/{slug}", status_code=303)
    error = delete_record(db, slug, obj, admin.id)
    if error:
        ui.flash(request, error, error=True)
        return RedirectResponse(f"/admin/db/{slug}/{pk}", status_code=303)
    db.commit()
    ui.flash(request, "رکورد حذف شد")
    return RedirectResponse(f"/admin/db/{slug}", status_code=303)
