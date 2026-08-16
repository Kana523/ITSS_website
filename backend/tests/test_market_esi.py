import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.market.domain import CacheMetadata
from app.market.errors import EsiPayloadError, EsiRateLimitError
from app.market.esi import (
    EsiClient,
    parse_hub_order_page,
    parse_reference_prices,
    parse_system_cost_indices,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
HTTP_DATE = "Fri, 14 Aug 2026 12:00:00 GMT"
LAST_MODIFIED = "Fri, 14 Aug 2026 11:59:00 GMT"


def _client(
    handler,
    *,
    now=NOW,
) -> tuple[EsiClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        EsiClient(
            http_client,
            base_url="https://esi.evetech.net",
            compatibility_date=date(2026, 8, 13),
            user_agent="TestIndustry/1.0 (test@example.com)",
            now=lambda: now,
        ),
        http_client,
    )


def test_conditional_get_sends_identity_headers_and_uses_cache_control() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/markets/10000002/orders"
        assert request.url.params["page"] == "1"
        assert request.headers["User-Agent"].startswith("TestIndustry/1.0")
        assert request.headers["X-Compatibility-Date"] == "2026-08-13"
        assert "If-None-Match" not in request.headers
        return httpx.Response(
            200,
            headers={
                "Cache-Control": "public, max-age=300",
                "Date": HTTP_DATE,
                "ETag": '"orders-v1"',
                "Last-Modified": LAST_MODIFIED,
                "X-Pages": "2",
                "X-Compatibility-Date": "2026-08-13",
                "X-Ratelimit-Remaining": "11998",
            },
            json=[],
        )

    client, http_client = _client(handler)
    try:
        result = client.conditional_get(
            "/markets/10000002/orders",
            params={"order_type": "all", "page": 1},
        )
    finally:
        http_client.close()

    assert result.not_modified is False
    assert result.page_count == 2
    assert result.rate_limit_remaining == 11_998
    assert result.metadata.etag == '"orders-v1"'
    assert result.metadata.fresh_until == NOW + timedelta(minutes=5)
    assert result.metadata.last_modified_at == datetime(
        2026, 8, 14, 11, 59, tzinfo=UTC
    )


def test_shared_cache_max_age_takes_precedence() -> None:
    client, http_client = _client(
        lambda _request: httpx.Response(
            200,
            headers={
                "Cache-Control": "public, max-age=60, s-maxage=300",
                "Date": HTTP_DATE,
            },
            json=[],
        )
    )
    try:
        result = client.conditional_get("/markets/prices")
    finally:
        http_client.close()

    assert result.metadata.fresh_until == NOW + timedelta(minutes=5)


def test_conditional_get_reuses_etag_and_payload_metadata_on_304() -> None:
    cached = CacheMetadata(
        etag='"cached"',
        last_modified_at=NOW - timedelta(minutes=5),
        fresh_until=NOW - timedelta(seconds=1),
        fetched_at=NOW - timedelta(minutes=5),
        requested_compatibility_date=date(2026, 8, 13),
        matched_compatibility_date=date(2026, 8, 13),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"cached"'
        return httpx.Response(
            304,
            headers={
                "Expires": "Fri, 14 Aug 2026 12:05:00 GMT",
                "Date": HTTP_DATE,
            },
        )

    client, http_client = _client(handler)
    try:
        result = client.conditional_get("/markets/prices", cached=cached)
    finally:
        http_client.close()

    assert result.not_modified is True
    assert result.content is None
    assert result.metadata.etag == '"cached"'
    assert result.metadata.last_modified_at == cached.last_modified_at
    assert result.metadata.fresh_until == NOW + timedelta(minutes=5)


def test_conditional_get_does_not_revalidate_an_old_compatibility_date() -> None:
    cached = CacheMetadata(
        etag='"old-contract"',
        last_modified_at=NOW - timedelta(minutes=5),
        fresh_until=NOW - timedelta(seconds=1),
        fetched_at=NOW - timedelta(minutes=5),
        requested_compatibility_date=date(2026, 8, 12),
        matched_compatibility_date=date(2026, 8, 12),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "If-None-Match" not in request.headers
        return httpx.Response(
            200,
            headers={
                "Cache-Control": "max-age=300",
                "Date": HTTP_DATE,
                "ETag": '"new-contract"',
            },
            json=[],
        )

    client, http_client = _client(handler)
    try:
        result = client.conditional_get("/markets/prices", cached=cached)
    finally:
        http_client.close()

    assert result.metadata.etag == '"new-contract"'
    assert result.metadata.last_modified_at is None


def test_conditional_get_honors_retry_after() -> None:
    client, http_client = _client(
        lambda _request: httpx.Response(
            429,
            headers={"Retry-After": "17"},
        )
    )
    try:
        with pytest.raises(EsiRateLimitError) as raised:
            client.conditional_get("/markets/prices")
    finally:
        http_client.close()
    assert raised.value.retry_after_seconds == 17


def test_order_parser_filters_location_and_merges_equal_best_volume() -> None:
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 10,
        },
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 15,
        },
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": False,
            "price": 5.25,
            "volume_remain": 20,
        },
        {
            "location_id": 60_000_001,
            "type_id": 34,
            "is_buy_order": False,
            "price": 1.00,
            "volume_remain": 999,
        },
    ]

    quotes = parse_hub_order_page(
        json.dumps(payload).encode(),
        location_id=60_003_760,
    )

    assert quotes[0].best_buy_price == Decimal("5.1")
    assert quotes[0].best_buy_volume == 25
    assert quotes[0].best_sell_price == Decimal("5.25")
    assert quotes[0].best_sell_volume == 20


def test_order_parser_uses_only_unrestricted_buy_orders() -> None:
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 6.00,
            "volume_remain": 1_000,
            "min_volume": 100,
        },
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.90,
            "volume_remain": 25,
            "min_volume": 1,
        },
    ]

    quotes = parse_hub_order_page(
        json.dumps(payload).encode(),
        location_id=60_003_760,
    )

    assert quotes[0].best_buy_price == Decimal("5.9")
    assert quotes[0].best_buy_volume == 25


def test_order_parser_defaults_missing_buy_min_volume_to_one() -> None:
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 10,
        }
    ]

    quotes = parse_hub_order_page(
        json.dumps(payload).encode(),
        location_id=60_003_760,
    )

    assert quotes[0].best_buy_price == Decimal("5.1")
    assert quotes[0].best_buy_volume == 10


@pytest.mark.parametrize("min_volume", [None, 0, -1, True, "1", 1.0])
def test_order_parser_rejects_invalid_buy_min_volume(min_volume) -> None:
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 10,
            "min_volume": min_volume,
        }
    ]

    with pytest.raises(EsiPayloadError, match="min_volume"):
        parse_hub_order_page(
            json.dumps(payload).encode(),
            location_id=60_003_760,
        )


def test_reference_and_system_parsers_preserve_decimal_values_and_nulls() -> None:
    prices = parse_reference_prices(
        b'[{"type_id":34,"adjusted_price":5.12},'
        b'{"type_id":35,"average_price":7.00}]'
    )
    indices = parse_system_cost_indices(
        b'[{"solar_system_id":30000142,"cost_indices":['
        b'{"activity":"manufacturing","cost_index":0.012345678901234567}]}]'
    )

    assert prices[0].adjusted_price == Decimal("5.12")
    assert prices[0].average_price is None
    assert prices[1].adjusted_price is None
    assert indices[0].cost_index == Decimal("0.012345678901234567")


def test_reference_parser_preserves_sub_cent_and_zero_values() -> None:
    prices = parse_reference_prices(
        b'[{"type_id":34,"adjusted_price":5.123456789},'
        b'{"type_id":35,"adjusted_price":0.0}]'
    )

    assert prices[0].adjusted_price == Decimal("5.123456789")
    assert prices[1].adjusted_price == Decimal("0.0")


def test_system_parser_rejects_duplicate_indices() -> None:
    with pytest.raises(EsiPayloadError, match="duplicate"):
        parse_system_cost_indices(
            b'[{"solar_system_id":30000142,"cost_indices":['
            b'{"activity":"manufacturing","cost_index":0.01},'
            b'{"activity":"manufacturing","cost_index":0.02}]}]'
        )


def test_order_parser_rejects_tied_volume_overflow() -> None:
    payload = [
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 9_223_372_036_854_775_807,
        },
        {
            "location_id": 60_003_760,
            "type_id": 34,
            "is_buy_order": True,
            "price": 5.10,
            "volume_remain": 1,
        },
    ]

    with pytest.raises(EsiPayloadError, match="BIGINT"):
        parse_hub_order_page(
            json.dumps(payload).encode(),
            location_id=60_003_760,
        )
