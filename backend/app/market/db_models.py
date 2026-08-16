from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class EsiCacheState(Base):
    __tablename__ = "esi_cache_states"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="row_count_non_negative"),
    )

    resource_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    fresh_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_compatibility_date: Mapped[date] = mapped_column(Date)
    matched_compatibility_date: Mapped[date | None] = mapped_column(Date)
    row_count: Mapped[int] = mapped_column(BigInteger)


class MarketOrderPageCache(Base):
    __tablename__ = "market_order_page_cache"
    __table_args__ = (
        CheckConstraint("region_id > 0", name="region_id_positive"),
        CheckConstraint("location_id > 0", name="location_id_positive"),
        CheckConstraint("page > 0", name="page_positive"),
        CheckConstraint("page_count > 0", name="page_count_positive"),
    )

    region_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_count: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    fresh_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_compatibility_date: Mapped[date] = mapped_column(Date)
    matched_compatibility_date: Mapped[date | None] = mapped_column(Date)
    page_quotes: Mapped[list[dict]] = mapped_column(JSONB)


class MarketHubPrice(Base):
    __tablename__ = "market_hub_prices"
    __table_args__ = (
        CheckConstraint("region_id > 0", name="region_id_positive"),
        CheckConstraint("location_id > 0", name="location_id_positive"),
        CheckConstraint("type_id > 0", name="type_id_positive"),
        CheckConstraint(
            "best_buy_price IS NULL OR best_buy_price > 0",
            name="best_buy_price_positive",
        ),
        CheckConstraint(
            "best_sell_price IS NULL OR best_sell_price > 0",
            name="best_sell_price_positive",
        ),
        CheckConstraint(
            "best_buy_volume IS NULL OR best_buy_volume > 0",
            name="best_buy_volume_positive",
        ),
        CheckConstraint(
            "best_sell_volume IS NULL OR best_sell_volume > 0",
            name="best_sell_volume_positive",
        ),
    )

    region_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    best_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    best_buy_volume: Mapped[int | None] = mapped_column(BigInteger)
    best_sell_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    best_sell_volume: Mapped[int | None] = mapped_column(BigInteger)


class MarketReferencePrice(Base):
    __tablename__ = "market_reference_prices"
    __table_args__ = (
        CheckConstraint("type_id > 0", name="type_id_positive"),
        CheckConstraint(
            "adjusted_price IS NULL OR adjusted_price >= 0",
            name="adjusted_price_non_negative",
        ),
        CheckConstraint(
            "average_price IS NULL OR average_price >= 0",
            name="average_price_non_negative",
        ),
    )

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adjusted_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 20))
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 20))


class IndustrySystemCostIndex(Base):
    __tablename__ = "industry_system_cost_indices"
    __table_args__ = (
        CheckConstraint("solar_system_id > 0", name="solar_system_id_positive"),
        CheckConstraint("cost_index >= 0", name="cost_index_non_negative"),
    )

    solar_system_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity: Mapped[str] = mapped_column(String(64), primary_key=True)
    cost_index: Mapped[Decimal] = mapped_column(Numeric(38, 20))
