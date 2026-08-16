import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.market.domain import (
    CacheMetadata,
    HubPrice,
    OrderPageCache,
    ResourceState,
)
from app.market.errors import EsiResponseError
from app.market.esi import EsiClient
from app.market.refresh import (
    REFERENCE_PRICES_RESOURCE_KEY,
    MarketCacheRefresher,
    hub_orders_resource_key,
    merge_hub_prices,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _metadata(
    *,
    fresh: bool = False,
    etag: str | None = None,
    compatibility_date: date = date(2026, 8, 13),
) -> CacheMetadata:
    return CacheMetadata(
        etag=etag,
        last_modified_at=NOW - timedelta(minutes=5),
        fresh_until=NOW + timedelta(minutes=5) if fresh else NOW - timedelta(seconds=1),
        fetched_at=NOW - timedelta(minutes=5),
        requested_compatibility_date=compatibility_date,
        matched_compatibility_date=compatibility_date,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.states: dict[str, ResourceState] = {}
        self.pages: dict[int, OrderPageCache] = {}
        self.published_orders = None
        self.reference_prices = None
        self.system_indices = None
        self.read_snapshot_active = False

    @contextmanager
    def acquire_read_snapshot(self):
        self.read_snapshot_active = True
        try:
            yield
        finally:
            self.read_snapshot_active = False

    def get_resource_state(self, resource_key):
        return self.states.get(resource_key)

    def get_order_pages(self, _region_id, _location_id):
        return self.pages

    def save_resource_state(self, state):
        self.states[state.resource_key] = state

    def publish_order_snapshot(self, state, pages, prices):
        self.states[state.resource_key] = state
        self.pages = {page.page: page for page in pages}
        self.published_orders = (tuple(pages), tuple(prices))

    def publish_reference_prices(self, state, prices):
        self.states[state.resource_key] = state
        self.reference_prices = tuple(prices)

    def publish_system_cost_indices(self, state, indices):
        self.states[state.resource_key] = state
        self.system_indices = tuple(indices)

    def load_hub_prices(self, *_args, **_kwargs):
        return {}

    def load_reference_prices(self, *_args, **_kwargs):
        return {}

    def load_system_cost_indices(self, *_args, **_kwargs):
        return {}


def _esi(handler) -> tuple[EsiClient, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        EsiClient(
            client,
            base_url="https://esi.evetech.net",
            compatibility_date=date(2026, 8, 13),
            user_agent="TestIndustry/1.0",
            now=lambda: NOW,
        ),
        client,
    )


def _headers(page_count: int = 1, etag: str = '"v1"') -> dict[str, str]:
    return {
        "Date": "Fri, 14 Aug 2026 12:00:00 GMT",
        "Expires": "Fri, 14 Aug 2026 12:05:00 GMT",
        "Last-Modified": "Fri, 14 Aug 2026 11:59:00 GMT",
        "ETag": etag,
        "X-Pages": str(page_count),
        "X-Compatibility-Date": "2026-08-13",
        "X-Ratelimit-Remaining": "11998",
    }


def test_fresh_reference_cache_is_noop_without_http() -> None:
    repository = FakeRepository()
    repository.states[REFERENCE_PRICES_RESOURCE_KEY] = ResourceState(
        REFERENCE_PRICES_RESOURCE_KEY,
        _metadata(fresh=True),
        42,
    )
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    esi, client = _esi(handler)
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_reference_prices()
    finally:
        client.close()

    assert result.status.value == "fresh"
    assert result.row_count == 42
    assert calls == 0


def test_refresh_releases_database_read_snapshot_before_http() -> None:
    repository = FakeRepository()

    def handler(_request):
        assert repository.read_snapshot_active is False
        return httpx.Response(200, headers=_headers(), json=[])

    esi, client = _esi(handler)
    try:
        MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_reference_prices()
    finally:
        client.close()


def test_fresh_cache_from_an_old_compatibility_date_is_refreshed() -> None:
    repository = FakeRepository()
    repository.states[REFERENCE_PRICES_RESOURCE_KEY] = ResourceState(
        REFERENCE_PRICES_RESOURCE_KEY,
        _metadata(
            fresh=True,
            etag='"old-contract"',
            compatibility_date=date(2026, 8, 12),
        ),
        42,
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert "If-None-Match" not in request.headers
        return httpx.Response(200, headers=_headers(), json=[])

    esi, client = _esi(handler)
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_reference_prices()
    finally:
        client.close()

    assert calls == 1
    assert result.status.value == "updated"


def test_failed_second_order_page_does_not_publish_partial_snapshot() -> None:
    repository = FakeRepository()
    resource_key = hub_orders_resource_key(10_000_002, 60_003_760)
    repository.states[resource_key] = ResourceState(
        resource_key,
        _metadata(etag=None),
        1,
    )
    for page_number in (1, 2):
        repository.pages[page_number] = OrderPageCache(
            10_000_002,
            60_003_760,
            page_number,
            2,
            _metadata(etag=f'"old-{page_number}"'),
            (HubPrice(34, Decimal("5.00"), 10, None, None),),
        )
    prior_states = dict(repository.states)
    prior_pages = dict(repository.pages)

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, headers=_headers(2), json=[])
        return httpx.Response(503, headers={"Expires": _headers()["Expires"]})

    esi, client = _esi(handler)
    try:
        with pytest.raises(EsiResponseError):
            MarketCacheRefresher(
                repository,
                esi,
                region_id=10_000_002,
                location_id=60_003_760,
            ).refresh_hub_orders()
    finally:
        client.close()

    assert repository.published_orders is None
    assert repository.states == prior_states
    assert repository.pages == prior_pages


def test_order_refresh_merges_pages_and_drops_pages_after_count_shrinks() -> None:
    repository = FakeRepository()
    stale_key = hub_orders_resource_key(10_000_002, 60_003_760)
    repository.states[stale_key] = ResourceState(
        stale_key,
        _metadata(),
        1,
    )
    repository.pages[2] = OrderPageCache(
        region_id=10_000_002,
        location_id=60_003_760,
        page=2,
        page_count=2,
        metadata=_metadata(etag='"old-page-2"'),
        quotes=(HubPrice(999, Decimal("1"), 1, None, None),),
    )
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 8,
        },
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": False,
            "price": 5.25,
            "volume_remain": 9,
        },
    ]

    esi, client = _esi(
        lambda _request: httpx.Response(
            200,
            headers=_headers(1),
            content=json.dumps(payload).encode(),
        )
    )
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_hub_orders()
    finally:
        client.close()

    assert result.status.value == "updated"
    assert set(repository.pages) == {1}
    prices = repository.published_orders[1]
    assert prices == (
        HubPrice(34, Decimal("5.1"), 8, Decimal("5.25"), 9),
    )


def test_final_order_page_can_publish_with_no_remaining_rate_budget() -> None:
    repository = FakeRepository()
    headers = _headers(1)
    headers["X-Ratelimit-Remaining"] = "0"
    esi, client = _esi(
        lambda _request: httpx.Response(200, headers=headers, json=[])
    )
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_hub_orders()
    finally:
        client.close()

    assert result.status.value == "updated"
    assert repository.published_orders == ((repository.pages[1],), ())


def test_order_snapshot_expires_with_its_earliest_page() -> None:
    repository = FakeRepository()

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        headers = _headers(2, etag=f'"page-{page}"')
        if page == 2:
            headers["Expires"] = "Fri, 14 Aug 2026 12:03:00 GMT"
        return httpx.Response(200, headers=headers, json=[])

    esi, client = _esi(handler)
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=10_000_002,
            location_id=60_003_760,
        ).refresh_hub_orders()
    finally:
        client.close()

    assert result.fresh_until == NOW + timedelta(minutes=3)


def test_merge_hub_prices_uses_best_side_and_sums_tied_volume() -> None:
    first = OrderPageCache(
        10_000_002,
        60_003_760,
        1,
        2,
        _metadata(),
        (HubPrice(34, Decimal("5.1"), 10, Decimal("5.3"), 20),),
    )
    second = OrderPageCache(
        10_000_002,
        60_003_760,
        2,
        2,
        _metadata(),
        (HubPrice(34, Decimal("5.1"), 15, Decimal("5.2"), 30),),
    )

    assert merge_hub_prices((first, second)) == (
        HubPrice(34, Decimal("5.1"), 25, Decimal("5.2"), 30),
    )
