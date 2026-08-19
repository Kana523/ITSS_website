from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from app.api.dependencies import get_market_application_service
from app.config import get_settings
from app.market.application import (
    JitaRefreshView,
    JitaSnapshotStatus,
    JitaSnapshotView,
    MarketApplicationService,
)
from app.market.domain import (
    CacheMetadata,
    HubPrice,
    OrderPageCache,
    RefreshStatus,
    ResourceState,
)
from app.market.esi import EsiClient
from app.market.refresh import MarketCacheRefresher, hub_orders_resource_key
from app.main import create_app


NOW = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
REGION_ID = 10_000_002
LOCATION_ID = 60_003_760
RESOURCE_KEY = hub_orders_resource_key(REGION_ID, LOCATION_ID)


class FakeSettings:
    market_region_id = REGION_ID
    market_location_id = LOCATION_ID
    market_location_name = "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
    esi_compatibility_date = date(2026, 8, 13)
    esi_user_agent = "ITS-S-Test/1.0"
    esi_base_url = "https://esi.evetech.net"


class FakeRepository:
    def __init__(self, state: ResourceState | None = None) -> None:
        self.state = state
        self.pages: dict[int, OrderPageCache] = {}

    @contextmanager
    def acquire_read_snapshot(self):
        yield

    def get_resource_state(self, resource_key: str):
        return self.state if resource_key == RESOURCE_KEY else None

    def get_order_pages(self, _region_id: int, _location_id: int):
        return self.pages

    def publish_order_snapshot(self, state, pages, _prices):
        self.state = state
        self.pages = {page.page: page for page in pages}


def _metadata(*, fresh: bool) -> CacheMetadata:
    return CacheMetadata(
        etag='"orders-v1"',
        last_modified_at=NOW - timedelta(minutes=4),
        fresh_until=(
            NOW + timedelta(minutes=1)
            if fresh
            else NOW - timedelta(minutes=1)
        ),
        fetched_at=NOW - timedelta(minutes=4, seconds=59),
        requested_compatibility_date=date(2026, 8, 13),
        matched_compatibility_date=date(2026, 8, 13),
    )


def test_market_status_reports_age_in_whole_minutes() -> None:
    repository = FakeRepository(
        ResourceState(RESOURCE_KEY, _metadata(fresh=True), 1234)
    )
    service = MarketApplicationService(
        repository,
        FakeSettings(),
        now=lambda: NOW,
    )

    status = service.jita_status()

    assert status.status == JitaSnapshotStatus.FRESH
    assert status.age_minutes == 4
    assert status.row_count == 1234
    assert status.location_id == LOCATION_ID


def test_market_status_reports_unavailable_without_snapshot() -> None:
    status = MarketApplicationService(
        FakeRepository(),
        FakeSettings(),
        now=lambda: NOW,
    ).jita_status()

    assert status.status == JitaSnapshotStatus.UNAVAILABLE
    assert status.age_minutes is None
    assert status.fetched_at is None
    assert status.row_count == 0


def test_fresh_jita_snapshot_makes_zero_esi_requests() -> None:
    repository = FakeRepository(
        ResourceState(RESOURCE_KEY, _metadata(fresh=True), 1)
    )
    repository.pages[1] = OrderPageCache(
        region_id=REGION_ID,
        location_id=LOCATION_ID,
        page=1,
        page_count=1,
        metadata=_metadata(fresh=True),
        quotes=(HubPrice(34, Decimal("5.00"), 10, None, None),),
    )
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        esi = EsiClient(
            client,
            base_url="https://esi.evetech.net",
            compatibility_date=date(2026, 8, 13),
            user_agent="ITS-S-Test/1.0",
            now=lambda: NOW,
        )
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=REGION_ID,
            location_id=LOCATION_ID,
        ).refresh_hub_orders()
    finally:
        client.close()

    assert result.status == RefreshStatus.FRESH
    assert calls == 0


class FakeMarketApplicationService:
    def __init__(self) -> None:
        self.refresh_calls = 0
        self.snapshot = JitaSnapshotView(
            region_id=REGION_ID,
            location_id=LOCATION_ID,
            location_name=FakeSettings.market_location_name,
            status=JitaSnapshotStatus.FRESH,
            fetched_at=NOW - timedelta(minutes=3),
            fresh_until=NOW + timedelta(minutes=2),
            age_minutes=3,
            row_count=987,
        )

    def jita_status(self) -> JitaSnapshotView:
        return self.snapshot

    def refresh_jita_prices(self) -> JitaRefreshView:
        self.refresh_calls += 1
        return JitaRefreshView(RefreshStatus.FRESH, self.snapshot)


def test_market_api_exposes_status_and_explicit_refresh() -> None:
    application = create_app(cors_origins=())
    fake_service = FakeMarketApplicationService()
    application.dependency_overrides[get_market_application_service] = (
        lambda: fake_service
    )

    with TestClient(application) as client:
        status_response = client.get("/api/market/jita/status")
        refresh_response = client.post("/api/market/jita/refresh")

    application.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert status_response.json()["age_minutes"] == 3
    assert status_response.json()["status"] == "fresh"
    assert refresh_response.status_code == 200
    assert refresh_response.json()["refresh_status"] == "fresh"
    assert refresh_response.json()["snapshot"]["row_count"] == 987
    assert fake_service.refresh_calls == 1


def test_market_frontend_refreshes_only_on_page_load_or_button() -> None:
    root = get_settings().model_config.get("env_file").parent.parent
    loader = (root.parent / "assets" / "js" / "industry.js").read_text(
        encoding="utf-8"
    )
    script = (root.parent / "assets" / "js" / "industry-market.js").read_text(
        encoding="utf-8"
    )

    assert "industry-market.js" in loader
    assert "/api/market/jita/refresh" in script
    assert "/api/market/jita/status" in script
    assert "Fetch new prices" in script
    assert 'button.addEventListener("click"' in script
    assert "refreshPrices();" in script
    assert "setInterval" not in script
    assert "setTimeout" not in script
