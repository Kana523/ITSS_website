from dataclasses import FrozenInstanceError
from decimal import Decimal, getcontext

import pytest

from app.industry.models import (
    ActivityKind,
    BlueprintEfficiency,
    IndustryRecipe,
    ItemQuantity,
    RecipeKey,
)
from app.industry.planner import plan_production
from app.industry.valuation import (
    ActivityFeeRates,
    AdjustedPrice,
    AdjustedPriceSnapshot,
    ExactDecimalRatio,
    IndustryFeeRates,
    IndustryValuationInputs,
    InvalidValuationDataError,
    LowerCostOption,
    MarketQuote,
    MarketQuoteSnapshot,
    RecipeJobCostModifier,
    SystemCostIndex,
    SystemCostIndexSnapshot,
    calculate_industry_economics,
)


def _recipe(
    blueprint_type_id: int,
    product_type_id: int,
    output_quantity: int,
    materials: tuple[tuple[int, int], ...],
    *,
    activity: ActivityKind = ActivityKind.MANUFACTURING,
) -> IndustryRecipe:
    return IndustryRecipe(
        key=RecipeKey(
            blueprint_type_id,
            1 if activity == ActivityKind.MANUFACTURING else 9,
        ),
        blueprint_name=f"Blueprint {blueprint_type_id}",
        activity=activity,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(product_type_id, output_quantity),),
        materials=tuple(
            ItemQuantity(type_id, quantity) for type_id, quantity in materials
        ),
    )


def _quote(
    type_id: int,
    best_buy_price: Decimal | None,
    best_sell_price: Decimal | None,
    *,
    best_buy_volume: int = 1_000_000,
    best_sell_volume: int = 1_000_000,
) -> MarketQuote:
    return MarketQuote(
        type_id=type_id,
        best_buy_price=best_buy_price,
        best_buy_volume=(
            best_buy_volume if best_buy_price is not None else None
        ),
        best_sell_price=best_sell_price,
        best_sell_volume=(
            best_sell_volume if best_sell_price is not None else None
        ),
    )


def _plan():
    component = _recipe(2001, 1002, 2, ((4001, 4),))
    finished_product = _recipe(
        2002,
        1003,
        5,
        ((1002, 2), (4002, 3)),
    )
    return plan_production(
        (ItemQuantity(1003, 6),),
        (component, finished_product),
        sde_build_number=1,
    )


def _inputs(
    *,
    quotes: tuple[MarketQuote, ...] | None = None,
    adjusted_prices: tuple[AdjustedPrice, ...] | None = None,
    indices: tuple[SystemCostIndex, ...] | None = None,
    fees: IndustryFeeRates | None = None,
) -> IndustryValuationInputs:
    return IndustryValuationInputs(
        market=MarketQuoteSnapshot(
            quotes=(
                quotes
                if quotes is not None
                else (
                    _quote(1002, Decimal("8"), Decimal("9")),
                    _quote(1003, Decimal("20"), Decimal("22")),
                    _quote(4001, Decimal("1"), Decimal("2")),
                    _quote(4002, Decimal("4"), Decimal("5")),
                )
            ),
        ),
        adjusted_prices=AdjustedPriceSnapshot(
            prices=(
                adjusted_prices
                if adjusted_prices is not None
                else (
                    AdjustedPrice(1002, Decimal("8")),
                    AdjustedPrice(4001, Decimal("1.5")),
                    AdjustedPrice(4002, Decimal("4")),
                )
            ),
        ),
        system_cost_indices=SystemCostIndexSnapshot(
            indices=(
                indices
                if indices is not None
                else (
                    SystemCostIndex(
                        30000142,
                        ActivityKind.MANUFACTURING,
                        Decimal("0.1"),
                    ),
                )
            ),
        ),
        fees=(
            fees
            if fees is not None
            else IndustryFeeRates(
                solar_system_id=30000142,
                facility_tax_rate=Decimal("0.0025"),
                scc_surcharge_rate=Decimal("0.04"),
                sales_tax_rate=Decimal("0.036"),
                broker_fee_rate=Decimal("0.01"),
                default_job_cost_modifier=Decimal("0.9"),
            )
        ),
    )


def test_values_whole_plan_without_double_counting_built_intermediates() -> None:
    result = calculate_industry_economics(_plan(), _inputs())

    assert [(line.type_id, line.quantity) for line in result.shopping_list] == [
        (4001, 8),
        (4002, 6),
    ]
    assert result.shopping_list_cost.amount == Decimal("46")
    assert result.requested_output_value.amount == Decimal("120")
    assert [(line.type_id, line.quantity) for line in result.surplus_inventory] == [
        (1003, 4)
    ]
    assert result.surplus_inventory_value.amount == Decimal("80")
    assert [(line.type_id, line.quantity) for line in result.marketable_inventory] == [
        (1003, 10)
    ]
    assert result.marketable_inventory_value.amount == Decimal("200")
    assert [job.estimated_item_value for job in result.job_costs] == [
        Decimal("12.0"),
        Decimal("56"),
    ]
    assert [job.installation_rate for job in result.job_costs] == [
        Decimal("0.1325"),
        Decimal("0.1325"),
    ]
    assert [job.installation_cost for job in result.job_costs] == [
        Decimal("1.59000"),
        Decimal("7.4200"),
    ]
    assert result.estimated_item_value_total == Decimal("68.0")
    assert result.installation_cost_total == Decimal("9.01000")
    assert result.sales_tax == Decimal("4.320")
    assert result.broker_fee == Decimal("1.20")
    assert result.transaction_fees_total == Decimal("5.520")
    assert result.net_output_value == Decimal("114.480")
    assert result.total_cost == Decimal("60.53000")
    assert result.profit == Decimal("59.47000")
    assert result.profit_margin == ExactDecimalRatio(
        numerator=Decimal("59.47000"),
        denominator=Decimal("120"),
    )
    assert result.sales_tax_including_surplus == Decimal("7.200")
    assert result.broker_fee_including_surplus == Decimal("2.00")
    assert result.transaction_fees_total_including_surplus == Decimal("9.200")
    assert result.net_output_value_including_surplus == Decimal("190.800")
    assert result.total_cost_including_surplus == Decimal("64.21000")
    assert result.profit_including_surplus == Decimal("135.79000")
    assert result.profit_margin_including_surplus == ExactDecimalRatio(
        numerator=Decimal("135.79000"),
        denominator=Decimal("200"),
    )
    assert result.is_complete
    assert not result.missing_data.has_missing_data


def test_step_comparisons_are_direct_and_do_not_change_the_plan() -> None:
    plan = _plan()

    result = calculate_industry_economics(plan, _inputs())

    component, finished_product = result.step_comparisons
    assert component.direct_input_market_cost == Decimal("16")
    assert component.direct_build_cost == Decimal("17.59000")
    assert component.surplus_quantity == 0
    assert component.surplus_market_value == Decimal("0")
    assert component.surplus_net_value == Decimal("0")
    assert component.effective_build_cost == Decimal("17.59000")
    assert component.direct_buy_cost == Decimal("36")
    assert component.savings_if_built == Decimal("18.41000")
    assert component.lower_cost_option == LowerCostOption.BUILD
    assert finished_product.direct_input_market_cost == Decimal("66")
    assert finished_product.direct_build_cost == Decimal("73.4200")
    assert finished_product.surplus_quantity == 4
    assert finished_product.surplus_market_value == Decimal("80")
    assert finished_product.surplus_net_value == Decimal("76.320")
    assert finished_product.effective_build_cost == Decimal("-2.9000")
    assert finished_product.direct_buy_cost == Decimal("132")
    assert finished_product.savings_if_built == Decimal("134.9000")
    assert finished_product.lower_cost_option == LowerCostOption.BUILD
    assert result.shopping_list_cost.amount == Decimal("46")
    assert result.shopping_list == tuple(
        line for line in result.shopping_list if line.type_id != 1002
    )
    assert [step.product_type_id for step in plan.build_steps] == [1002, 1003]


def test_eiv_uses_sde_base_materials_not_me_adjusted_inputs() -> None:
    recipe = _recipe(2001, 1001, 1, ((4001, 19),))
    plan = plan_production(
        (ItemQuantity(1001, 2),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={
            recipe.key: BlueprintEfficiency(
                material_efficiency=10,
                time_efficiency=0,
            )
        },
    )
    assert plan.build_steps[0].inputs == (ItemQuantity(4001, 35),)
    inputs = _inputs(
        quotes=(
            _quote(1001, Decimal("100"), Decimal("110")),
            _quote(4001, Decimal("2"), Decimal("3")),
        ),
        adjusted_prices=(AdjustedPrice(4001, Decimal("2")),),
    )

    result = calculate_industry_economics(plan, inputs)

    assert result.job_costs[0].estimated_item_value == Decimal("76")
    assert result.shopping_list_cost.amount == Decimal("105")


def test_zero_eiv_does_not_require_a_system_cost_index() -> None:
    recipe = _recipe(2001, 1001, 1, ())
    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
    )
    inputs = _inputs(
        quotes=(_quote(1001, Decimal("10"), Decimal("11")),),
        adjusted_prices=(),
        indices=(),
    )

    result = calculate_industry_economics(plan, inputs)

    assert result.job_costs[0].estimated_item_value == Decimal("0")
    assert result.job_costs[0].installation_cost == Decimal("0")
    assert not result.job_costs[0].missing_system_cost_index
    assert result.installation_cost_total == Decimal("0")
    assert result.missing_data.system_cost_index_keys == ()
    assert result.is_complete


@pytest.mark.parametrize(
    ("inputs", "missing_attribute"),
    (
        (
            _inputs(
                quotes=(
                    _quote(1002, Decimal("8"), Decimal("9")),
                    _quote(1003, Decimal("20"), Decimal("22")),
                    _quote(4001, Decimal("1"), None),
                    _quote(4002, Decimal("4"), Decimal("5")),
                )
            ),
            "shopping_sell_quote_type_ids",
        ),
        (
            _inputs(
                quotes=(
                    _quote(1002, Decimal("8"), Decimal("9")),
                    _quote(1003, None, Decimal("22")),
                    _quote(4001, Decimal("1"), Decimal("2")),
                    _quote(4002, Decimal("4"), Decimal("5")),
                )
            ),
            "output_buy_quote_type_ids",
        ),
        (
            _inputs(
                adjusted_prices=(
                    AdjustedPrice(1002, Decimal("8")),
                    AdjustedPrice(4001, None),
                    AdjustedPrice(4002, Decimal("4")),
                )
            ),
            "adjusted_price_type_ids",
        ),
        (
            _inputs(indices=()),
            "system_cost_index_keys",
        ),
    ),
)
def test_missing_core_data_propagates_null_never_zero(
    inputs: IndustryValuationInputs,
    missing_attribute: str,
) -> None:
    result = calculate_industry_economics(_plan(), inputs)

    assert getattr(result.missing_data, missing_attribute)
    assert result.total_cost is None
    assert result.profit is None
    assert result.profit_margin is None
    assert not result.is_complete


def test_missing_comparison_quote_does_not_invalidate_complete_profit() -> None:
    inputs = _inputs(
        quotes=(
            _quote(1003, Decimal("20"), None),
            _quote(4001, Decimal("1"), Decimal("2")),
            _quote(4002, Decimal("4"), Decimal("5")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    assert result.is_complete
    assert result.profit == Decimal("59.47000")
    assert result.step_comparisons[0].missing_sell_quote_type_ids == (1002,)
    assert not result.step_comparisons[0].is_complete
    assert result.step_comparisons[1].missing_sell_quote_type_ids == (
        1002,
        1003,
    )


def test_best_price_depth_must_cover_the_full_shopping_quantity() -> None:
    inputs = _inputs(
        quotes=(
            _quote(1002, Decimal("8"), Decimal("9")),
            _quote(1003, Decimal("20"), Decimal("22")),
            _quote(
                4001,
                Decimal("1"),
                Decimal("2"),
                best_sell_volume=7,
            ),
            _quote(4002, Decimal("4"), Decimal("5")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    shallow_line = next(
        line for line in result.shopping_list if line.type_id == 4001
    )
    assert shallow_line.quantity == 8
    assert shallow_line.available_volume == 7
    assert shallow_line.has_sufficient_liquidity is False
    assert shallow_line.total is None
    assert result.shopping_list_cost.amount is None
    assert result.missing_data.shopping_sell_quote_type_ids == ()
    assert result.missing_data.shopping_sell_liquidity_type_ids == (4001,)
    assert result.total_cost is None
    assert result.profit is None


def test_best_buy_depth_must_cover_all_requested_outputs() -> None:
    inputs = _inputs(
        quotes=(
            _quote(1002, Decimal("8"), Decimal("9")),
            _quote(
                1003,
                Decimal("20"),
                Decimal("22"),
                best_buy_volume=5,
            ),
            _quote(4001, Decimal("1"), Decimal("2")),
            _quote(4002, Decimal("4"), Decimal("5")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    assert result.requested_outputs[0].quantity == 6
    assert result.requested_outputs[0].available_volume == 5
    assert result.requested_outputs[0].total is None
    assert result.requested_output_value.amount is None
    assert result.missing_data.output_buy_quote_type_ids == ()
    assert result.missing_data.output_buy_liquidity_type_ids == (1003,)
    assert result.sales_tax is None
    assert result.profit is None


def test_surplus_profitability_requires_depth_for_all_marketable_units() -> None:
    inputs = _inputs(
        quotes=(
            _quote(1002, Decimal("8"), Decimal("9")),
            _quote(
                1003,
                Decimal("20"),
                Decimal("22"),
                # Enough to value the six requested units and the four surplus
                # units separately, but not enough to sell all ten together.
                best_buy_volume=6,
            ),
            _quote(4001, Decimal("1"), Decimal("2")),
            _quote(4002, Decimal("4"), Decimal("5")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    assert result.is_complete
    assert result.profit == Decimal("59.47000")
    assert result.surplus_inventory_value.amount == Decimal("80")
    assert result.marketable_inventory_value.amount is None
    assert result.marketable_inventory_value.insufficient_liquidity_type_ids == (
        1003,
    )
    assert result.profit_including_surplus is None
    assert result.profit_margin_including_surplus is None


def test_direct_buy_comparison_checks_best_sell_depth_independently() -> None:
    inputs = _inputs(
        quotes=(
            _quote(
                1002,
                Decimal("8"),
                Decimal("9"),
                best_sell_volume=3,
            ),
            _quote(1003, Decimal("20"), Decimal("22")),
            _quote(4001, Decimal("1"), Decimal("2")),
            _quote(4002, Decimal("4"), Decimal("5")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    assert result.is_complete
    component = result.step_comparisons[0]
    assert component.required_quantity == 4
    assert component.direct_buy_cost is None
    assert component.insufficient_sell_liquidity_type_ids == (1002,)
    finished = result.step_comparisons[1]
    assert finished.direct_input_market_cost is None
    assert finished.insufficient_sell_liquidity_type_ids == (1002,)


def test_zero_is_a_real_price_not_missing_data() -> None:
    inputs = _inputs(
        quotes=(
            _quote(1002, Decimal("8"), Decimal("9")),
            _quote(1003, Decimal("0"), Decimal("22")),
            _quote(4001, Decimal("1"), Decimal("0")),
            _quote(4002, Decimal("4"), Decimal("0")),
        )
    )

    result = calculate_industry_economics(_plan(), inputs)

    assert result.shopping_list_cost.amount == Decimal("0")
    assert result.requested_output_value.amount == Decimal("0")
    assert result.total_cost == Decimal("9.01000")
    assert result.profit == Decimal("-9.01000")
    assert result.profit_margin is None
    assert result.is_complete


def test_recipe_specific_job_cost_modifier_wins_over_default() -> None:
    plan = _plan()
    finished_recipe = plan.build_steps[1].recipe.key
    rates = IndustryFeeRates(
        solar_system_id=30000142,
        facility_tax_rate=Decimal("0"),
        scc_surcharge_rate=Decimal("0"),
        sales_tax_rate=Decimal("0"),
        broker_fee_rate=Decimal("0"),
        default_job_cost_modifier=Decimal("1"),
        recipe_job_cost_modifiers=(
            RecipeJobCostModifier(finished_recipe, Decimal("0.5")),
        ),
    )

    result = calculate_industry_economics(plan, _inputs(fees=rates))

    assert result.job_costs[0].installation_cost == Decimal("1.20")
    assert result.job_costs[1].installation_cost == Decimal("2.800")


def test_manufacturing_and_reaction_jobs_use_separate_fee_contexts() -> None:
    reaction = _recipe(
        2001,
        1002,
        2,
        ((4001, 4),),
        activity=ActivityKind.REACTION,
    )
    manufacturing = _recipe(2002, 1003, 1, ((1002, 2),))
    plan = plan_production(
        (ItemQuantity(1003, 1),),
        (reaction, manufacturing),
        sde_build_number=1,
    )
    fees = IndustryFeeRates(
        solar_system_id=30000142,
        facility_tax_rate=Decimal("0.0025"),
        scc_surcharge_rate=Decimal("0.04"),
        sales_tax_rate=Decimal("0"),
        broker_fee_rate=Decimal("0"),
        default_job_cost_modifier=Decimal("0.9"),
        activity_fee_rates=(
            ActivityFeeRates(
                activity=ActivityKind.MANUFACTURING,
                solar_system_id=30000142,
                facility_tax_rate=Decimal("0.0025"),
                scc_surcharge_rate=Decimal("0.04"),
                default_job_cost_modifier=Decimal("0.9"),
            ),
            ActivityFeeRates(
                activity=ActivityKind.REACTION,
                solar_system_id=30000144,
                facility_tax_rate=Decimal("0.005"),
                scc_surcharge_rate=Decimal("0.04"),
                default_job_cost_modifier=Decimal("0.8"),
            ),
        ),
    )
    inputs = _inputs(
        quotes=(
            _quote(1002, Decimal("8"), Decimal("9")),
            _quote(1003, Decimal("20"), Decimal("22")),
            _quote(4001, Decimal("1"), Decimal("2")),
        ),
        adjusted_prices=(
            AdjustedPrice(1002, Decimal("8")),
            AdjustedPrice(4001, Decimal("1.5")),
        ),
        indices=(
            SystemCostIndex(
                30000142,
                ActivityKind.MANUFACTURING,
                Decimal("0.1"),
            ),
            SystemCostIndex(
                30000144,
                ActivityKind.REACTION,
                Decimal("0.2"),
            ),
        ),
        fees=fees,
    )

    result = calculate_industry_economics(plan, inputs)

    reaction_job, manufacturing_job = result.job_costs
    assert reaction_job.activity == ActivityKind.REACTION
    assert reaction_job.solar_system_id == 30000144
    assert reaction_job.estimated_item_value == Decimal("6.0")
    assert reaction_job.installation_rate == Decimal("0.205")
    assert reaction_job.installation_cost == Decimal("1.2300")
    assert manufacturing_job.activity == ActivityKind.MANUFACTURING
    assert manufacturing_job.solar_system_id == 30000142
    assert manufacturing_job.estimated_item_value == Decimal("16")
    assert manufacturing_job.installation_rate == Decimal("0.1325")
    assert manufacturing_job.installation_cost == Decimal("2.1200")


def test_calculation_is_independent_of_global_decimal_precision() -> None:
    original_precision = getcontext().prec
    getcontext().prec = 6
    try:
        result = calculate_industry_economics(_plan(), _inputs())
    finally:
        getcontext().prec = original_precision

    assert result.profit == Decimal("59.47000")


def test_input_dtos_are_immutable_and_reject_floats_and_duplicates() -> None:
    quote = _quote(1, Decimal("1"), Decimal("2"))
    with pytest.raises(FrozenInstanceError):
        quote.best_buy_price = Decimal("3")

    with pytest.raises(InvalidValuationDataError, match="must be a Decimal"):
        _quote(1, 1.0, Decimal("2"))  # type: ignore[arg-type]
    with pytest.raises(InvalidValuationDataError, match="repeats a type_id"):
        MarketQuoteSnapshot(quotes=(quote, quote))
