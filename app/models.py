from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(80), default="")
    mobile: Mapped[str] = mapped_column(String(20), default="")
    salary_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    gold_grams: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    coin_emami: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    coin_bahar: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    coin_half: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    coin_quarter: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    coin_gram: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    silver_grams: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    btc: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    ada: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    eth: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    sol: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    doge: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    matic: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    cash_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    car_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    car_count: Mapped[int] = mapped_column(default=0)
    sanjeh_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mcp_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    car_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(back_populates="user")
    debts: Mapped[list["Debt"]] = relationship(back_populates="user")
    monthly_expenses: Mapped[list["MonthlyExpense"]] = relationship(back_populates="user")
    spend_categories: Mapped[list["SpendCategory"]] = relationship(back_populates="user")
    daily_spends: Mapped[list["DailySpend"]] = relationship(back_populates="user")


class MarketPrice(Base):
    __tablename__ = "market_prices"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    price_toman: Mapped[Decimal] = mapped_column(Numeric(24, 4))
    source_updated_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    total_toman: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    breakdown_json: Mapped[str] = mapped_column(Text, default="{}")

    user: Mapped[User] = relationship(back_populates="snapshots")


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(64), default="")
    monthly_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    months_left: Mapped[int] = mapped_column()
    due_year: Mapped[int] = mapped_column()
    due_month: Mapped[int] = mapped_column()
    due_day: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="debts")


class MonthlyExpense(Base):
    """Recurring monthly cost such as rent. Not included in portfolio reports."""

    __tablename__ = "monthly_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(64), default="")
    amount_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    due_day: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="monthly_expenses")


class SpendCategory(Base):
    """Parent or subcategory for one-off daily spends. Seed rows stay; users may add more."""

    __tablename__ = "spend_categories"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_spend_category_user_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("spend_categories.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="spend_categories")
    parent: Mapped["SpendCategory | None"] = relationship(remote_side="SpendCategory.id")


class DailySpend(Base):
    """One-off daily spend in toman. Not part of portfolio value or مانده."""

    __tablename__ = "daily_spends"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("spend_categories.id"), index=True)
    amount_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    spent_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="daily_spends")
    category: Mapped[SpendCategory] = relationship()
