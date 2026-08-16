from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class RefreshStatus(StrEnum):
    FRESH = "fresh"
    NOT_MODIFIED = "not_modified"
    UPDATED = "updated"


@dataclass(frozen=True, slots=True)
class CacheMetadata:
    etag: str | None
    last_modified_at: datetime | None
    fresh_until: datetime
    fetched_at: datetime
    requested_compatibility_date: date
    matched_compatibility_date: date | None


@dataclass(frozen=True, slots=True)
class ResourceState:
    resource_key: str
    metadata: CacheMetadata
    row_count: int


@dataclass(frozen=True, slots=True, order=True)
class MarketPriceLevel:
    """Aggregated executable volume at one exact market price."""

    price: Decimal
    volume: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.price, Decimal)
            or not self.price.is_finite()
            or self.price <= 0
        ):
            raise ValueError(
                "market price level price must be a positive finite Decimal"
            )
        if (
            isinstance(self.volume, bool)
            or not isinstance(self.volume, int)
            or self.volume <= 0
        ):
            raise ValueError(
                "market price level volume must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class HubPrice:
    """Hub quote plus executable depth.

    The best-price fields remain the compatibility surface used by older
    callers. Depth is intentionally excluded from dataclass equality so code
    and tests that compare legacy HubPrice values continue to behave exactly
    as before. Callers that care about depth inspect the explicit level fields.
    """

    type_id: int
    best_buy_price: Decimal | None
    best_buy_volume: int | None
    best_sell_price: Decimal | None
    best_sell_volume: int | None
    buy_levels: tuple[MarketPriceLevel, ...] = field(
        default=(),
        compare=False,
    )
    sell_levels: tuple[MarketPriceLevel, ...] = field(
        default=(),
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class ReferencePrice:
    type_id: int
    adjusted_price: Decimal | None
    average_price: Decimal | None


@dataclass(frozen=True, slots=True)
class SystemCostIndex:
    solar_system_id: int
    activity: str
    cost_index: Decimal


@dataclass(frozen=True, slots=True)
class OrderPageCache:
    region_id: int
    location_id: int
    page: int
    page_count: int
    metadata: CacheMetadata
    quotes: tuple[HubPrice, ...]


@dataclass(frozen=True, slots=True)
class RefreshResult:
    resource: str
    status: RefreshStatus
    row_count: int
    fresh_until: datetime
