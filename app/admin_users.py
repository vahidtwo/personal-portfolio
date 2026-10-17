"""Admin user list and account deletion."""

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_toman, format_when, persian_digits
from app.models import PortfolioSnapshot, User
from app.portfolio import ASSET_LABEL_FA, ASSET_ORDER, build_portfolio, latest_market_prices_fetched_at, load_prices
from app.security import PERSIAN_DIGITS, get_authenticated_user, is_admin, redirect_to_login, require_csrf
from app.user_delete import (
    BACKUP_NAME_RE, DeleteRefused, count_labels, count_user_rows, delete_users, new_backup_name, protected_reason,
)
from app.web import flash, pop_flash, render

router = APIRouter()


def _is_admin_name(name: str) -> bool:
    import app.security as security
    return security.normalize_username(name) in security.ADMIN_USERNAMES

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
                "can_delete": account.id != current_user_id and not _is_admin_name(account.username),
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


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    if user is None:
        return redirect_to_login(request)
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


def _admin_or_redirect(request: Request, db: Session):
    admin = get_authenticated_user(request, db)
    if admin is None:
        return None, redirect_to_login(request)
    if not is_admin(admin):
        flash(request, "دسترسی مدیریت ندارید.", error=True)
        return None, RedirectResponse("/dashboard", status_code=303)
    return admin, None


def _parse_ids(raw: list[str]) -> list[int]:
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(str(item).translate(PERSIAN_DIGITS)))
        except ValueError:
            continue
    return sorted(set(out))


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    """Single delete: goes through the same confirm flow as batch delete."""
    require_csrf(request, csrf)
    admin, resp = _admin_or_redirect(request, db)
    if resp:
        return resp
    return RedirectResponse(f"/admin/users/delete?ids={user_id}", status_code=303)


@router.get("/admin/users/delete", response_class=HTMLResponse)
async def admin_delete_confirm(request: Request, db: Session = Depends(get_db)):
    admin, resp = _admin_or_redirect(request, db)
    if resp:
        return resp
    ids = _parse_ids(request.query_params.getlist("ids"))
    if not ids:
        flash(request, "هیچ کاربری انتخاب نشده است.", error=True)
        return RedirectResponse("/admin", status_code=303)
    users = db.query(User).filter(User.id.in_(ids)).order_by(User.id).all()
    if len(users) != len(ids):
        flash(request, "برخی کاربران پیدا نشدند.", error=True)
        return RedirectResponse("/admin", status_code=303)
    for u in users:
        reason = protected_reason(u, admin)
        if reason:
            flash(request, reason, error=True)
            return RedirectResponse("/admin", status_code=303)
    counts = {u.id: count_user_rows(db, u.id) for u in users}
    keys: list[str] = []
    for c in counts.values():
        keys += [k for k in c if k not in keys]
    labels = count_labels(keys)
    rows = [
        {
            "id": u.id,
            "username": u.username,
            "counts": [(label, persian_digits(str(counts[u.id].get(key, 0)))) for key, label in labels],
            "total": persian_digits(str(sum(counts[u.id].values()))),
        }
        for u in users
    ]
    return render(
        request,
        "admin_delete_confirm.html",
        db,
        rows=rows,
        count_labels=[label for _, label in labels],
        user_count=persian_digits(str(len(users))),
        ids=[u.id for u in users],
        expected_json=json.dumps({str(k): v for k, v in counts.items()}),
        backup_name=new_backup_name(),
    )


@router.post("/admin/users/delete")
async def admin_delete_users(
    request: Request,
    csrf: str = Form(""),
    ids: list[str] = Form(default=[]),
    expected_json: str = Form(""),
    backup_name: str = Form(""),
    confirm_count: str = Form(""),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf)
    admin, resp = _admin_or_redirect(request, db)
    if resp:
        return resp
    id_list = _parse_ids(ids)
    back = "/admin/users/delete?" + "&".join(f"ids={i}" for i in id_list) if id_list else "/admin"
    if confirm_count.strip().translate(PERSIAN_DIGITS) != str(len(id_list)) or not id_list:
        flash(request, "برای تأیید، تعداد کاربران را درست وارد کنید.", error=True)
        return RedirectResponse(back, status_code=303)
    try:
        expected = {int(k): {str(t): int(n) for t, n in v.items()} for k, v in json.loads(expected_json).items()}
    except (ValueError, AttributeError, TypeError):
        flash(request, "فرم تأیید نامعتبر است.", error=True)
        return RedirectResponse(back, status_code=303)
    if not BACKUP_NAME_RE.match(backup_name):
        flash(request, "نام فایل پشتیبان نامعتبر است.", error=True)
        return RedirectResponse(back, status_code=303)
    db.rollback()
    try:
        delete_users(db, admin, id_list, expected, backup_name)
    except DeleteRefused as exc:
        flash(request, str(exc), error=True)
        return RedirectResponse(back if "پشتیبان" not in str(exc) else "/admin", status_code=303)
    flash(
        request,
        f"{persian_digits(str(len(id_list)))} کاربر و تمام داده‌هایشان حذف شد. پشتیبان: {backup_name}",
    )
    return RedirectResponse("/admin", status_code=303)
