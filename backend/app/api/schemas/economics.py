from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.industry.economics_service import (
    IndustryPricingOptions,
    MarketSnapshotStatus,
    ValuedProductionPlan,
)
from app.industry.models import ActivityKind, IndustryType
from app.industry.valuation import IndustryEconomics, ValuedItem


TypeId = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]
BasisPoints = Annotated[int, Field(strict=True, ge=0, le=10_000)]
ZeroBasisPoints = Annotated[int, Field(strict=True, ge=0, le=0)]


class EconomicsApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndustryPricingRequest(EconomicsApiModel):
    """Pricing and tax assumptions for one reproducible estimate."""

    solar_system_id: TypeId = 30_000_142
    facility_tax_basis_points: BasisPoints = 25
    scc_surcharge_basis_points: BasisPoints = 400
    alpha_clone_tax_basis_points: BasisPoints = 0
    sales_tax_basis_points: BasisPoints = 0
    broker_fee_basis_points: ZeroBasisPoints = 0
    job_cost_reduction_basis_points: BasisPoints = 0
    reaction_solar_system_id: TypeId | None = None
    reaction_facility_tax_basis_points: BasisPoints = 25
    reaction_scc_surcharge_basis_points: BasisPoints = 400
    reaction_alpha_clone_tax_basis_points: BasisPoints = 0
    reaction_job_cost_reduction_basis_points: BasisPoints = 0

    def to_domain(self) -> IndustryPricingOptions:
        return IndustryPricingOptions(
            solar_system_id=self.solar_system_id,
            facility_tax_basis_points=self.facility_tax_basis_points,
            scc_surcharge_basis_points=self.scc_surcharge_basis_points,
            alpha_clone_tax_basis_points=(
                self.alpha_clone_tax_basis_points
            ),
            sales_tax_basis_points=self.sales_tax_basis_points,
            broker_fee_basis_points=self.broker_fee_basis_points,
            job_cost_reduction_basis_points=(
                self.job_cost_reduction_basis_points
            ),
            reaction_solar_system_id=self.reaction_solar_system_id,
            reaction_facility_tax_basis_points=(
                self.reaction_facility_tax_basis_points
            ),
            reaction_scc_surcharge_basis_points=(
                self.reaction_scc_surcharge_basis_points
            ),
            reaction_alpha_clone_tax_basis_points=(
                self.reaction_alpha_clone_tax_basis_points
            ),
            reaction_job_cost_reduction_basis_points=(
                self.reaction_job_cost_reduction_basis_points
            ),
        )


class EconomicsItemReferenceResponse(EconomicsApiModel):
    type_id: int
    name: str


class EconomicsRecipeKeyResponse(EconomicsApiModel):
    blueprint_type_id: int
    activity_id: int


class CacheResourceStampResponse(EconomicsApiModel):
    resource: str
    fetched_at: datetime
    fresh_until: datetime
    row_count: int
    requested_compatibility_date: date
    matched_compatibility_date: date | None


class MarketSnapshotResponse(EconomicsApiModel):
    region_id: int
    location_id: int
    location_name: str
    status: MarketSnapshotStatus
    input_strategy: Literal["best_sell"]
    output_strategy: Literal["best_unrestricted_buy"]
    resources: tuple[CacheResourceStampResponse, ...]


class PricingOptionsResponse(EconomicsApiModel):
    solar_system_id: int
    facility_tax_basis_points: int
    scc_surcharge_basis_points: int
    alpha_clone_tax_basis_points: int
    sales_tax_basis_points: int
    broker_fee_basis_points: int
    job_cost_reduction_basis_points: int
    reaction_solar_system_id: int | None
    reaction_facility_tax_basis_points: int
    reaction_scc_surcharge_basis_points: int
    reaction_alpha_clone_tax_basis_points: int
    reaction_job_cost_reduction_basis_points: int


class ValuedItemResponse(EconomicsApiModel):
    item: EconomicsItemReferenceResponse
    quantity: int
    unit_price_isk: str | None
    available_volume: int | None
    has_sufficient_liquidity: bool | None
    total_isk: str | None


class ValuationSubtotalResponse(EconomicsApiModel):
    amount_isk: str | None
    complete: bool
    missing_type_ids: tuple[int, ...]
    insufficient_liquidity_type_ids: tuple[int, ...]


class JobCostEstimateResponse(EconomicsApiModel):
    product: EconomicsItemReferenceResponse
    recipe_key: EconomicsRecipeKeyResponse
    activity: ActivityKind
    solar_system_id: int
    runs: int
    estimated_item_value_isk: str | None
    system_cost_index: str | None
    job_cost_modifier: str
    installation_rate: str | None
    installation_cost_isk: str | None
    missing_adjusted_price_type_ids: tuple[int, ...]
    missing_system_cost_index: bool


class StepBuildBuyComparisonResponse(EconomicsApiModel):
    product: EconomicsItemReferenceResponse
    recipe_key: EconomicsRecipeKeyResponse
    required_quantity: int
    direct_input_market_cost_isk: str | None
    installation_cost_isk: str | None
    direct_build_cost_isk: str | None
    surplus_quantity: int
    surplus_market_value_isk: str | None
    surplus_net_value_isk: str | None
    effective_build_cost_isk: str | None
    buy_unit_price_isk: str | None
    direct_buy_cost_isk: str | None
    savings_if_built_isk: str | None
    lower_cost_option: Literal["build", "buy", "equal"] | None
    missing_sell_quote_type_ids: tuple[int, ...]
    insufficient_sell_liquidity_type_ids: tuple[int, ...]
    missing_surplus_buy_quote: bool
    insufficient_surplus_buy_liquidity: bool


class ExactDecimalRatioResponse(EconomicsApiModel):
    numerator: str
    denominator: str


class MissingSystemCostIndexResponse(EconomicsApiModel):
    solar_system_id: int
    activity: ActivityKind


class MissingValuationDataResponse(EconomicsApiModel):
    shopping_sell_quote_type_ids: tuple[int, ...]
    shopping_sell_liquidity_type_ids: tuple[int, ...]
    output_buy_quote_type_ids: tuple[int, ...]
    output_buy_liquidity_type_ids: tuple[int, ...]
    adjusted_price_type_ids: tuple[int, ...]
    system_cost_indices: tuple[MissingSystemCostIndexResponse, ...]


class IndustryEconomicsResponse(EconomicsApiModel):
    complete: bool
    shopping_list: tuple[ValuedItemResponse, ...]
    shopping_list_cost: ValuationSubtotalResponse
    requested_outputs: tuple[ValuedItemResponse, ...]
    requested_output_value: ValuationSubtotalResponse
    surplus_inventory: tuple[ValuedItemResponse, ...]
    surplus_inventory_value: ValuationSubtotalResponse
    marketable_inventory: tuple[ValuedItemResponse, ...]
    marketable_inventory_value: ValuationSubtotalResponse
    estimated_item_value_total_isk: str | None
    installation_cost_total_isk: str | None
    sales_tax_isk: str | None
    broker_fee_isk: str | None
    transaction_fees_total_isk: str | None
    net_output_value_isk: str | None
    total_cost_isk: str | None
    profit_isk: str | None
    profit_margin: ExactDecimalRatioResponse | None
    sales_tax_including_surplus_isk: str | None
    broker_fee_including_surplus_isk: str | None
    transaction_fees_total_including_surplus_isk: str | None
    net_output_value_including_surplus_isk: str | None
    total_cost_including_surplus_isk: str | None
    profit_including_surplus_isk: str | None
    profit_margin_including_surplus: ExactDecimalRatioResponse | None
    job_costs: tuple[JobCostEstimateResponse, ...]
    step_comparisons: tuple[StepBuildBuyComparisonResponse, ...]
    missing_data: MissingValuationDataResponse


class ValuationResponse(EconomicsApiModel):
    market_snapshot: MarketSnapshotResponse
    pricing_options: PricingOptionsResponse
    economics: IndustryEconomicsResponse


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return "0" if formatted in ("-0", "") else formatted


def _item_reference(
    type_id: int,
    item_types: dict[int, IndustryType],
) -> EconomicsItemReferenceResponse:
    item = item_types[type_id]
    return EconomicsItemReferenceResponse(type_id=type_id, name=item.name)


def _valued_item_response(
    item: ValuedItem,
    item_types: dict[int, IndustryType],
) -> ValuedItemResponse:
    return ValuedItemResponse(
        item=_item_reference(item.type_id, item_types),
        quantity=item.quantity,
        unit_price_isk=_decimal(item.unit_price),
        available_volume=item.available_volume,
        has_sufficient_liquidity=item.has_sufficient_liquidity,
        total_isk=_decimal(item.total),
    )


def _economics_response(
    economics: IndustryEconomics,
    item_types: dict[int, IndustryType],
) -> IndustryEconomicsResponse:
    def subtotal(value) -> ValuationSubtotalResponse:
        return ValuationSubtotalResponse(
            amount_isk=_decimal(value.amount),
            complete=value.is_complete,
            missing_type_ids=value.missing_type_ids,
            insufficient_liquidity_type_ids=(
                value.insufficient_liquidity_type_ids
            ),
        )

    return IndustryEconomicsResponse(
        complete=economics.is_complete,
        shopping_list=tuple(
            _valued_item_response(item, item_types)
            for item in economics.shopping_list
        ),
        shopping_list_cost=subtotal(economics.shopping_list_cost),
        requested_outputs=tuple(
            _valued_item_response(item, item_types)
            for item in economics.requested_outputs
        ),
        requested_output_value=subtotal(
            economics.requested_output_value
        ),
        surplus_inventory=tuple(
            _valued_item_response(item, item_types)
            for item in economics.surplus_inventory
        ),
        surplus_inventory_value=subtotal(
            economics.surplus_inventory_value
        ),
        marketable_inventory=tuple(
            _valued_item_response(item, item_types)
            for item in economics.marketable_inventory
        ),
        marketable_inventory_value=subtotal(
            economics.marketable_inventory_value
        ),
        estimated_item_value_total_isk=_decimal(
            economics.estimated_item_value_total
        ),
        installation_cost_total_isk=_decimal(
            economics.installation_cost_total
        ),
        sales_tax_isk=_decimal(economics.sales_tax),
        broker_fee_isk=_decimal(economics.broker_fee),
        transaction_fees_total_isk=_decimal(
            economics.transaction_fees_total
        ),
        net_output_value_isk=_decimal(economics.net_output_value),
        total_cost_isk=_decimal(economics.total_cost),
        profit_isk=_decimal(economics.profit),
        profit_margin=(
            ExactDecimalRatioResponse(
                numerator=_decimal(economics.profit_margin.numerator),
                denominator=_decimal(economics.profit_margin.denominator),
            )
            if economics.profit_margin is not None
            else None
        ),
        sales_tax_including_surplus_isk=_decimal(
            economics.sales_tax_including_surplus
        ),
        broker_fee_including_surplus_isk=_decimal(
            economics.broker_fee_including_surplus
        ),
        transaction_fees_total_including_surplus_isk=_decimal(
            economics.transaction_fees_total_including_surplus
        ),
        net_output_value_including_surplus_isk=_decimal(
            economics.net_output_value_including_surplus
        ),
        total_cost_including_surplus_isk=_decimal(
            economics.total_cost_including_surplus
        ),
        profit_including_surplus_isk=_decimal(
            economics.profit_including_surplus
        ),
        profit_margin_including_surplus=(
            ExactDecimalRatioResponse(
                numerator=_decimal(
                    economics.profit_margin_including_surplus.numerator
                ),
                denominator=_decimal(
                    economics.profit_margin_including_surplus.denominator
                ),
            )
            if economics.profit_margin_including_surplus is not None
            else None
        ),
        job_costs=tuple(
            JobCostEstimateResponse(
                product=_item_reference(job.product_type_id, item_types),
                recipe_key=EconomicsRecipeKeyResponse(
                    blueprint_type_id=job.recipe_key.blueprint_type_id,
                    activity_id=job.recipe_key.activity_id,
                ),
                activity=job.activity,
                solar_system_id=job.solar_system_id,
                runs=job.runs,
                estimated_item_value_isk=_decimal(
                    job.estimated_item_value
                ),
                system_cost_index=_decimal(job.system_cost_index),
                job_cost_modifier=_decimal(job.job_cost_modifier),
                installation_rate=_decimal(job.installation_rate),
                installation_cost_isk=_decimal(job.installation_cost),
                missing_adjusted_price_type_ids=(
                    job.missing_adjusted_price_type_ids
                ),
                missing_system_cost_index=job.missing_system_cost_index,
            )
            for job in economics.job_costs
        ),
        step_comparisons=tuple(
            StepBuildBuyComparisonResponse(
                product=_item_reference(
                    comparison.product_type_id,
                    item_types,
                ),
                recipe_key=EconomicsRecipeKeyResponse(
                    blueprint_type_id=(
                        comparison.recipe_key.blueprint_type_id
                    ),
                    activity_id=comparison.recipe_key.activity_id,
                ),
                required_quantity=comparison.required_quantity,
                direct_input_market_cost_isk=_decimal(
                    comparison.direct_input_market_cost
                ),
                installation_cost_isk=_decimal(
                    comparison.installation_cost
                ),
                direct_build_cost_isk=_decimal(
                    comparison.direct_build_cost
                ),
                surplus_quantity=comparison.surplus_quantity,
                surplus_market_value_isk=_decimal(
                    comparison.surplus_market_value
                ),
                surplus_net_value_isk=_decimal(
                    comparison.surplus_net_value
                ),
                effective_build_cost_isk=_decimal(
                    comparison.effective_build_cost
                ),
                buy_unit_price_isk=_decimal(comparison.buy_unit_price),
                direct_buy_cost_isk=_decimal(comparison.direct_buy_cost),
                savings_if_built_isk=_decimal(
                    comparison.savings_if_built
                ),
                lower_cost_option=(
                    comparison.lower_cost_option.value
                    if comparison.lower_cost_option is not None
                    else None
                ),
                missing_sell_quote_type_ids=(
                    comparison.missing_sell_quote_type_ids
                ),
                insufficient_sell_liquidity_type_ids=(
                    comparison.insufficient_sell_liquidity_type_ids
                ),
                missing_surplus_buy_quote=(
                    comparison.missing_surplus_buy_quote
                ),
                insufficient_surplus_buy_liquidity=(
                    comparison.insufficient_surplus_buy_liquidity
                ),
            )
            for comparison in economics.step_comparisons
        ),
        missing_data=MissingValuationDataResponse(
            shopping_sell_quote_type_ids=(
                economics.missing_data.shopping_sell_quote_type_ids
            ),
            shopping_sell_liquidity_type_ids=(
                economics.missing_data.shopping_sell_liquidity_type_ids
            ),
            output_buy_quote_type_ids=(
                economics.missing_data.output_buy_quote_type_ids
            ),
            output_buy_liquidity_type_ids=(
                economics.missing_data.output_buy_liquidity_type_ids
            ),
            adjusted_price_type_ids=(
                economics.missing_data.adjusted_price_type_ids
            ),
            system_cost_indices=tuple(
                MissingSystemCostIndexResponse(
                    solar_system_id=solar_system_id,
                    activity=activity,
                )
                for solar_system_id, activity in (
                    economics.missing_data.system_cost_index_keys
                )
            ),
        ),
    )


def valuation_response(
    result: ValuedProductionPlan,
    item_types: dict[int, IndustryType],
) -> ValuationResponse:
    snapshot = result.market_snapshot
    options = result.pricing_options
    return ValuationResponse(
        market_snapshot=MarketSnapshotResponse(
            region_id=snapshot.region_id,
            location_id=snapshot.location_id,
            location_name=snapshot.location_name,
            status=snapshot.status,
            input_strategy="best_sell",
            output_strategy="best_unrestricted_buy",
            resources=tuple(
                CacheResourceStampResponse(
                    resource=resource.resource,
                    fetched_at=resource.fetched_at,
                    fresh_until=resource.fresh_until,
                    row_count=resource.row_count,
                    requested_compatibility_date=(
                        resource.requested_compatibility_date
                    ),
                    matched_compatibility_date=(
                        resource.matched_compatibility_date
                    ),
                )
                for resource in snapshot.resources
            ),
        ),
        pricing_options=PricingOptionsResponse(
            solar_system_id=options.solar_system_id,
            facility_tax_basis_points=options.facility_tax_basis_points,
            scc_surcharge_basis_points=options.scc_surcharge_basis_points,
            alpha_clone_tax_basis_points=(
                options.alpha_clone_tax_basis_points
            ),
            sales_tax_basis_points=options.sales_tax_basis_points,
            broker_fee_basis_points=options.broker_fee_basis_points,
            job_cost_reduction_basis_points=(
                options.job_cost_reduction_basis_points
            ),
            reaction_solar_system_id=options.reaction_solar_system_id,
            reaction_facility_tax_basis_points=(
                options.reaction_facility_tax_basis_points
            ),
            reaction_scc_surcharge_basis_points=(
                options.reaction_scc_surcharge_basis_points
            ),
            reaction_alpha_clone_tax_basis_points=(
                options.reaction_alpha_clone_tax_basis_points
            ),
            reaction_job_cost_reduction_basis_points=(
                options.reaction_job_cost_reduction_basis_points
            ),
        ),
        economics=_economics_response(result.economics, item_types),
    )
