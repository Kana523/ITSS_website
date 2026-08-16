from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from app.industry.errors import MissingActivityPricingError
from app.industry.models import ActivityKind, ProductionPlan
from app.industry.valuation import (
    ActivityFeeRates,
    AdjustedPrice,
    AdjustedPriceSnapshot,
    IndustryEconomics,
    IndustryFeeRates,
    IndustryValuationInputs,
    MarketQuote,
    MarketQuoteSnapshot,
    SystemCostIndex,
    SystemCostIndexSnapshot,
    calculate_industry_economics,
)
from app.market.domain import ResourceState
from app.market.refresh import (
    REFERENCE_PRICES_RESOURCE_KEY,
    SYSTEM_COST_INDICES_RESOURCE_KEY,
    hub_orders_resource_key,
)
from app.market.repository import MarketCacheRepository


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_basis_points(value: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 10_000
    ):
        raise ValueError(f"{field_name} must be an integer from 0 to 10000")


def _rate(basis_points: int) -> Decimal:
    # Construct the finite decimal directly. Decimal division (and subtraction
    # from one) observes the process-wide context and can silently round these
    # request rates when another caller has lowered its precision.
    whole, fraction = divmod(basis_points, 10_000)
    return Decimal(f"{whole}.{fraction:04d}")


class MarketSnapshotStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class MarketContext:
    region_id: int
    location_id: int
    location_name: str

    def __post_init__(self) -> None:
        _require_positive_int(self.region_id, "region_id")
        _require_positive_int(self.location_id, "location_id")
        if not self.location_name.strip():
            raise ValueError("location_name must not be blank")


@dataclass(frozen=True, slots=True)
class IndustryPricingOptions:
    """Explicit, reproducible rates for one profitability estimate.

    Rates use integer basis points. They are deliberately request inputs rather
    than hidden constants because character, facility, and game rates change.
    """

    solar_system_id: int = 30_000_142
    facility_tax_basis_points: int = 25
    scc_surcharge_basis_points: int = 400
    alpha_clone_tax_basis_points: int = 0
    sales_tax_basis_points: int = 0
    broker_fee_basis_points: int = 0
    job_cost_reduction_basis_points: int = 0
    reaction_solar_system_id: int | None = None
    reaction_facility_tax_basis_points: int = 25
    reaction_scc_surcharge_basis_points: int = 400
    reaction_alpha_clone_tax_basis_points: int = 0
    reaction_job_cost_reduction_basis_points: int = 0

    def __post_init__(self) -> None:
        _require_positive_int(self.solar_system_id, "solar_system_id")
        if self.reaction_solar_system_id is not None:
            _require_positive_int(
                self.reaction_solar_system_id,
                "reaction_solar_system_id",
            )
        for field_name in (
            "facility_tax_basis_points",
            "scc_surcharge_basis_points",
            "alpha_clone_tax_basis_points",
            "sales_tax_basis_points",
            "broker_fee_basis_points",
            "job_cost_reduction_basis_points",
            "reaction_facility_tax_basis_points",
            "reaction_scc_surcharge_basis_points",
            "reaction_alpha_clone_tax_basis_points",
            "reaction_job_cost_reduction_basis_points",
        ):
            _require_basis_points(getattr(self, field_name), field_name)
        if self.broker_fee_basis_points:
            raise ValueError(
                "broker_fee_basis_points must be zero for immediate best-buy "
                "sales"
            )

    def activity_fee_rates(
        self,
        activity: ActivityKind,
    ) -> ActivityFeeRates:
        if activity == ActivityKind.MANUFACTURING:
            return ActivityFeeRates(
                activity=activity,
                solar_system_id=self.solar_system_id,
                facility_tax_rate=_rate(self.facility_tax_basis_points),
                scc_surcharge_rate=_rate(self.scc_surcharge_basis_points),
                alpha_clone_tax_rate=_rate(
                    self.alpha_clone_tax_basis_points
                ),
                default_job_cost_modifier=_rate(
                    10_000 - self.job_cost_reduction_basis_points
                ),
            )
        if activity == ActivityKind.REACTION:
            if self.reaction_solar_system_id is None:
                raise MissingActivityPricingError((activity,))
            return ActivityFeeRates(
                activity=activity,
                solar_system_id=self.reaction_solar_system_id,
                facility_tax_rate=_rate(
                    self.reaction_facility_tax_basis_points
                ),
                scc_surcharge_rate=_rate(
                    self.reaction_scc_surcharge_basis_points
                ),
                alpha_clone_tax_rate=_rate(
                    self.reaction_alpha_clone_tax_basis_points
                ),
                default_job_cost_modifier=_rate(
                    10_000
                    - self.reaction_job_cost_reduction_basis_points
                ),
            )
        raise ValueError(f"Unsupported pricing activity: {activity}")

    def to_fee_rates(
        self,
        activities: set[ActivityKind] | None = None,
    ) -> IndustryFeeRates:
        selected_activities = activities or {ActivityKind.MANUFACTURING}
        activity_rates = tuple(
            self.activity_fee_rates(activity)
            for activity in sorted(
                selected_activities,
                key=lambda value: value.value,
            )
        )
        manufacturing = self.activity_fee_rates(ActivityKind.MANUFACTURING)
        return IndustryFeeRates(
            solar_system_id=manufacturing.solar_system_id,
            facility_tax_rate=manufacturing.facility_tax_rate,
            scc_surcharge_rate=manufacturing.scc_surcharge_rate,
            alpha_clone_tax_rate=manufacturing.alpha_clone_tax_rate,
            sales_tax_rate=_rate(self.sales_tax_basis_points),
            broker_fee_rate=_rate(self.broker_fee_basis_points),
            default_job_cost_modifier=manufacturing.default_job_cost_modifier,
            activity_fee_rates=activity_rates,
        )


@dataclass(frozen=True, slots=True)
class CacheResourceStamp:
    resource: str
    fetched_at: datetime
    fresh_until: datetime
    row_count: int
    requested_compatibility_date: date
    matched_compatibility_date: date | None


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    region_id: int
    location_id: int
    location_name: str
    status: MarketSnapshotStatus
    input_strategy: str
    output_strategy: str
    resources: tuple[CacheResourceStamp, ...]


@dataclass(frozen=True, slots=True)
class ValuedProductionPlan:
    economics: IndustryEconomics
    market_snapshot: MarketSnapshot
    pricing_options: IndustryPricingOptions


def _resource_stamp(state: ResourceState) -> CacheResourceStamp:
    return CacheResourceStamp(
        resource=state.resource_key,
        fetched_at=state.metadata.fetched_at,
        fresh_until=state.metadata.fresh_until,
        row_count=state.row_count,
        requested_compatibility_date=(
            state.metadata.requested_compatibility_date
        ),
        matched_compatibility_date=state.metadata.matched_compatibility_date,
    )


class IndustryEconomicsService:
    """Join a pure production plan to previously cached public ESI data."""

    def __init__(
        self,
        repository: MarketCacheRepository,
        context: MarketContext,
        *,
        now: Callable[[], datetime] | None = None,
        compatibility_date: date | None = None,
    ) -> None:
        self._repository = repository
        self._context = context
        self._now = now or (lambda: datetime.now(UTC))
        self._compatibility_date = compatibility_date

    def value_plan(
        self,
        plan: ProductionPlan,
        options: IndustryPricingOptions,
    ) -> ValuedProductionPlan:
        quote_type_ids = {
            item.type_id for item in plan.requested
        } | {item.type_id for item in plan.purchases}
        adjusted_price_type_ids: set[int] = set()
        activities: set[ActivityKind] = set()
        for step in plan.build_steps:
            quote_type_ids.add(step.product_type_id)
            quote_type_ids.update(item.type_id for item in step.inputs)
            adjusted_price_type_ids.update(
                item.type_id for item in step.recipe.materials
            )
            activities.add(step.recipe.activity)

        activity_fee_rates = {
            activity: options.activity_fee_rates(activity)
            for activity in activities
        }

        orders_key = hub_orders_resource_key(
            self._context.region_id,
            self._context.location_id,
        )
        with self._repository.acquire_read_snapshot():
            order_state = self._repository.get_resource_state(orders_key)
            reference_state = (
                self._repository.get_resource_state(
                    REFERENCE_PRICES_RESOURCE_KEY
                )
                if plan.build_steps
                else None
            )
            systems_state = (
                self._repository.get_resource_state(
                    SYSTEM_COST_INDICES_RESOURCE_KEY
                )
                if plan.build_steps
                else None
            )
            hub_prices = self._repository.load_hub_prices(
                quote_type_ids,
                region_id=self._context.region_id,
                location_id=self._context.location_id,
            )
            reference_prices = self._repository.load_reference_prices(
                adjusted_price_type_ids
            )
            cost_indices = {}
            activities_by_system: dict[int, set[str]] = {}
            for activity, rates in activity_fee_rates.items():
                activities_by_system.setdefault(
                    rates.solar_system_id,
                    set(),
                ).add(activity.value)
            for system_id, activity_codes in sorted(
                activities_by_system.items()
            ):
                for activity_code, index in (
                    self._repository.load_system_cost_indices(
                        system_id,
                        activity_codes,
                    ).items()
                ):
                    cost_indices[(system_id, activity_code)] = index

        required_states = [order_state]
        if plan.build_steps:
            required_states.extend((reference_state, systems_state))
        present_states = tuple(
            state for state in required_states if state is not None
        )
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("economics clock must return an aware datetime")
        now = now.astimezone(UTC)
        compatibility_mismatch = self._compatibility_date is not None and any(
            state.metadata.requested_compatibility_date
            != self._compatibility_date
            or state.metadata.matched_compatibility_date
            not in (None, self._compatibility_date)
            for state in present_states
        )
        if len(present_states) != len(required_states):
            status = MarketSnapshotStatus.UNAVAILABLE
        elif compatibility_mismatch or any(
            state.metadata.fresh_until <= now for state in present_states
        ):
            status = MarketSnapshotStatus.STALE
        else:
            status = MarketSnapshotStatus.FRESH

        valuation_inputs = IndustryValuationInputs(
            market=MarketQuoteSnapshot(
                quotes=tuple(
                    MarketQuote(
                        type_id=price.type_id,
                        best_buy_price=price.best_buy_price,
                        best_buy_volume=price.best_buy_volume,
                        best_sell_price=price.best_sell_price,
                        best_sell_volume=price.best_sell_volume,
                    )
                    for price in sorted(
                        hub_prices.values(),
                        key=lambda price: price.type_id,
                    )
                )
            ),
            adjusted_prices=AdjustedPriceSnapshot(
                prices=tuple(
                    AdjustedPrice(
                        type_id=price.type_id,
                        price=price.adjusted_price,
                    )
                    for price in sorted(
                        reference_prices.values(),
                        key=lambda price: price.type_id,
                    )
                )
            ),
            system_cost_indices=SystemCostIndexSnapshot(
                indices=tuple(
                    SystemCostIndex(
                        solar_system_id=index.solar_system_id,
                        activity=ActivityKind(index.activity),
                        cost_index=index.cost_index,
                    )
                    for index in sorted(
                        cost_indices.values(),
                        key=lambda index: (
                            index.solar_system_id,
                            index.activity,
                        ),
                    )
                )
            ),
            fees=options.to_fee_rates(activities),
        )
        economics = calculate_industry_economics(plan, valuation_inputs)
        return ValuedProductionPlan(
            economics=economics,
            market_snapshot=MarketSnapshot(
                region_id=self._context.region_id,
                location_id=self._context.location_id,
                location_name=self._context.location_name,
                status=status,
                input_strategy="best_sell",
                output_strategy="best_unrestricted_buy",
                resources=tuple(
                    _resource_stamp(state)
                    for state in sorted(
                        present_states,
                        key=lambda state: state.resource_key,
                    )
                ),
            ),
            pricing_options=options,
        )
