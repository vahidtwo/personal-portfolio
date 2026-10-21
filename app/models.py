from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, attribute_keyed_dict, mapped_column, relationship

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
    _legacy_gold_grams: Mapped[Decimal] = mapped_column("gold_grams", Numeric(20, 8), default=Decimal("0"))
    _legacy_coin_emami: Mapped[Decimal] = mapped_column("coin_emami", Numeric(20, 8), default=Decimal("0"))
    _legacy_coin_bahar: Mapped[Decimal] = mapped_column("coin_bahar", Numeric(20, 8), default=Decimal("0"))
    _legacy_coin_half: Mapped[Decimal] = mapped_column("coin_half", Numeric(20, 8), default=Decimal("0"))
    _legacy_coin_quarter: Mapped[Decimal] = mapped_column("coin_quarter", Numeric(20, 8), default=Decimal("0"))
    _legacy_coin_gram: Mapped[Decimal] = mapped_column("coin_gram", Numeric(20, 8), default=Decimal("0"))
    _legacy_silver_grams: Mapped[Decimal] = mapped_column("silver_grams", Numeric(20, 8), default=Decimal("0"))
    _legacy_btc: Mapped[Decimal] = mapped_column("btc", Numeric(20, 8), default=Decimal("0"))
    _legacy_ada: Mapped[Decimal] = mapped_column("ada", Numeric(20, 8), default=Decimal("0"))
    _legacy_eth: Mapped[Decimal] = mapped_column("eth", Numeric(20, 8), default=Decimal("0"))
    _legacy_sol: Mapped[Decimal] = mapped_column("sol", Numeric(20, 8), default=Decimal("0"))
    _legacy_doge: Mapped[Decimal] = mapped_column("doge", Numeric(20, 8), default=Decimal("0"))
    _legacy_matic: Mapped[Decimal] = mapped_column("matic", Numeric(20, 8), default=Decimal("0"))
    _legacy_usd: Mapped[Decimal] = mapped_column("usd", Numeric(20, 8), default=Decimal("0"))
    _legacy_cash_toman: Mapped[Decimal] = mapped_column("cash_toman", Numeric(20, 2), default=Decimal("0"))
    car_toman: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    _legacy_car_count: Mapped[int] = mapped_column("car_count", default=0)
    sanjeh_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # last Sanjeh fetch outcome: 'ok' | 'rejected' | 'failed'; NULL (rows before 0004) = treated as connected
    sanjeh_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mcp_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    car_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(back_populates="user")
    debts: Mapped[list["Debt"]] = relationship(back_populates="user")
    monthly_expenses: Mapped[list["MonthlyExpense"]] = relationship(back_populates="user")
    spend_categories: Mapped[list["SpendCategory"]] = relationship(back_populates="user")
    daily_spends: Mapped[list["DailySpend"]] = relationship(back_populates="user")
    push_tokens: Mapped[list["PushDeviceToken"]] = relationship(back_populates="user")
    holdings: Mapped[dict[str, "Holding"]] = relationship(
        back_populates="user",
        collection_class=attribute_keyed_dict("asset_key"),
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def get_holding(self, key: str):
        row = self.holdings.get(key)
        qty = Decimal(row.quantity) if row is not None else Decimal("0")
        return int(qty) if key in INT_HOLDING_KEYS else qty

    def set_holding(self, key: str, value) -> None:
        if key not in HOLDING_KEYS:
            raise KeyError(key)
        qty = Decimal(value or 0)
        row = self.holdings.get(key)
        if row is None:
            self.holdings[key] = Holding(asset_key=key, quantity=qty)
        else:
            row.quantity = qty
        # Transition: keep the legacy column in sync so a rollback still shows current values.
        setattr(self, f"_legacy_{key}", int(qty) if key in INT_HOLDING_KEYS else qty)


HOLDING_KEYS: tuple[str, ...] = ('gold_grams', 'coin_emami', 'coin_bahar', 'coin_half', 'coin_quarter', 'coin_gram', 'silver_grams', 'btc', 'ada', 'eth', 'sol', 'doge', 'matic', 'usd', 'cash_toman', 'car_count')
INT_HOLDING_KEYS = frozenset({"car_count"})


def _holding_property(key: str) -> property:
    return property(lambda self: self.get_holding(key), lambda self, v: self.set_holding(key, v))


for _key in HOLDING_KEYS:
    setattr(User, _key, _holding_property(_key))


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "asset_key", name="uq_holdings_user_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    asset_key: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="holdings")


class PushDeviceToken(Base):
    __tablename__ = "push_device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(16), default="web")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="push_tokens")


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


class AdminAuditLog(Base):
    """Append-only log of destructive admin actions (e.g. batch user delete)."""

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_username: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    targets_json: Mapped[str] = mapped_column(Text)
    counts_json: Mapped[str] = mapped_column(Text)
    backup_filename: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
