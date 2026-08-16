from collections.abc import Collection, Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from app.market.domain import (
    HubPrice,
    OrderPageCache,
    ReferencePrice,
    ResourceState,
    SystemCostIndex,
)


class MarketCacheRepository(Protocol):
    def acquire_read_snapshot(self) -> AbstractContextManager[None]: ...

    def get_resource_state(self, resource_key: str) -> ResourceState | None: ...

    def get_order_pages(
        self,
        region_id: int,
        location_id: int,
    ) -> Mapping[int, OrderPageCache]: ...

    def save_resource_state(self, state: ResourceState) -> None: ...

    def publish_order_snapshot(
        self,
        state: ResourceState,
        pages: Collection[OrderPageCache],
        prices: Collection[HubPrice],
    ) -> None: ...

    def publish_reference_prices(
        self,
        state: ResourceState,
        prices: Collection[ReferencePrice],
    ) -> None: ...

    def publish_system_cost_indices(
        self,
        state: ResourceState,
        indices: Collection[SystemCostIndex],
    ) -> None: ...

    def load_hub_prices(
        self,
        type_ids: Collection[int],
        *,
        region_id: int,
        location_id: int,
    ) -> Mapping[int, HubPrice]: ...

    def load_reference_prices(
        self,
        type_ids: Collection[int],
    ) -> Mapping[int, ReferencePrice]: ...

    def load_system_cost_indices(
        self,
        solar_system_id: int,
        activities: Collection[str],
    ) -> Mapping[str, SystemCostIndex]: ...
