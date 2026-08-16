from collections.abc import Iterable
from decimal import Decimal

from app.market.domain import (
    CacheMetadata,
    HubPrice,
    MarketPriceLevel,
    OrderPageCache,
    RefreshResult,
    RefreshStatus,
    ResourceState,
)
from app.market.errors import EsiPayloadError, EsiRateLimitError
from app.market.esi import (
    ConditionalGetResult,
    EsiClient,
    parse_hub_order_page,
    parse_reference_prices,
    parse_system_cost_indices,
)
from app.market.repository import MarketCacheRepository


REFERENCE_PRICES_RESOURCE_KEY = "markets-prices"
SYSTEM_COST_INDICES_RESOURCE_KEY = "industry-systems"
_MAX_INT64 = 9_223_372_036_854_775_807


def hub_orders_resource_key(region_id: int, location_id: int) -> str:
    if region_id <= 0 or location_id <= 0:
        raise ValueError("Market region and location IDs must be positive")
    return f"market-orders:{region_id}:{location_id}"


def _resource_state(
    resource_key: str,
    metadata: CacheMetadata,
    row_count: int,
) -> ResourceState:
    return ResourceState(
        resource_key=resource_key,
        metadata=metadata,
        row_count=row_count,
    )


def _fresh_result(state: ResourceState) -> RefreshResult:
    return RefreshResult(
        resource=state.resource_key,
        status=RefreshStatus.FRESH,
        row_count=state.row_count,
        fresh_until=state.metadata.fresh_until,
    )


def _checked_volume_sum(left: int, right: int) -> int:
    total = left + right
    if total > _MAX_INT64:
        raise EsiPayloadError("Aggregated market volume exceeds BIGINT")
    return total


def _quote_levels(quote: HubPrice, side: str) -> tuple[MarketPriceLevel, ...]:
    levels = quote.buy_levels if side == "buy" else quote.sell_levels
    if levels:
        return levels
    price = quote.best_buy_price if side == "buy" else quote.best_sell_price
    volume = quote.best_buy_volume if side == "buy" else quote.best_sell_volume
    if price is None:
        return ()
    if volume is None:
        raise EsiPayloadError(f"Best-{side} volume is missing")
    return (MarketPriceLevel(price=price, volume=volume),)


def _merge_levels(
    left: tuple[MarketPriceLevel, ...],
    right: tuple[MarketPriceLevel, ...],
    *,
    reverse: bool,
) -> tuple[MarketPriceLevel, ...]:
    volumes: dict[Decimal, int] = {}
    for level in (*left, *right):
        volumes[level.price] = _checked_volume_sum(
            volumes.get(level.price, 0),
            level.volume,
        )
    return tuple(
        MarketPriceLevel(price=price, volume=volume)
        for price, volume in sorted(
            volumes.items(),
            key=lambda item: item[0],
            reverse=reverse,
        )
    )


def merge_hub_prices(pages: Iterable[OrderPageCache]) -> tuple[HubPrice, ...]:
    """Merge station-scoped page depth without losing equal-price volume."""
    merged: dict[int, HubPrice] = {}
    for page in pages:
        for quote in page.quotes:
            current = merged.get(quote.type_id)
            if current is None:
                buy_levels = _quote_levels(quote, "buy")
                sell_levels = _quote_levels(quote, "sell")
            else:
                buy_levels = _merge_levels(
                    _quote_levels(current, "buy"),
                    _quote_levels(quote, "buy"),
                    reverse=True,
                )
                sell_levels = _merge_levels(
                    _quote_levels(current, "sell"),
                    _quote_levels(quote, "sell"),
                    reverse=False,
                )
            merged[quote.type_id] = HubPrice(
                type_id=quote.type_id,
                best_buy_price=buy_levels[0].price if buy_levels else None,
                best_buy_volume=buy_levels[0].volume if buy_levels else None,
                best_sell_price=sell_levels[0].price if sell_levels else None,
                best_sell_volume=sell_levels[0].volume if sell_levels else None,
                buy_levels=buy_levels,
                sell_levels=sell_levels,
            )
    return tuple(merged[type_id] for type_id in sorted(merged))


class MarketCacheRefresher:
    def __init__(
        self,
        repository: MarketCacheRepository,
        esi: EsiClient,
        *,
        region_id: int,
        location_id: int,
    ) -> None:
        if region_id <= 0 or location_id <= 0:
            raise ValueError("Market region and location IDs must be positive")
        self._repository = repository
        self._esi = esi
        self._region_id = region_id
        self._location_id = location_id

    def _is_fresh(self, state: ResourceState | None) -> bool:
        return (
            state is not None
            and state.metadata.fresh_until > self._esi.now()
            and state.metadata.requested_compatibility_date
            == self._esi.compatibility_date
        )

    def refresh_reference_prices(self) -> RefreshResult:
        with self._repository.acquire_read_snapshot():
            state = self._repository.get_resource_state(
                REFERENCE_PRICES_RESOURCE_KEY
            )
        if self._is_fresh(state):
            return _fresh_result(state)

        result = self._esi.conditional_get(
            "/markets/prices",
            cached=state.metadata if state is not None else None,
        )
        if result.not_modified:
            if state is None:
                raise EsiPayloadError(
                    "Reference prices returned 304 without cached rows"
                )
            refreshed_state = _resource_state(
                REFERENCE_PRICES_RESOURCE_KEY,
                result.metadata,
                state.row_count,
            )
            self._repository.save_resource_state(refreshed_state)
            return RefreshResult(
                resource=REFERENCE_PRICES_RESOURCE_KEY,
                status=RefreshStatus.NOT_MODIFIED,
                row_count=state.row_count,
                fresh_until=result.metadata.fresh_until,
            )

        if result.content is None:
            raise EsiPayloadError("Reference-price response body is missing")
        prices = parse_reference_prices(result.content)
        refreshed_state = _resource_state(
            REFERENCE_PRICES_RESOURCE_KEY,
            result.metadata,
            len(prices),
        )
        self._repository.publish_reference_prices(refreshed_state, prices)
        return RefreshResult(
            resource=REFERENCE_PRICES_RESOURCE_KEY,
            status=RefreshStatus.UPDATED,
            row_count=len(prices),
            fresh_until=result.metadata.fresh_until,
        )

    def refresh_system_cost_indices(self) -> RefreshResult:
        with self._repository.acquire_read_snapshot():
            state = self._repository.get_resource_state(
                SYSTEM_COST_INDICES_RESOURCE_KEY
            )
        if self._is_fresh(state):
            return _fresh_result(state)

        result = self._esi.conditional_get(
            "/industry/systems",
            cached=state.metadata if state is not None else None,
        )
        if result.not_modified:
            if state is None:
                raise EsiPayloadError(
                    "System indices returned 304 without cached rows"
                )
            refreshed_state = _resource_state(
                SYSTEM_COST_INDICES_RESOURCE_KEY,
                result.metadata,
                state.row_count,
            )
            self._repository.save_resource_state(refreshed_state)
            return RefreshResult(
                resource=SYSTEM_COST_INDICES_RESOURCE_KEY,
                status=RefreshStatus.NOT_MODIFIED,
                row_count=state.row_count,
                fresh_until=result.metadata.fresh_until,
            )

        if result.content is None:
            raise EsiPayloadError("System-index response body is missing")
        indices = parse_system_cost_indices(result.content)
        refreshed_state = _resource_state(
            SYSTEM_COST_INDICES_RESOURCE_KEY,
            result.metadata,
            len(indices),
        )
        self._repository.publish_system_cost_indices(
            refreshed_state,
            indices,
        )
        return RefreshResult(
            resource=SYSTEM_COST_INDICES_RESOURCE_KEY,
            status=RefreshStatus.UPDATED,
            row_count=len(indices),
            fresh_until=result.metadata.fresh_until,
        )

    def _order_page(
        self,
        page: int,
        cached: OrderPageCache | None,
    ) -> tuple[OrderPageCache, ConditionalGetResult]:
        response = self._esi.conditional_get(
            f"/markets/{self._region_id}/orders",
            params={"order_type": "all", "page": page},
            cached=cached.metadata if cached is not None else None,
        )
        page_count = response.page_count or (
            cached.page_count if cached is not None else None
        )
        if page_count is None:
            raise EsiPayloadError("Market-order response is missing X-Pages")
        if response.not_modified:
            if cached is None:
                raise EsiPayloadError(
                    f"Market-order page {page} returned 304 without a cache"
                )
            quotes = cached.quotes
        else:
            if response.content is None:
                raise EsiPayloadError(
                    f"Market-order page {page} has no response body"
                )
            quotes = parse_hub_order_page(
                response.content,
                location_id=self._location_id,
                page=page,
            )
        return (
            OrderPageCache(
                region_id=self._region_id,
                location_id=self._location_id,
                page=page,
                page_count=page_count,
                metadata=response.metadata,
                quotes=quotes,
            ),
            response,
        )

    @staticmethod
    def _require_rate_budget(
        response: ConditionalGetResult,
        remaining_pages: int,
    ) -> None:
        if remaining_pages <= 0:
            return
        remaining_tokens = response.rate_limit_remaining
        required_tokens = remaining_pages * 2 + 10
        if remaining_tokens is not None and remaining_tokens < required_tokens:
            raise EsiRateLimitError()

    def refresh_hub_orders(self) -> RefreshResult:
        resource_key = hub_orders_resource_key(
            self._region_id,
            self._location_id,
        )
        with self._repository.acquire_read_snapshot():
            state = self._repository.get_resource_state(resource_key)
            cached_pages = self._repository.get_order_pages(
                self._region_id,
                self._location_id,
            )
        if self._is_fresh(state) and cached_pages:
            return _fresh_result(state)

        first_page, first_response = self._order_page(1, cached_pages.get(1))
        page_count = first_page.page_count
        self._require_rate_budget(first_response, page_count - 1)
        pages = [first_page]
        changed = not first_response.not_modified

        for page_number in range(2, page_count + 1):
            page, response = self._order_page(
                page_number,
                cached_pages.get(page_number),
            )
            if page.page_count != page_count:
                raise EsiPayloadError(
                    "X-Pages changed while the market snapshot was fetched"
                )
            pages.append(page)
            changed = changed or not response.not_modified
            self._require_rate_budget(response, page_count - page_number)

        last_modified_values = {
            page.metadata.last_modified_at
            for page in pages
            if page.metadata.last_modified_at is not None
        }
        if len(last_modified_values) > 1:
            raise EsiPayloadError(
                "Last-Modified changed while the market snapshot was fetched"
            )
        matched_compatibility_dates = {
            page.metadata.matched_compatibility_date
            for page in pages
            if page.metadata.matched_compatibility_date is not None
        }
        if len(matched_compatibility_dates) > 1:
            raise EsiPayloadError(
                "ESI compatibility date changed during market refresh"
            )

        prices = merge_hub_prices(pages)
        snapshot_metadata = CacheMetadata(
            etag=None,
            last_modified_at=(
                next(iter(last_modified_values)) if last_modified_values else None
            ),
            fresh_until=min(page.metadata.fresh_until for page in pages),
            fetched_at=max(page.metadata.fetched_at for page in pages),
            requested_compatibility_date=(
                first_page.metadata.requested_compatibility_date
            ),
            matched_compatibility_date=(
                next(iter(matched_compatibility_dates))
                if matched_compatibility_dates
                else None
            ),
        )
        refreshed_state = _resource_state(
            resource_key,
            snapshot_metadata,
            len(prices),
        )
        self._repository.publish_order_snapshot(
            refreshed_state,
            pages,
            prices,
        )
        return RefreshResult(
            resource=resource_key,
            status=(
                RefreshStatus.UPDATED if changed else RefreshStatus.NOT_MODIFIED
            ),
            row_count=len(prices),
            fresh_until=snapshot_metadata.fresh_until,
        )
