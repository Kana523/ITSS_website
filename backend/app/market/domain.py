from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class HubPrice:
    """Best sell and best unrestricted (min-volume 1) buy price levels."""

    type_id: int
    best_buy_price: Decimal | None
    best_buy_volume: int | None
    best_sell_price: Decimal | None
    best_sell_volume: int | None


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
