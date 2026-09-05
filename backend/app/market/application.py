from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.config import Settings
from app.market.refresh import (
    SYSTEM_COST_INDICES_RESOURCE_KEY,
    hub_orders_resource_key,
)
from app.market.repository import MarketCacheRepository


class JitaSnapshotStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class JitaSnapshotView:
    region_id: int
    location_id: int
    location_name: str
    status: JitaSnapshotStatus
    fetched_at: datetime | None
    fresh_until: datetime | None
    age_minutes: int | None
    row_count: int


@dataclass(frozen=True, slots=True)
class IndustryIndexSnapshotView:
    solar_system_id: int
    activity: str
    cost_index: Decimal | None
    status: JitaSnapshotStatus
    fetched_at: datetime | None
    fresh_until: datetime | None
    age_minutes: int | None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("market clock must return an aware datetime")
    return value.astimezone(UTC)


class MarketApplicationService:
    """Expose read-only Jita snapshot status to the public API."""

    def __init__(
        self,
        repository: MarketCacheRepository,
        settings: Settings,
        *,
        now=None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def resource_key(self) -> str:
        return hub_orders_resource_key(
            self._settings.market_region_id,
            self._settings.market_location_id,
        )

    def jita_status(self) -> JitaSnapshotView:
        with self._repository.acquire_read_snapshot():
            state = self._repository.get_resource_state(self.resource_key)

        if state is None:
            return JitaSnapshotView(
                region_id=self._settings.market_region_id,
                location_id=self._settings.market_location_id,
                location_name=self._settings.market_location_name,
                status=JitaSnapshotStatus.UNAVAILABLE,
                fetched_at=None,
                fresh_until=None,
                age_minutes=None,
                row_count=0,
            )

        now = _aware_utc(self._now())
        fetched_at = _aware_utc(state.metadata.fetched_at)
        fresh_until = _aware_utc(state.metadata.fresh_until)
        age_seconds = max(0, int((now - fetched_at).total_seconds()))
        compatibility_ok = (
            state.metadata.requested_compatibility_date
            == self._settings.esi_compatibility_date
            and state.metadata.matched_compatibility_date
            in (None, self._settings.esi_compatibility_date)
        )
        snapshot_status = (
            JitaSnapshotStatus.FRESH
            if compatibility_ok and fresh_until > now
            else JitaSnapshotStatus.STALE
        )
        return JitaSnapshotView(
            region_id=self._settings.market_region_id,
            location_id=self._settings.market_location_id,
            location_name=self._settings.market_location_name,
            status=snapshot_status,
            fetched_at=fetched_at,
            fresh_until=fresh_until,
            age_minutes=age_seconds // 60,
            row_count=state.row_count,
        )

    def system_cost_index(
        self,
        solar_system_id: int,
        activity: str,
    ) -> IndustryIndexSnapshotView:
        with self._repository.acquire_read_snapshot():
            state = self._repository.get_resource_state(
                SYSTEM_COST_INDICES_RESOURCE_KEY
            )
            index = self._repository.load_system_cost_indices(
                solar_system_id,
                (activity,),
            ).get(activity)

        if state is None or index is None:
            return IndustryIndexSnapshotView(
                solar_system_id=solar_system_id,
                activity=activity,
                cost_index=None,
                status=JitaSnapshotStatus.UNAVAILABLE,
                fetched_at=None,
                fresh_until=None,
                age_minutes=None,
            )

        now = _aware_utc(self._now())
        fetched_at = _aware_utc(state.metadata.fetched_at)
        fresh_until = _aware_utc(state.metadata.fresh_until)
        age_seconds = max(0, int((now - fetched_at).total_seconds()))
        compatibility_ok = (
            state.metadata.requested_compatibility_date
            == self._settings.esi_compatibility_date
            and state.metadata.matched_compatibility_date
            in (None, self._settings.esi_compatibility_date)
        )
        snapshot_status = (
            JitaSnapshotStatus.FRESH
            if compatibility_ok and fresh_until > now
            else JitaSnapshotStatus.STALE
        )
        return IndustryIndexSnapshotView(
            solar_system_id=solar_system_id,
            activity=activity,
            cost_index=index.cost_index,
            status=snapshot_status,
            fetched_at=fetched_at,
            fresh_until=fresh_until,
            age_minutes=age_seconds // 60,
        )
