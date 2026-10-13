"""Rule (Vahid, Oct 13 2026): never delete a user who has any data."""
from sqlalchemy.orm import Session

from app.models import (
    DailySpend, Debt, Holding, MonthlyExpense, PortfolioSnapshot, PushDeviceToken, SpendCategory, User,
)

USER_HAS_DATA_ERROR = "این کاربر داده دارد (دارایی، تاریخچه، بدهی یا خرج) و حذف نمی‌شود."


def user_has_data(db: Session, user: User) -> bool:
    uid = user.id
    for model in (PortfolioSnapshot, Holding, Debt, MonthlyExpense, DailySpend, PushDeviceToken):
        if db.query(model.id).filter(model.user_id == uid).first() is not None:
            return True
    if db.query(SpendCategory.id).filter(SpendCategory.user_id == uid, SpendCategory.is_seed.is_(False)).first():
        return True
    return False
