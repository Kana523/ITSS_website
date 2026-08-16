from collections.abc import Collection, Iterator
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.market.db_models import (
    EsiCacheState,
    IndustrySystemCostIndex as IndustrySystemCostIndexRow,
    MarketHubPrice as MarketHubPriceRow,
    MarketOrderPageCache as MarketOrderPageCacheRow,
    MarketReferencePrice as MarketReferencePriceRow,
)
from app.market.domain import (
    CacheMetadata,
    HubPrice,
    MarketPriceLevel,
    OrderPageCache,
    ReferencePrice,
    ResourceState,
    SystemCostIndex,
)


MARKET_REFRESH_ADVISORY_LOCK_ID = 4_607_714_803_391_920_212
MARKET_PUBLICATION_ADVISORY_LOCK_ID = 4_607_714_803_391_920_213


def _metadata(row) -> CacheMetadata:
    return CacheMetadata(
        etag=row.etag,
        last_modified_at=row.last_modified_at,
        fresh_until=row.fresh_until,
        fetched_at=row.fetched_at,
        requested_compatibility_date=row.requested_compatibility_date,
        matched_compatibility_date=row.matched_compatibility_date,
    )


def _state_values(state: ResourceState) -> dict:
    return {
        "resource_key": state.resource_key,
        "etag": state.metadata.etag,
        "last_modified_at": state.metadata.last_modified_at,
        "fresh_until": state.metadata.fresh_until,
        "fetched_at": state.metadata.fetched_at,
        "requested_compatibility_date": state.metadata.requested_compatibility_date,
        "matched_compatibility_date": state.metadata.matched_compatibility_date,
        "row_count": state.row_count,
    }


def _level_values(levels: tuple[MarketPriceLevel, ...]) -> list[dict]:
    return [
        {"price": str(level.price), "volume": level.volume}
        for level in levels
    ]


def _levels(rows: list[dict] | None) -> tuple[MarketPriceLevel, ...]:
    return tuple(
        MarketPriceLevel(
            price=Decimal(row["price"]),
            volume=int(row["volume"]),
        )
        for row in (rows or [])
    )


def _page_quote_values(quote: HubPrice) -> dict:
    return {
        "type_id": quote.type_id,
        "best_buy_price": (
            str(quote.best_buy_price) if quote.best_buy_price is not None else None
        ),
        "best_buy_volume": quote.best_buy_volume,
        "best_sell_price": (
            str(quote.best_sell_price) if quote.best_sell_price is not None else None
        ),
        "best_sell_volume": quote.best_sell_volume,
        "buy_levels": _level_values(quote.buy_levels),
        "sell_levels": _level_values(quote.sell_levels),
    }


def _page_quote(row: dict) -> HubPrice:
    return HubPrice(
        type_id=int(row["type_id"]),
        best_buy_price=(
            Decimal(row["best_buy_price"])
            if row["best_buy_price"] is not None
            else None
        ),
        best_buy_volume=row["best_buy_volume"],
        best_sell_price=(
            Decimal(row["best_sell_price"])
            if row["best_sell_price"] is not None
            else None
        ),
        best_sell_volume=row["best_sell_volume"],
        buy_levels=_levels(row.get("buy_levels")),
        sell_levels=_levels(row.get("sell_levels")),
    )


class SqlAlchemyMarketCacheRepository:
    """Persist complete public-ESI cache snapshots in short transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def acquire_read_snapshot(self) -> Iterator[None]:
        """Prevent a market publication between related read statements."""
        owns_transaction = not self._session.in_transaction()
        try:
            self._session.execute(
                text("SELECT pg_advisory_xact_lock_shared(:lock_id)"),
                {"lock_id": MARKET_PUBLICATION_ADVISORY_LOCK_ID},
            )
            yield
        finally:
            if owns_transaction:
                self._session.rollback()

    def _lock_publication(self) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": MARKET_PUBLICATION_ADVISORY_LOCK_ID},
        )

    def get_resource_state(self, resource_key: str) -> ResourceState | None:
        row = self._session.get(EsiCacheState, resource_key)
        if row is None:
            return None
        return ResourceState(
            resource_key=row.resource_key,
            metadata=_metadata(row),
            row_count=row.row_count,
        )

    def get_order_pages(
        self,
        region_id: int,
        location_id: int,
    ) -> dict[int, OrderPageCache]:
        rows = self._session.scalars(
            select(MarketOrderPageCacheRow)
            .where(
                MarketOrderPageCacheRow.region_id == region_id,
                MarketOrderPageCacheRow.location_id == location_id,
            )
            .order_by(MarketOrderPageCacheRow.page)
        )
        return {
            row.page: OrderPageCache(
                region_id=row.region_id,
                location_id=row.location_id,
                page=row.page,
                page_count=row.page_count,
                metadata=_metadata(row),
                quotes=tuple(_page_quote(quote) for quote in row.page_quotes),
            )
            for row in rows
        }

    def _upsert_state(self, state: ResourceState) -> None:
        values = _state_values(state)
        statement = postgresql_insert(EsiCacheState).values(values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[EsiCacheState.resource_key],
                set_={
                    key: value
                    for key, value in values.items()
                    if key != "resource_key"
                },
            )
        )

    def _commit(self) -> None:
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def save_resource_state(self, state: ResourceState) -> None:
        try:
            self._lock_publication()
            self._upsert_state(state)
            self._commit()
        except Exception:
            self._session.rollback()
            raise

    def publish_order_snapshot(
        self,
        state: ResourceState,
        pages: Collection[OrderPageCache],
        prices: Collection[HubPrice],
    ) -> None:
        page_tuple = tuple(pages)
        if not page_tuple:
            raise ValueError("An order snapshot must contain at least one page")
        region_id = page_tuple[0].region_id
        location_id = page_tuple[0].location_id
        if any(
            page.region_id != region_id or page.location_id != location_id
            for page in page_tuple
        ):
            raise ValueError("Order snapshot pages must share a market location")

        try:
            self._lock_publication()
            self._session.execute(
                delete(MarketOrderPageCacheRow).where(
                    MarketOrderPageCacheRow.region_id == region_id,
                    MarketOrderPageCacheRow.location_id == location_id,
                )
            )
            self._session.execute(
                insert(MarketOrderPageCacheRow),
                [
                    {
                        "region_id": page.region_id,
                        "location_id": page.location_id,
                        "page": page.page,
                        "page_count": page.page_count,
                        "etag": page.metadata.etag,
                        "last_modified_at": page.metadata.last_modified_at,
                        "fresh_until": page.metadata.fresh_until,
                        "fetched_at": page.metadata.fetched_at,
                        "requested_compatibility_date": (
                            page.metadata.requested_compatibility_date
                        ),
                        "matched_compatibility_date": (
                            page.metadata.matched_compatibility_date
                        ),
                        "page_quotes": [
                            _page_quote_values(quote) for quote in page.quotes
                        ],
                    }
                    for page in page_tuple
                ],
            )
            self._session.execute(
                delete(MarketHubPriceRow).where(
                    MarketHubPriceRow.region_id == region_id,
                    MarketHubPriceRow.location_id == location_id,
                )
            )
            price_values = [
                {
                    "region_id": region_id,
                    "location_id": location_id,
                    "type_id": price.type_id,
                    "best_buy_price": price.best_buy_price,
                    "best_buy_volume": price.best_buy_volume,
                    "best_sell_price": price.best_sell_price,
                    "best_sell_volume": price.best_sell_volume,
                    "buy_levels": _level_values(price.buy_levels),
                    "sell_levels": _level_values(price.sell_levels),
                }
                for price in prices
            ]
            if price_values:
                self._session.execute(insert(MarketHubPriceRow), price_values)
            self._upsert_state(state)
            self._commit()
        except Exception:
            self._session.rollback()
            raise

    def publish_reference_prices(
        self,
        state: ResourceState,
        prices: Collection[ReferencePrice],
    ) -> None:
        try:
            self._lock_publication()
            self._session.execute(delete(MarketReferencePriceRow))
            values = [
                {
                    "type_id": price.type_id,
                    "adjusted_price": price.adjusted_price,
                    "average_price": price.average_price,
                }
                for price in prices
            ]
            if values:
                self._session.execute(insert(MarketReferencePriceRow), values)
            self._upsert_state(state)
            self._commit()
        except Exception:
            self._session.rollback()
            raise

    def publish_system_cost_indices(
        self,
        state: ResourceState,
        indices: Collection[SystemCostIndex],
    ) -> None:
        try:
            self._lock_publication()
            self._session.execute(delete(IndustrySystemCostIndexRow))
            values = [
                {
                    "solar_system_id": index.solar_system_id,
                    "activity": index.activity,
                    "cost_index": index.cost_index,
                }
                for index in indices
            ]
            if values:
                self._session.execute(insert(IndustrySystemCostIndexRow), values)
            self._upsert_state(state)
            self._commit()
        except Exception:
            self._session.rollback()
            raise

    def load_hub_prices(
        self,
        type_ids: Collection[int],
        *,
        region_id: int,
        location_id: int,
    ) -> dict[int, HubPrice]:
        requested_ids = sorted(set(type_ids))
        if not requested_ids:
            return {}
        rows = self._session.scalars(
            select(MarketHubPriceRow).where(
                MarketHubPriceRow.region_id == region_id,
                MarketHubPriceRow.location_id == location_id,
                MarketHubPriceRow.type_id.in_(requested_ids),
            )
        )
        return {
            row.type_id: HubPrice(
                type_id=row.type_id,
                best_buy_price=row.best_buy_price,
                best_buy_volume=row.best_buy_volume,
                best_sell_price=row.best_sell_price,
                best_sell_volume=row.best_sell_volume,
                buy_levels=_levels(row.buy_levels),
                sell_levels=_levels(row.sell_levels),
            )
            for row in rows
        }

    def load_reference_prices(
        self,
        type_ids: Collection[int],
    ) -> dict[int, ReferencePrice]:
        requested_ids = sorted(set(type_ids))
        if not requested_ids:
            return {}
        rows = self._session.scalars(
            select(MarketReferencePriceRow).where(
                MarketReferencePriceRow.type_id.in_(requested_ids)
            )
        )
        return {
            row.type_id: ReferencePrice(
                type_id=row.type_id,
                adjusted_price=row.adjusted_price,
                average_price=row.average_price,
            )
            for row in rows
        }

    def load_system_cost_indices(
        self,
        solar_system_id: int,
        activities: Collection[str],
    ) -> dict[str, SystemCostIndex]:
        requested_activities = sorted(set(activities))
        if not requested_activities:
            return {}
        rows = self._session.scalars(
            select(IndustrySystemCostIndexRow).where(
                IndustrySystemCostIndexRow.solar_system_id == solar_system_id,
                IndustrySystemCostIndexRow.activity.in_(requested_activities),
            )
        )
        return {
            row.activity: SystemCostIndex(
                solar_system_id=row.solar_system_id,
                activity=row.activity,
                cost_index=row.cost_index,
            )
            for row in rows
        }


@contextmanager
def market_refresh_lock(engine: Engine) -> Iterator[bool]:
    """Hold one PostgreSQL session advisory lock across external refresh I/O."""
    with engine.connect() as connection:
        acquired = bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": MARKET_REFRESH_ADVISORY_LOCK_ID},
            )
        )
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": MARKET_REFRESH_ADVISORY_LOCK_ID},
                )
                connection.commit()
