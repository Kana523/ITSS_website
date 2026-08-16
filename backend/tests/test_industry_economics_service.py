from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, getcontext

import pytest

from app.industry.economics_service import (
    CacheResourceStamp,
    IndustryEconomicsService,
    IndustryPricingOptions,
    MarketContext,
    MarketSnapshotStatus,
)
from app.industry.models import (
    ActivityKind,
    IndustryRecipe,
    ItemQuantity,
    RecipeKey,
)
from app.industry.planner import plan_production
from app.market.domain import (
    CacheMetadata,
    HubPrice,
    ReferencePrice,
    ResourceState,
    SystemCostIndex as CachedSystemCostIndex,
)
from app.market.refresh import (
    REFERENCE_PRICES_RESOURCE_KEY,
    SYSTEM_COST_INDICES_RESOURCE_KEY,
    hub_orders_resource_key,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
COMPATIBILITY_DATE = date(2026, 8, 13)
REGION_ID = 10_000_002
LOCATION_ID = 60_003_760
SYSTEM_ID = 30_000_142
ORDERS_KEY = hub_orders_resource_key(REGION_ID, LOCATION_ID)


def _state(
    resource_key: str,
    *,
    fetched_at: datetime,
    fresh_until: datetime,
    row_count: int,
    requested_compatibility_date: date = COMPATIBILITY_DATE,
    matched_compatibility_date: date | None = COMPATIBILITY_DATE,
) -> ResourceState:
    return ResourceState(
        resource_key=resource_key,
        metadata=CacheMetadata(
            etag='"v1"',
            last_modified_at=fetched_at - timedelta(minutes=1),
            fresh_until=fresh_until,
            fetched_at=fetched_at,
            requested_compatibility_date=requested_compatibility_date,
            matched_compatibility_date=matched_compatibility_date,
        ),
        row_count=row_count,
    )


def _states() -> dict[str, ResourceState]:
    return {
        ORDERS_KEY: _state(
            ORDERS_KEY,
            fetched_at=NOW - timedelta(minutes=3),
            fresh_until=NOW + timedelta(minutes=2),
            row_count=2,
        ),
        REFERENCE_PRICES_RESOURCE_KEY: _state(
            REFERENCE_PRICES_RESOURCE_KEY,
            fetched_at=NOW - timedelta(minutes=2),
            fresh_until=NOW + timedelta(minutes=3),
            row_count=1,
        ),
        SYSTEM_COST_INDICES_RESOURCE_KEY: _state(
            SYSTEM_COST_INDICES_RESOURCE_KEY,
            fetched_at=NOW - timedelta(minutes=1),
            fresh_until=NOW + timedelta(minutes=4),
            row_count=1,
        ),
    }


def _plan():
    recipe = IndustryRecipe(
        key=RecipeKey(2_001, 1),
        blueprint_name="Test Product Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(1_001, 2),),
        materials=(ItemQuantity(34, 3),),
    )
    return plan_production(
        (ItemQuantity(1_001, 3),),
        (recipe,),
        sde_build_number=1,
    )


def _mixed_activity_plan():
    reaction = IndustryRecipe(
        key=RecipeKey(2_002, 9),
        blueprint_name="Test Reaction Formula",
        activity=ActivityKind.REACTION,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(1_002, 2),),
        materials=(ItemQuantity(35, 4),),
    )
    manufacturing = IndustryRecipe(
        key=RecipeKey(2_003, 1),
        blueprint_name="Final Product Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(1_003, 1),),
        materials=(ItemQuantity(1_002, 2),),
    )
    return plan_production(
        (ItemQuantity(1_003, 1),),
        (reaction, manufacturing),
        sde_build_number=1,
    )


class FakeMarketCacheRepository:
    def __init__(
        self,
        *,
        states: Mapping[str, ResourceState] | None = None,
        hub_prices: Mapping[int, HubPrice] | None = None,
        reference_prices: Mapping[int, ReferencePrice] | None = None,
        cost_indices: Mapping[str, CachedSystemCostIndex] | None = None,
    ) -> None:
        self.states = dict(states or {})
        self.hub_prices = dict(hub_prices or {})
        self.reference_prices = dict(reference_prices or {})
        self.cost_indices = dict(cost_indices or {})
        self.calls: list[tuple[object, ...]] = []
        self.snapshot_depth = 0
        self.snapshot_count = 0

    def _record(self, *call: object) -> None:
        if self.snapshot_depth != 1:
            raise AssertionError("cache read occurred outside the read snapshot")
        self.calls.append(call)

    @contextmanager
    def acquire_read_snapshot(self) -> Iterator[None]:
        if self.snapshot_depth != 0:
            raise AssertionError("nested read snapshots are not expected")
        self.snapshot_depth = 1
        self.snapshot_count += 1
        self.calls.append(("snapshot_enter",))
        try:
            yield
        finally:
            self.calls.append(("snapshot_exit",))
            self.snapshot_depth = 0

    def get_resource_state(self, resource_key: str) -> ResourceState | None:
        self._record("state", resource_key)
        return self.states.get(resource_key)

    def load_hub_prices(
        self,
        type_ids: Collection[int],
        *,
        region_id: int,
        location_id: int,
    ) -> Mapping[int, HubPrice]:
        requested = tuple(sorted(type_ids))
        self._record("hub", requested, region_id, location_id)
        return {
            type_id: self.hub_prices[type_id]
            for type_id in requested
            if type_id in self.hub_prices
        }

    def load_reference_prices(
        self,
        type_ids: Collection[int],
    ) -> Mapping[int, ReferencePrice]:
        requested = tuple(sorted(type_ids))
        self._record("reference", requested)
        return {
            type_id: self.reference_prices[type_id]
            for type_id in requested
            if type_id in self.reference_prices
        }

    def load_system_cost_indices(
        self,
        solar_system_id: int,
        activities: Collection[str],
    ) -> Mapping[str, CachedSystemCostIndex]:
        requested = tuple(sorted(activities))
        self._record("indices", solar_system_id, requested)
        return {
            index.activity: index
            for index in self.cost_indices.values()
            if index.solar_system_id == solar_system_id
            and index.activity in requested
        }


def _service(repository: FakeMarketCacheRepository) -> IndustryEconomicsService:
    return IndustryEconomicsService(
        repository,
        MarketContext(REGION_ID, LOCATION_ID, "Jita 4-4"),
        now=lambda: NOW,
        compatibility_date=COMPATIBILITY_DATE,
    )


def test_fresh_snapshot_preserves_resource_stamps_and_uses_one_read_snapshot(
) -> None:
    states = _states()
    repository = FakeMarketCacheRepository(states=states)

    result = _service(repository).value_plan(
        _plan(),
        IndustryPricingOptions(),
    )

    assert result.market_snapshot.status == MarketSnapshotStatus.FRESH
    assert result.market_snapshot.region_id == REGION_ID
    assert result.market_snapshot.location_id == LOCATION_ID
    assert result.market_snapshot.location_name == "Jita 4-4"
    assert result.market_snapshot.resources == (
        CacheResourceStamp(
            resource=SYSTEM_COST_INDICES_RESOURCE_KEY,
            fetched_at=states[SYSTEM_COST_INDICES_RESOURCE_KEY].metadata.fetched_at,
            fresh_until=states[
                SYSTEM_COST_INDICES_RESOURCE_KEY
            ].metadata.fresh_until,
            row_count=1,
            requested_compatibility_date=COMPATIBILITY_DATE,
            matched_compatibility_date=COMPATIBILITY_DATE,
        ),
        CacheResourceStamp(
            resource=ORDERS_KEY,
            fetched_at=states[ORDERS_KEY].metadata.fetched_at,
            fresh_until=states[ORDERS_KEY].metadata.fresh_until,
            row_count=2,
            requested_compatibility_date=COMPATIBILITY_DATE,
            matched_compatibility_date=COMPATIBILITY_DATE,
        ),
        CacheResourceStamp(
            resource=REFERENCE_PRICES_RESOURCE_KEY,
            fetched_at=states[
                REFERENCE_PRICES_RESOURCE_KEY
            ].metadata.fetched_at,
            fresh_until=states[
                REFERENCE_PRICES_RESOURCE_KEY
            ].metadata.fresh_until,
            row_count=1,
            requested_compatibility_date=COMPATIBILITY_DATE,
            matched_compatibility_date=COMPATIBILITY_DATE,
        ),
    )
    assert repository.snapshot_count == 1
    assert repository.snapshot_depth == 0
    assert repository.calls == [
        ("snapshot_enter",),
        ("state", ORDERS_KEY),
        ("state", REFERENCE_PRICES_RESOURCE_KEY),
        ("state", SYSTEM_COST_INDICES_RESOURCE_KEY),
        ("hub", (34, 1_001), REGION_ID, LOCATION_ID),
        ("reference", (34,)),
        ("indices", SYSTEM_ID, ("manufacturing",)),
        ("snapshot_exit",),
    ]


@pytest.mark.parametrize(
    ("remove_resource", "stale_resource", "expected_status"),
    (
        (None, REFERENCE_PRICES_RESOURCE_KEY, MarketSnapshotStatus.STALE),
        (
            SYSTEM_COST_INDICES_RESOURCE_KEY,
            None,
            MarketSnapshotStatus.UNAVAILABLE,
        ),
    ),
)
def test_snapshot_status_reports_stale_and_unavailable_resources(
    remove_resource: str | None,
    stale_resource: str | None,
    expected_status: MarketSnapshotStatus,
) -> None:
    states = _states()
    if remove_resource is not None:
        del states[remove_resource]
    if stale_resource is not None:
        previous = states[stale_resource]
        states[stale_resource] = _state(
            stale_resource,
            fetched_at=previous.metadata.fetched_at,
            fresh_until=NOW,
            row_count=previous.row_count,
        )
    repository = FakeMarketCacheRepository(states=states)

    result = _service(repository).value_plan(
        _plan(),
        IndustryPricingOptions(),
    )

    assert result.market_snapshot.status == expected_status
    assert {stamp.resource for stamp in result.market_snapshot.resources} == set(
        states
    )


def test_fresh_timestamps_from_an_old_compatibility_date_are_stale() -> None:
    old_date = COMPATIBILITY_DATE - timedelta(days=1)
    states = {
        key: _state(
            key,
            fetched_at=state.metadata.fetched_at,
            fresh_until=state.metadata.fresh_until,
            row_count=state.row_count,
            requested_compatibility_date=old_date,
            matched_compatibility_date=old_date,
        )
        for key, state in _states().items()
    }

    result = _service(
        FakeMarketCacheRepository(states=states)
    ).value_plan(_plan(), IndustryPricingOptions())

    assert result.market_snapshot.status == MarketSnapshotStatus.STALE
    assert {
        stamp.requested_compatibility_date
        for stamp in result.market_snapshot.resources
    } == {old_date}
    assert {
        stamp.matched_compatibility_date
        for stamp in result.market_snapshot.resources
    } == {old_date}


def test_cached_values_map_exactly_and_default_basis_point_fees_are_explicit(
) -> None:
    repository = FakeMarketCacheRepository(
        states=_states(),
        hub_prices={
            34: HubPrice(
                type_id=34,
                best_buy_price=Decimal("4.875"),
                best_buy_volume=200,
                best_sell_price=Decimal("5.125"),
                best_sell_volume=6,
            ),
            1_001: HubPrice(
                type_id=1_001,
                best_buy_price=Decimal("17.75"),
                best_buy_volume=4,
                best_sell_price=Decimal("19.50"),
                best_sell_volume=3,
            ),
        },
        reference_prices={
            34: ReferencePrice(
                type_id=34,
                adjusted_price=Decimal("4.25"),
                average_price=Decimal("4.50"),
            )
        },
        cost_indices={
            "manufacturing": CachedSystemCostIndex(
                solar_system_id=SYSTEM_ID,
                activity="manufacturing",
                cost_index=Decimal("0.012345"),
            )
        },
    )
    options = IndustryPricingOptions()

    result = _service(repository).value_plan(_plan(), options)

    rates = options.to_fee_rates()
    assert rates.solar_system_id == SYSTEM_ID
    assert rates.facility_tax_rate == Decimal("0.0025")
    assert rates.scc_surcharge_rate == Decimal("0.04")
    assert rates.alpha_clone_tax_rate == Decimal("0")
    assert rates.sales_tax_rate == Decimal("0")
    assert rates.broker_fee_rate == Decimal("0")
    assert rates.default_job_cost_modifier == Decimal("1")

    economics = result.economics
    assert economics.shopping_list[0].unit_price == Decimal("5.125")
    assert economics.shopping_list[0].available_volume == 6
    assert economics.shopping_list_cost.amount == Decimal("30.750")
    assert economics.requested_outputs[0].unit_price == Decimal("17.75")
    assert economics.requested_outputs[0].available_volume == 4
    assert economics.requested_output_value.amount == Decimal("53.25")
    assert economics.surplus_inventory_value.amount == Decimal("17.75")
    assert economics.marketable_inventory_value.amount == Decimal("71.00")
    assert economics.profit == Decimal("21.10145250")
    assert economics.profit_including_surplus == Decimal("38.85145250")
    assert economics.job_costs[0].estimated_item_value == Decimal("25.50")
    assert economics.job_costs[0].system_cost_index == Decimal("0.012345")
    assert economics.job_costs[0].job_cost_modifier == Decimal("1")
    assert economics.job_costs[0].installation_rate == Decimal("0.054845")
    assert economics.job_costs[0].installation_cost == Decimal("1.39854750")
    assert result.market_snapshot.input_strategy == "best_sell"
    assert result.market_snapshot.output_strategy == "best_unrestricted_buy"


def test_cached_nulls_and_market_depth_propagate_as_missing_not_zero() -> None:
    repository = FakeMarketCacheRepository(
        states=_states(),
        hub_prices={
            34: HubPrice(
                type_id=34,
                best_buy_price=Decimal("4.875"),
                best_buy_volume=200,
                best_sell_price=Decimal("5.125"),
                best_sell_volume=5,
            ),
            1_001: HubPrice(
                type_id=1_001,
                best_buy_price=None,
                best_buy_volume=None,
                best_sell_price=Decimal("19.50"),
                best_sell_volume=3,
            ),
        },
        reference_prices={
            34: ReferencePrice(
                type_id=34,
                adjusted_price=None,
                average_price=Decimal("4.50"),
            )
        },
        cost_indices={},
    )

    economics = _service(repository).value_plan(
        _plan(),
        IndustryPricingOptions(),
    ).economics

    assert economics.shopping_list[0].has_sufficient_liquidity is False
    assert economics.shopping_list[0].total is None
    assert economics.requested_outputs[0].unit_price is None
    assert economics.requested_outputs[0].total is None
    assert economics.job_costs[0].estimated_item_value is None
    assert economics.job_costs[0].system_cost_index is None
    assert economics.missing_data.shopping_sell_quote_type_ids == ()
    assert economics.missing_data.shopping_sell_liquidity_type_ids == (34,)
    assert economics.missing_data.output_buy_quote_type_ids == (1_001,)
    assert economics.missing_data.output_buy_liquidity_type_ids == ()
    assert economics.missing_data.adjusted_price_type_ids == (34,)
    assert economics.missing_data.system_cost_index_keys == (
        (SYSTEM_ID, ActivityKind.MANUFACTURING),
    )
    assert economics.shopping_list_cost.amount is None
    assert economics.requested_output_value.amount is None
    assert economics.total_cost is None
    assert economics.profit is None


def test_non_default_basis_points_convert_without_float_rounding() -> None:
    options = IndustryPricingOptions(
        solar_system_id=30_002_665,
        facility_tax_basis_points=37,
        scc_surcharge_basis_points=401,
        alpha_clone_tax_basis_points=200,
        sales_tax_basis_points=359,
        broker_fee_basis_points=0,
        job_cost_reduction_basis_points=1_234,
    )

    original_precision = getcontext().prec
    getcontext().prec = 2
    try:
        rates = options.to_fee_rates()
    finally:
        getcontext().prec = original_precision

    assert rates.solar_system_id == 30_002_665
    assert rates.facility_tax_rate == Decimal("0.0037")
    assert rates.scc_surcharge_rate == Decimal("0.0401")
    assert rates.alpha_clone_tax_rate == Decimal("0.02")
    assert rates.sales_tax_rate == Decimal("0.0359")
    assert rates.broker_fee_rate == Decimal("0")
    assert rates.default_job_cost_modifier == Decimal("0.8766")


def test_best_buy_pricing_rejects_a_nonzero_broker_fee() -> None:
    with pytest.raises(
        ValueError,
        match="broker_fee_basis_points must be zero",
    ):
        IndustryPricingOptions(broker_fee_basis_points=1)


def test_mixed_plan_loads_and_applies_activity_costs_from_different_systems(
) -> None:
    manufacturing_system = SYSTEM_ID
    reaction_system = 30_000_144
    repository = FakeMarketCacheRepository(
        states=_states(),
        hub_prices={
            35: HubPrice(35, Decimal("1"), 100, Decimal("2"), 100),
            1_002: HubPrice(1_002, Decimal("8"), 100, Decimal("9"), 100),
            1_003: HubPrice(1_003, Decimal("20"), 100, Decimal("22"), 100),
        },
        reference_prices={
            35: ReferencePrice(35, Decimal("1.5"), Decimal("1.6")),
            1_002: ReferencePrice(1_002, Decimal("8"), Decimal("8.5")),
        },
        cost_indices={
            "manufacturing": CachedSystemCostIndex(
                manufacturing_system,
                "manufacturing",
                Decimal("0.1"),
            ),
            "reaction": CachedSystemCostIndex(
                reaction_system,
                "reaction",
                Decimal("0.2"),
            ),
        },
    )
    options = IndustryPricingOptions(
        solar_system_id=manufacturing_system,
        reaction_solar_system_id=reaction_system,
        reaction_facility_tax_basis_points=50,
        reaction_scc_surcharge_basis_points=400,
        reaction_alpha_clone_tax_basis_points=100,
        reaction_job_cost_reduction_basis_points=2_000,
    )

    result = _service(repository).value_plan(_mixed_activity_plan(), options)

    reaction_job, manufacturing_job = result.economics.job_costs
    assert reaction_job.activity == ActivityKind.REACTION
    assert reaction_job.solar_system_id == reaction_system
    assert reaction_job.system_cost_index == Decimal("0.2")
    assert reaction_job.job_cost_modifier == Decimal("0.8")
    assert reaction_job.installation_rate == Decimal("0.215")
    assert reaction_job.installation_cost == Decimal("1.2900")
    assert manufacturing_job.activity == ActivityKind.MANUFACTURING
    assert manufacturing_job.solar_system_id == manufacturing_system
    assert manufacturing_job.system_cost_index == Decimal("0.1")
    assert manufacturing_job.job_cost_modifier == Decimal("1")
    assert manufacturing_job.installation_rate == Decimal("0.1425")
    assert manufacturing_job.installation_cost == Decimal("2.2800")
    assert (
        "indices",
        manufacturing_system,
        ("manufacturing",),
    ) in repository.calls
    assert ("indices", reaction_system, ("reaction",)) in repository.calls
