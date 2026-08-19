from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import httpx

from app.config import Settings
from app.database.engine import engine
from app.database.repositories.market import market_refresh_lock
from app.market.domain import RefreshStatus
from app.market.errors import MarketRefreshInProgressError
from app.market.esi import EsiClient
from app.market.refresh import MarketCacheRefresher, hub_orders_resource_key
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
class JitaRefreshView:
    refresh_status: RefreshStatus
    snapshot: JitaSnapshotView


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("market clock must return an aware datetime")
    return value.astimezone(UTC)


def _validate_user_agent(value: str) -> str:
    normalized = value.strip()
    lowered = normalized.casefold()
    if lowered.startswith(("python/", "python-httpx/", "httpx/")):
        raise ValueError("ESI_USER_AGENT must be application-specific")
    if len(normalized) < 8 or "/" not in normalized:
        raise ValueError("ESI_USER_AGENT must identify the application and version")
    return normalized


class MarketApplicationService:
    """Expose Jita snapshot status and explicit on-demand refreshes.

    Nothing in this service schedules work. A refresh only happens when a caller
    invokes ``refresh_jita_prices``. The underlying refresher still honors ESI's
    ``fresh_until`` metadata, so repeated page reloads or button clicks while the
    current snapshot is fresh do not perform external ESI requests.
    """

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

    def refresh_jita_prices(self) -> JitaRefreshView:
        """Refresh Jita prices once if the cached ESI resource is stale.

        This deliberately has no force mode. If ESI says the current snapshot is
        still fresh, the refresher returns ``fresh`` without making HTTP calls.
        """
        user_agent = _validate_user_agent(self._settings.esi_user_agent)
        with market_refresh_lock(engine) as acquired:
            if not acquired:
                raise MarketRefreshInProgressError(
                    "Another market refresh is already running"
                )
            with httpx.Client(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=False,
            ) as http_client:
                esi = EsiClient(
                    http_client,
                    base_url=self._settings.esi_base_url,
                    compatibility_date=self._settings.esi_compatibility_date,
                    user_agent=user_agent,
                )
                result = MarketCacheRefresher(
                    self._repository,
                    esi,
                    region_id=self._settings.market_region_id,
                    location_id=self._settings.market_location_id,
                ).refresh_hub_orders()
        return JitaRefreshView(
            refresh_status=result.status,
            snapshot=self.jita_status(),
        )
