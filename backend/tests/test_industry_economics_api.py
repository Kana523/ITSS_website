from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_industry_application_service
from app.industry.application import IndustryApplicationService
from app.industry.economics_service import (
    IndustryEconomicsService,
    MarketContext,
)
from app.industry.models import (
    ActivityKind,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    RecipeKey,
)
from app.main import create_app
from app.market.domain import (
    CacheMetadata,
    HubPrice,
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
COMPATIBILITY_DATE = date(2026, 8, 13)
REGION_ID = 10_000_002
LOCATION_ID = 60_003_760
SYSTEM_ID = 30_000_142
RAW_TYPE_ID = 34
PRODUCT_TYPE_ID = 1_001
BLUEPRINT_TYPE_ID = 2_001
ORDERS_RESOURCE_KEY = hub_orders_resource_key(REGION_ID, LOCATION_ID)


def _type(type_id: int, name: str) -> IndustryType:
    return IndustryType(
        type_id=type_id,
        name=name,
        published=True,
        group_id=10,
        group_name="Test Group",
        category_id=1,
        category_name="Test Category",
    )


RECIPE = IndustryRecipe(
    key=RecipeKey(BLUEPRINT_TYPE_ID, 1),
    blueprint_name="Test Product Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=60,
    max_production_limit=100,
    products=(ItemQuantity(PRODUCT_TYPE_ID, 2),),
    materials=(ItemQuantity(RAW_TYPE_ID, 3),),
)

REACTION_RECIPE = IndustryRecipe(
    key=RecipeKey(BLUEPRINT_TYPE_ID, 9),
    blueprint_name="Test Product Reaction Formula",
    activity=ActivityKind.REACTION,
    time_seconds=60,
    max_production_limit=100,
    products=(ItemQuantity(PRODUCT_TYPE_ID, 2),),
    materials=(ItemQuantity(RAW_TYPE_ID, 3),),
)


class FakeIndustryDataRepository:
    def __init__(self) -> None:
        self.types = {
            item.type_id: item
            for item in (
                _type(RAW_TYPE_ID, "Raw Material"),
                _type(PRODUCT_TYPE_ID, "Test Product"),
                _type(BLUEPRINT_TYPE_ID, "Test Product Blueprint"),
            )
        }

    def latest_sde_build_number(self) -> int:
        return 9_000_001

    def search_types(
        self,
        query: str,
        *,
        published_only: bool = True,
        producible_only: bool = False,
        limit: int = 20,
    ) -> tuple[IndustryType, ...]:
        del published_only, producible_only
        return tuple(
            item
            for item in self.types.values()
            if query.casefold() in item.name.casefold()
        )[:limit]

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        return {
            type_id: self.types[type_id]
            for type_id in type_ids
            if type_id in self.types
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        return {
            type_id: (RECIPE,) if type_id == PRODUCT_TYPE_ID else ()
            for type_id in product_type_ids
        }


class FakeReactionIndustryDataRepository(FakeIndustryDataRepository):
    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        return {
            type_id: (
                (REACTION_RECIPE,) if type_id == PRODUCT_TYPE_ID else ()
            )
            for type_id in product_type_ids
        }


def _resource_state(resource_key: str, row_count: int) -> ResourceState:
    return ResourceState(
        resource_key=resource_key,
        metadata=CacheMetadata(
            etag='"test"',
            last_modified_at=NOW - timedelta(minutes=2),
            fresh_until=NOW + timedelta(minutes=4),
            fetched_at=NOW - timedelta(minutes=1),
            requested_compatibility_date=COMPATIBILITY_DATE,
            matched_compatibility_date=COMPATIBILITY_DATE,
        ),
        row_count=row_count,
    )


def _fresh_states() -> dict[str, ResourceState]:
    return {
        ORDERS_RESOURCE_KEY: _resource_state(ORDERS_RESOURCE_KEY, 2),
        REFERENCE_PRICES_RESOURCE_KEY: _resource_state(
            REFERENCE_PRICES_RESOURCE_KEY,
            1,
        ),
        SYSTEM_COST_INDICES_RESOURCE_KEY: _resource_state(
            SYSTEM_COST_INDICES_RESOURCE_KEY,
            1,
        ),
    }


class FakeMarketCacheRepository:
    def __init__(
        self,
        *,
        states: Mapping[str, ResourceState] | None = None,
        hub_prices: Mapping[int, HubPrice] | None = None,
        reference_prices: Mapping[int, ReferencePrice] | None = None,
        cost_indices: Mapping[str, SystemCostIndex] | None = None,
    ) -> None:
        self.states = dict(states or {})
        self.hub_prices = dict(hub_prices or {})
        self.reference_prices = dict(reference_prices or {})
        self.cost_indices = dict(cost_indices or {})
        self.read_snapshot_count = 0

    @contextmanager
    def acquire_read_snapshot(self) -> Iterator[None]:
        self.read_snapshot_count += 1
        yield

    def get_resource_state(self, resource_key: str) -> ResourceState | None:
        return self.states.get(resource_key)

    def load_hub_prices(
        self,
        type_ids: Collection[int],
        *,
        region_id: int,
        location_id: int,
    ) -> Mapping[int, HubPrice]:
        assert region_id == REGION_ID
        assert location_id == LOCATION_ID
        return {
            type_id: self.hub_prices[type_id]
            for type_id in type_ids
            if type_id in self.hub_prices
        }

    def load_reference_prices(
        self,
        type_ids: Collection[int],
    ) -> Mapping[int, ReferencePrice]:
        return {
            type_id: self.reference_prices[type_id]
            for type_id in type_ids
            if type_id in self.reference_prices
        }

    def load_system_cost_indices(
        self,
        solar_system_id: int,
        activities: Collection[str],
    ) -> Mapping[str, SystemCostIndex]:
        assert solar_system_id == SYSTEM_ID
        return {
            activity: self.cost_indices[activity]
            for activity in activities
            if activity in self.cost_indices
        }


def _complete_market_repository(
    *,
    raw_sell_volume: int = 6,
    product_buy_volume: int = 4,
) -> FakeMarketCacheRepository:
    return FakeMarketCacheRepository(
        states=_fresh_states(),
        hub_prices={
            RAW_TYPE_ID: HubPrice(
                type_id=RAW_TYPE_ID,
                best_buy_price=Decimal("4.875"),
                best_buy_volume=100,
                best_sell_price=Decimal("5.1250"),
                best_sell_volume=raw_sell_volume,
            ),
            PRODUCT_TYPE_ID: HubPrice(
                type_id=PRODUCT_TYPE_ID,
                best_buy_price=Decimal("17.75"),
                best_buy_volume=product_buy_volume,
                best_sell_price=Decimal("19.50"),
                best_sell_volume=100,
            ),
        },
        reference_prices={
            RAW_TYPE_ID: ReferencePrice(
                type_id=RAW_TYPE_ID,
                adjusted_price=Decimal("4.25"),
                average_price=Decimal("4.50"),
            )
        },
        cost_indices={
            "manufacturing": SystemCostIndex(
                solar_system_id=SYSTEM_ID,
                activity="manufacturing",
                cost_index=Decimal("0.012345"),
            )
        },
    )


@contextmanager
def _api_client(
    market_repository: FakeMarketCacheRepository,
    industry_repository: FakeIndustryDataRepository | None = None,
) -> Iterator[TestClient]:
    application = create_app()
    economics = IndustryEconomicsService(
        market_repository,
        MarketContext(REGION_ID, LOCATION_ID, "Jita 4-4"),
        now=lambda: NOW,
        compatibility_date=COMPATIBILITY_DATE,
    )
    service = IndustryApplicationService(
        industry_repository or FakeIndustryDataRepository(),
        economics,
    )
    application.dependency_overrides[get_industry_application_service] = (
        lambda: service
    )
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


def _calculation_request(*, include_pricing: bool = True) -> dict:
    request: dict = {
        "demands": [{"type_id": PRODUCT_TYPE_ID, "quantity": 3}],
    }
    if include_pricing:
        request["pricing"] = {}
    return request


@pytest.mark.parametrize(
    "pricing",
    (
        {"solar_system_id": "30000142"},
        {"solar_system_id": True},
        {"facility_tax_basis_points": -1},
        {"scc_surcharge_basis_points": 10_001},
        {"sales_tax_basis_points": "359"},
        {"broker_fee_basis_points": 1},
        {"broker_fee_basis_points": 1.5},
        {"job_cost_reduction_basis_points": 10_001},
        {"unexpected_rate": 10},
    ),
)
def test_pricing_request_validation_uses_the_api_error_envelope(
    pricing: dict,
) -> None:
    with _api_client(_complete_market_repository()) as client:
        response = client.post(
            "/api/industry/calculate",
            json={
                "demands": [
                    {"type_id": PRODUCT_TYPE_ID, "quantity": 3}
                ],
                "pricing": pricing,
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_fresh_valuation_serializes_every_decimal_as_an_exact_string() -> None:
    repository = _complete_market_repository()

    with _api_client(repository) as client:
        response = client.post(
            "/api/industry/calculate",
            json=_calculation_request(),
        )

    assert response.status_code == 200
    valuation = response.json()["valuation"]
    assert valuation["market_snapshot"]["status"] == "fresh"
    assert valuation["market_snapshot"]["input_strategy"] == "best_sell"
    assert (
        valuation["market_snapshot"]["output_strategy"]
        == "best_unrestricted_buy"
    )
    assert len(valuation["market_snapshot"]["resources"]) == 3
    assert {
        resource["requested_compatibility_date"]
        for resource in valuation["market_snapshot"]["resources"]
    } == {COMPATIBILITY_DATE.isoformat()}
    assert {
        resource["matched_compatibility_date"]
        for resource in valuation["market_snapshot"]["resources"]
    } == {COMPATIBILITY_DATE.isoformat()}
    assert valuation["pricing_options"] == {
        "solar_system_id": SYSTEM_ID,
        "facility_tax_basis_points": 25,
        "scc_surcharge_basis_points": 400,
        "sales_tax_basis_points": 0,
        "broker_fee_basis_points": 0,
        "job_cost_reduction_basis_points": 0,
        "reaction_solar_system_id": None,
        "reaction_facility_tax_basis_points": 25,
        "reaction_scc_surcharge_basis_points": 400,
        "reaction_job_cost_reduction_basis_points": 0,
    }

    economics = valuation["economics"]
    assert economics["complete"] is True
    assert economics["shopping_list"][0]["unit_price_isk"] == "5.125"
    assert economics["shopping_list_cost"]["amount_isk"] == "30.75"
    assert economics["requested_output_value"]["amount_isk"] == "53.25"
    assert economics["surplus_inventory"][0]["quantity"] == 1
    assert economics["surplus_inventory_value"]["amount_isk"] == "17.75"
    assert economics["marketable_inventory"][0]["quantity"] == 4
    assert economics["marketable_inventory_value"]["amount_isk"] == "71"
    assert economics["estimated_item_value_total_isk"] == "25.5"
    assert economics["installation_cost_total_isk"] == "1.3985475"
    assert economics["total_cost_isk"] == "32.1485475"
    assert economics["profit_isk"] == "21.1014525"
    assert economics["profit_margin"] == {
        "numerator": "21.1014525",
        "denominator": "53.25",
    }
    assert economics["profit_including_surplus_isk"] == "38.8514525"
    assert economics["profit_margin_including_surplus"] == {
        "numerator": "38.8514525",
        "denominator": "71",
    }
    assert economics["broker_fee_isk"] == "0"
    assert economics["broker_fee_including_surplus_isk"] == "0"
    assert economics["job_costs"][0]["job_cost_modifier"] == "1"
    assert economics["job_costs"][0]["installation_rate"] == "0.054845"
    comparison = economics["step_comparisons"][0]
    assert comparison["surplus_quantity"] == 1
    assert comparison["surplus_market_value_isk"] == "17.75"
    assert comparison["surplus_net_value_isk"] == "17.75"
    assert comparison["direct_build_cost_isk"] == "32.1485475"
    assert comparison["effective_build_cost_isk"] == "14.3985475"
    assert comparison["savings_if_built_isk"] == "44.1014525"
    assert comparison["lower_cost_option"] == "build"
    assert comparison["missing_surplus_buy_quote"] is False
    assert comparison["insufficient_surplus_buy_liquidity"] is False
    assert repository.read_snapshot_count == 1

    decimal_fields = (
        economics["shopping_list"][0]["unit_price_isk"],
        economics["shopping_list_cost"]["amount_isk"],
        economics["requested_output_value"]["amount_isk"],
        economics["installation_cost_total_isk"],
        economics["profit_isk"],
    )
    assert all(isinstance(value, str) for value in decimal_fields)


def test_unavailable_cache_returns_an_explicit_incomplete_valuation() -> None:
    repository = FakeMarketCacheRepository()

    with _api_client(repository) as client:
        response = client.post(
            "/api/industry/calculate",
            json=_calculation_request(),
        )

    assert response.status_code == 200
    valuation = response.json()["valuation"]
    assert valuation["market_snapshot"]["status"] == "unavailable"
    assert valuation["market_snapshot"]["resources"] == []

    economics = valuation["economics"]
    assert economics["complete"] is False
    assert economics["shopping_list_cost"]["amount_isk"] is None
    assert economics["requested_output_value"]["amount_isk"] is None
    assert economics["total_cost_isk"] is None
    assert economics["profit_isk"] is None
    assert economics["missing_data"] == {
        "shopping_sell_quote_type_ids": [RAW_TYPE_ID],
        "shopping_sell_liquidity_type_ids": [],
        "output_buy_quote_type_ids": [PRODUCT_TYPE_ID],
        "output_buy_liquidity_type_ids": [],
        "adjusted_price_type_ids": [RAW_TYPE_ID],
        "system_cost_indices": [
            {
                "solar_system_id": SYSTEM_ID,
                "activity": "manufacturing",
            }
        ],
    }


def test_reaction_pricing_requires_an_explicit_reaction_system() -> None:
    repository = _complete_market_repository()

    with _api_client(
        repository,
        FakeReactionIndustryDataRepository(),
    ) as client:
        response = client.post(
            "/api/industry/calculate",
            json=_calculation_request(),
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "missing_activity_pricing",
        "message": (
            "Pricing requires a job-cost context for each selected activity; "
            "missing: reaction"
        ),
        "details": {"activities": ["reaction"]},
    }
    assert repository.read_snapshot_count == 0


def test_insufficient_market_depth_is_not_reported_as_a_missing_quote() -> None:
    repository = _complete_market_repository(
        raw_sell_volume=5,
        product_buy_volume=2,
    )

    with _api_client(repository) as client:
        response = client.post(
            "/api/industry/calculate",
            json=_calculation_request(),
        )

    assert response.status_code == 200
    economics = response.json()["valuation"]["economics"]
    assert economics["complete"] is False
    shopping_line = economics["shopping_list"][0]
    assert shopping_line["quantity"] == 6
    assert shopping_line["unit_price_isk"] == "5.125"
    assert shopping_line["available_volume"] == 5
    assert shopping_line["has_sufficient_liquidity"] is False
    assert shopping_line["total_isk"] is None
    output_line = economics["requested_outputs"][0]
    assert output_line["quantity"] == 3
    assert output_line["unit_price_isk"] == "17.75"
    assert output_line["available_volume"] == 2
    assert output_line["has_sufficient_liquidity"] is False
    assert output_line["total_isk"] is None
    assert economics["missing_data"]["shopping_sell_quote_type_ids"] == []
    assert economics["missing_data"]["shopping_sell_liquidity_type_ids"] == [
        RAW_TYPE_ID
    ]
    assert economics["missing_data"]["output_buy_quote_type_ids"] == []
    assert economics["missing_data"]["output_buy_liquidity_type_ids"] == [
        PRODUCT_TYPE_ID
    ]
    assert economics["shopping_list_cost"]["amount_isk"] is None
    assert economics["requested_output_value"]["amount_isk"] is None
    assert economics["profit_isk"] is None


def test_omitting_pricing_skips_market_reads_and_returns_no_valuation() -> None:
    repository = _complete_market_repository()

    with _api_client(repository) as client:
        response = client.post(
            "/api/industry/calculate",
            json=_calculation_request(include_pricing=False),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valuation"] is None
    assert "market_prices" in body["excluded_modifiers"]
    assert repository.read_snapshot_count == 0
