"""Admin user list and account deletion."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.formatting import format_toman, format_when, persian_digits
from app.models import DailySpend, Debt, MonthlyExpense, PortfolioSnapshot, SpendCategory, User
from app.portfolio import ASSET_LABEL_FA, ASSET_ORDER, build_portfolio, latest_market_prices_fetched_at, load_prices
from app.security import get_current_user, is_admin, require_csrf
from app.web import flash, pop_flash, render

router = APIRouter()

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


@router.get("/admin", response_class=HTMLResponse)
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


@router.post("/admin/users/{user_id}/delete")
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
    db.query(DailySpend).filter(DailySpend.user_id == user_id).delete(synchronize_session=False)
    db.query(SpendCategory).filter(
        SpendCategory.user_id == user_id, SpendCategory.parent_id.is_not(None)
    ).delete(synchronize_session=False)
    db.query(SpendCategory).filter(SpendCategory.user_id == user_id).delete(synchronize_session=False)
    db.delete(target)
    db.commit()
    flash(request, f"کاربر «{username}» و تمام داده‌هایش حذف شد.")
    return RedirectResponse("/admin", status_code=303)
