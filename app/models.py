from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    gold_grams: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
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
    car_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(back_populates="user")


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
