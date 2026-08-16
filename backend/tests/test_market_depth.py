import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.market.domain import CacheMetadata, HubPrice, MarketPriceLevel, OrderPageCache
from app.market.errors import EsiOrderPayloadError
from app.market.esi import EsiClient, parse_hub_order_page
from app.market.refresh import MarketCacheRefresher, merge_hub_prices


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
REGION_ID = 10_000_002
LOCATION_ID = 60_003_760


def _metadata() -> CacheMetadata:
    return CacheMetadata(
        etag=None,
        last_modified_at=NOW - timedelta(minutes=1),
        fresh_until=NOW + timedelta(minutes=5),
        fetched_at=NOW,
        requested_compatibility_date=date(2026, 8, 13),
        matched_compatibility_date=date(2026, 8, 13),
    )


def _order(**overrides):
    row = {
        "order_id": 123456789,
        "location_id": LOCATION_ID,
        "type_id": 34,
        "is_buy_order": False,
        "price": 5.0,
        "volume_remain": 10,
    }
    row.update(overrides)
    return row


def test_exhausted_order_is_ignored_before_other_order_fields_are_parsed() -> None:
    payload = [_order(volume_remain=0, price="not-a-price", type_id=None)]

    assert parse_hub_order_page(
        json.dumps(payload).encode(),
        location_id=LOCATION_ID,
        page=7,
    ) == ()


@pytest.mark.parametrize(
    "bad_value",
    [None, -1, True, "12", 1.5, 0.0],
)
def test_malformed_volume_reports_page_row_order_field_and_value(bad_value) -> None:
    payload = [_order(order_id=987654321, volume_remain=bad_value)]

    with pytest.raises(EsiOrderPayloadError) as raised:
        parse_hub_order_page(
            json.dumps(payload).encode(),
            location_id=LOCATION_ID,
            page=9,
        )

    error = raised.value
    assert error.page == 9
    assert error.row == 1
    assert error.order_id == 987654321
    assert error.field == "volume_remain"
    assert error.rejected_value == bad_value
    message = str(error)
    assert "page=9" in message
    assert "row=1" in message
    assert "order_id=987654321" in message
    assert "field=volume_remain" in message


def test_parser_caches_all_price_levels_and_merges_equal_prices() -> None:
    payload = [
        _order(is_buy_order=False, price=5.0, volume_remain=4),
        _order(order_id=2, is_buy_order=False, price=5.0, volume_remain=6),
        _order(order_id=3, is_buy_order=False, price=5.5, volume_remain=20),
        _order(order_id=4, is_buy_order=True, price=4.8, volume_remain=7),
        _order(order_id=5, is_buy_order=True, price=4.7, volume_remain=8),
        _order(
            order_id=6,
            is_buy_order=True,
            price=4.9,
            volume_remain=999,
            min_volume=100,
        ),
    ]

    quote = parse_hub_order_page(
        json.dumps(payload).encode(),
        location_id=LOCATION_ID,
    )[0]

    assert quote.sell_levels == (
        MarketPriceLevel(Decimal("5.0"), 10),
        MarketPriceLevel(Decimal("5.5"), 20),
    )
    assert quote.buy_levels == (
        MarketPriceLevel(Decimal("4.8"), 7),
        MarketPriceLevel(Decimal("4.7"), 8),
    )
    assert quote.best_sell_price == Decimal("5.0")
    assert quote.best_sell_volume == 10
    assert quote.best_buy_price == Decimal("4.8")
    assert quote.best_buy_volume == 7


def test_merge_hub_prices_preserves_depth_across_pages() -> None:
    page_one = OrderPageCache(
        REGION_ID,
        LOCATION_ID,
        1,
        2,
        _metadata(),
        (
            HubPrice(
                34,
                Decimal("4.8"),
                7,
                Decimal("5.0"),
                4,
                buy_levels=(MarketPriceLevel(Decimal("4.8"), 7),),
                sell_levels=(MarketPriceLevel(Decimal("5.0"), 4),),
            ),
        ),
    )
    page_two = OrderPageCache(
        REGION_ID,
        LOCATION_ID,
        2,
        2,
        _metadata(),
        (
            HubPrice(
                34,
                Decimal("4.8"),
                3,
                Decimal("5.2"),
                8,
                buy_levels=(
                    MarketPriceLevel(Decimal("4.8"), 3),
                    MarketPriceLevel(Decimal("4.7"), 9),
                ),
                sell_levels=(MarketPriceLevel(Decimal("5.2"), 8),),
            ),
        ),
    )

    quote = merge_hub_prices((page_one, page_two))[0]

    assert quote.buy_levels == (
        MarketPriceLevel(Decimal("4.8"), 10),
        MarketPriceLevel(Decimal("4.7"), 9),
    )
    assert quote.sell_levels == (
        MarketPriceLevel(Decimal("5.0"), 4),
        MarketPriceLevel(Decimal("5.2"), 8),
    )
    assert quote.best_buy_volume == 10


class _Repository:
    def __init__(self) -> None:
        self.published = None

    @contextmanager
    def acquire_read_snapshot(self):
        yield

    def get_resource_state(self, _resource_key):
        return None

    def get_order_pages(self, _region_id, _location_id):
        return {}

    def publish_order_snapshot(self, state, pages, prices):
        self.published = (state, tuple(pages), tuple(prices))


def test_fresh_order_snapshot_with_exhausted_rows_publishes_successfully() -> None:
    headers = {
        "Date": "Sun, 16 Aug 2026 12:00:00 GMT",
        "Expires": "Sun, 16 Aug 2026 12:05:00 GMT",
        "Last-Modified": "Sun, 16 Aug 2026 11:59:00 GMT",
        "X-Pages": "1",
        "X-Compatibility-Date": "2026-08-13",
        "X-Ratelimit-Remaining": "11998",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["page"] == "1"
        return httpx.Response(
            200,
            headers=headers,
            json=[
                _order(order_id=1, volume_remain=0),
                _order(order_id=2, volume_remain=15, price=5.0),
                _order(order_id=3, volume_remain=20, price=5.5),
            ],
        )

    repository = _Repository()
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    esi = EsiClient(
        http_client,
        base_url="https://esi.evetech.net",
        compatibility_date=date(2026, 8, 13),
        user_agent="TestIndustry/1.0",
        now=lambda: NOW,
    )
    try:
        result = MarketCacheRefresher(
            repository,
            esi,
            region_id=REGION_ID,
            location_id=LOCATION_ID,
        ).refresh_hub_orders()
    finally:
        http_client.close()

    assert result.status.value == "updated"
    assert result.row_count == 1
    assert repository.published is not None
    _state, pages, prices = repository.published
    assert len(pages) == 1
    assert prices[0].sell_levels == (
        MarketPriceLevel(Decimal("5.0"), 15),
        MarketPriceLevel(Decimal("5.5"), 20),
    )
