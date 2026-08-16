from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.database.repositories.market import SqlAlchemyMarketCacheRepository
from app.market.db_models import MarketHubPrice as MarketHubPriceRow
from app.market.domain import (
    CacheMetadata,
    HubPrice,
    OrderPageCache,
    ReferencePrice,
    ResourceState,
    SystemCostIndex,
)
from app.market.refresh import (
    REFERENCE_PRICES_RESOURCE_KEY,
    SYSTEM_COST_INDICES_RESOURCE_KEY,
    hub_orders_resource_key,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _metadata(etag: str | None = '"v1"') -> CacheMetadata:
    return CacheMetadata(
        etag=etag,
        last_modified_at=NOW - timedelta(minutes=1),
        fresh_until=NOW + timedelta(minutes=5),
        fetched_at=NOW,
        requested_compatibility_date=date(2026, 8, 13),
        matched_compatibility_date=date(2026, 8, 13),
    )


@pytest.mark.integration
def test_repository_publishes_and_replaces_complete_market_snapshots(
    migrated_connection: Connection,
) -> None:
    session = Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    )
    repository = SqlAlchemyMarketCacheRepository(session)
    key = hub_orders_resource_key(10_000_002, 60_003_760)
    first_page = OrderPageCache(
        10_000_002,
        60_003_760,
        1,
        1,
        _metadata(),
        (
            HubPrice(34, Decimal("5.10"), 100, Decimal("5.20"), 200),
            HubPrice(35, Decimal("7.10"), 300, None, None),
        ),
    )
    repository.publish_order_snapshot(
        ResourceState(key, _metadata(None), 2),
        (first_page,),
        first_page.quotes,
    )

    with repository.acquire_read_snapshot():
        assert repository.get_resource_state(key).row_count == 2
        assert repository.load_hub_prices(
            {34, 35},
            region_id=10_000_002,
            location_id=60_003_760,
        ) == {
            34: HubPrice(34, Decimal("5.10"), 100, Decimal("5.20"), 200),
            35: HubPrice(35, Decimal("7.10"), 300, None, None),
        }

    replacement_page = OrderPageCache(
        10_000_002,
        60_003_760,
        1,
        1,
        _metadata('"v2"'),
        (HubPrice(34, Decimal("5.15"), 50, None, None),),
    )
    repository.publish_order_snapshot(
        ResourceState(key, _metadata(None), 1),
        (replacement_page,),
        replacement_page.quotes,
    )

    assert repository.load_hub_prices(
        {34, 35},
        region_id=10_000_002,
        location_id=60_003_760,
    ) == {
        34: HubPrice(34, Decimal("5.15"), 50, None, None)
    }
    assert set(repository.get_order_pages(10_000_002, 60_003_760)) == {1}
    session.close()


@pytest.mark.integration
def test_repository_reads_reference_prices_indices_and_snapshot_metadata(
    migrated_connection: Connection,
) -> None:
    session = Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    )
    repository = SqlAlchemyMarketCacheRepository(session)
    repository.publish_reference_prices(
        ResourceState(REFERENCE_PRICES_RESOURCE_KEY, _metadata(), 2),
        (
            ReferencePrice(
                34,
                Decimal("5.123456789"),
                Decimal("5.20"),
            ),
            ReferencePrice(35, Decimal("0"), Decimal("7.00")),
        ),
    )
    repository.publish_system_cost_indices(
        ResourceState(SYSTEM_COST_INDICES_RESOURCE_KEY, _metadata(), 2),
        (
            SystemCostIndex(30_000_142, "manufacturing", Decimal("0.0123")),
            SystemCostIndex(30_000_142, "reaction", Decimal("0.0042")),
        ),
    )

    assert repository.load_reference_prices({34, 35, 999}) == {
        34: ReferencePrice(
            34,
            Decimal("5.123456789"),
            Decimal("5.20"),
        ),
        35: ReferencePrice(35, Decimal("0"), Decimal("7.00")),
    }
    assert repository.load_system_cost_indices(
        30_000_142,
        {"manufacturing"},
    ) == {
        "manufacturing": SystemCostIndex(
            30_000_142,
            "manufacturing",
            Decimal("0.01230000000000000000"),
        )
    }
    state = repository.get_resource_state(REFERENCE_PRICES_RESOURCE_KEY)
    assert state.metadata.fetched_at == NOW
    assert state.metadata.fresh_until == NOW + timedelta(minutes=5)
    session.close()


@pytest.mark.integration
def test_invalid_replacement_rolls_back_and_keeps_prior_snapshot(
    migrated_connection: Connection,
) -> None:
    session = Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    )
    repository = SqlAlchemyMarketCacheRepository(session)
    key = hub_orders_resource_key(10_000_002, 60_003_760)
    page = OrderPageCache(
        10_000_002,
        60_003_760,
        1,
        1,
        _metadata(),
        (HubPrice(34, Decimal("5.10"), 10, None, None),),
    )
    repository.publish_order_snapshot(
        ResourceState(key, _metadata(None), 1),
        (page,),
        page.quotes,
    )

    with pytest.raises(Exception):
        repository.publish_order_snapshot(
            ResourceState(key, _metadata(None), 1),
            (page,),
            (HubPrice(34, Decimal("-1.00"), 10, None, None),),
        )

    assert migrated_connection.scalar(
        select(MarketHubPriceRow.best_buy_price).where(
            MarketHubPriceRow.region_id == 10_000_002,
            MarketHubPriceRow.location_id == 60_003_760,
            MarketHubPriceRow.type_id == 34,
        )
    ) == Decimal("5.10")
    session.close()
