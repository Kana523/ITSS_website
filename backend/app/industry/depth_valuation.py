"""Depth-aware market fills layered over the established industry valuation.

The original valuation module remains the compatibility implementation for
callers that only have one best level.  This module recalculates every
market-dependent line with complete cached depth while reusing the established
EIV, installation-cost, fee, and missing-static-data calculations.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext

from app.industry.models import ProductionPlan
from app.industry.valuation import (
    ExactDecimalRatio,
    IndustryEconomics,
    IndustryValuationInputs,
    LowerCostOption,
    MissingValuationData,
    StepBuildBuyComparison,
    ValuationSubtotal,
    ValuedItem,
    calculate_industry_economics,
)
from app.market.domain import MarketPriceLevel


ZERO = Decimal("0")
ONE = Decimal("1")
_CALCULATION_PRECISION = 512


@dataclass(frozen=True, slots=True)
class MarketDepthQuote:
    type_id: int
    buy_levels: tuple[MarketPriceLevel, ...]
    sell_levels: tuple[MarketPriceLevel, ...]


@dataclass(frozen=True, slots=True)
class _Fill:
    unit_price: Decimal | None
    available_volume: int | None
    sufficient: bool | None
    total: Decimal | None


def _fill(
    levels: tuple[MarketPriceLevel, ...],
    quantity: int,
) -> _Fill:
    if not levels:
        return _Fill(None, None, None, None)
    available = sum(level.volume for level in levels)
    if available < quantity:
        return _Fill(levels[0].price, available, False, None)

    remaining = quantity
    total = ZERO
    for level in levels:
        take = min(remaining, level.volume)
        if take:
            total += level.price * Decimal(take)
            remaining -= take
        if remaining == 0:
            break
    return _Fill(
        unit_price=total / Decimal(quantity),
        available_volume=available,
        sufficient=True,
        total=total,
    )


def _value_items(
    quantities: tuple[tuple[int, int], ...],
    depth_by_type: Mapping[int, MarketDepthQuote],
    *,
    side: str,
) -> tuple[tuple[ValuedItem, ...], ValuationSubtotal]:
    lines: list[ValuedItem] = []
    missing: list[int] = []
    insufficient: list[int] = []
    subtotal = ZERO

    for type_id, quantity in quantities:
        quote = depth_by_type.get(type_id)
        levels = ()
        if quote is not None:
            levels = quote.sell_levels if side == "sell" else quote.buy_levels
        fill = _fill(levels, quantity)
        if fill.unit_price is None:
            missing.append(type_id)
        elif not fill.sufficient:
            insufficient.append(type_id)
        if fill.total is not None:
            subtotal += fill.total
        lines.append(
            ValuedItem(
                type_id=type_id,
                quantity=quantity,
                unit_price=fill.unit_price,
                available_volume=fill.available_volume,
                has_sufficient_liquidity=fill.sufficient,
                total=fill.total,
            )
        )

    missing_ids = tuple(sorted(set(missing)))
    insufficient_ids = tuple(sorted(set(insufficient)))
    return (
        tuple(lines),
        ValuationSubtotal(
            amount=(
                None if missing_ids or insufficient_ids else subtotal
            ),
            missing_type_ids=missing_ids,
            insufficient_liquidity_type_ids=insufficient_ids,
        ),
    )


def calculate_depth_aware_industry_economics(
    plan: ProductionPlan,
    inputs: IndustryValuationInputs,
    depth_by_type: Mapping[int, MarketDepthQuote],
) -> IndustryEconomics:
    """Calculate economics with an exact volume-weighted fill for every line."""
    base = calculate_industry_economics(plan, inputs)

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION

        shopping_list, shopping_cost = _value_items(
            tuple(
                (purchase.type_id, purchase.quantity)
                for purchase in plan.purchases
            ),
            depth_by_type,
            side="sell",
        )
        requested_outputs, requested_output_value = _value_items(
            tuple(
                (requested.type_id, requested.quantity)
                for requested in plan.requested
            ),
            depth_by_type,
            side="buy",
        )

        surplus_quantities: dict[int, int] = {}
        for step in plan.build_steps:
            if step.surplus_quantity:
                surplus_quantities[step.product_type_id] = (
                    surplus_quantities.get(step.product_type_id, 0)
                    + step.surplus_quantity
                )
        surplus_inventory, surplus_inventory_value = _value_items(
            tuple(sorted(surplus_quantities.items())),
            depth_by_type,
            side="buy",
        )

        marketable_quantities = dict(surplus_quantities)
        for requested in plan.requested:
            marketable_quantities[requested.type_id] = (
                marketable_quantities.get(requested.type_id, 0)
                + requested.quantity
            )
        marketable_inventory, marketable_inventory_value = _value_items(
            tuple(sorted(marketable_quantities.items())),
            depth_by_type,
            side="buy",
        )

        job_by_recipe = {job.recipe_key: job for job in base.job_costs}
        comparisons: list[StepBuildBuyComparison] = []
        for step in plan.build_steps:
            direct_inputs, direct_input_cost = _value_items(
                tuple(
                    (material.type_id, material.quantity)
                    for material in step.inputs
                ),
                depth_by_type,
                side="sell",
            )
            job = job_by_recipe[step.recipe.key]
            direct_build_cost = None
            if (
                direct_input_cost.amount is not None
                and job.installation_cost is not None
            ):
                direct_build_cost = (
                    direct_input_cost.amount + job.installation_cost
                )

            product_depth = depth_by_type.get(step.product_type_id)
            sell_levels = (
                product_depth.sell_levels if product_depth is not None else ()
            )
            direct_buy_fill = _fill(sell_levels, step.required_quantity)
            direct_buy_cost = direct_buy_fill.total

            surplus_market_value = ZERO if step.surplus_quantity == 0 else None
            surplus_net_value = ZERO if step.surplus_quantity == 0 else None
            missing_surplus_buy_quote = False
            insufficient_surplus_buy_liquidity = False
            if step.surplus_quantity:
                buy_levels = (
                    product_depth.buy_levels if product_depth is not None else ()
                )
                surplus_fill = _fill(buy_levels, step.surplus_quantity)
                if surplus_fill.unit_price is None:
                    missing_surplus_buy_quote = True
                elif not surplus_fill.sufficient:
                    insufficient_surplus_buy_liquidity = True
                else:
                    surplus_market_value = surplus_fill.total
                    surplus_net_value = surplus_market_value * (
                        ONE
                        - inputs.fees.sales_tax_rate
                        - inputs.fees.broker_fee_rate
                    )

            effective_build_cost = None
            if direct_build_cost is not None and surplus_net_value is not None:
                effective_build_cost = direct_build_cost - surplus_net_value

            savings_if_built = None
            lower_cost_option = None
            if effective_build_cost is not None and direct_buy_cost is not None:
                savings_if_built = direct_buy_cost - effective_build_cost
                if effective_build_cost < direct_buy_cost:
                    lower_cost_option = LowerCostOption.BUILD
                elif direct_buy_cost < effective_build_cost:
                    lower_cost_option = LowerCostOption.BUY
                else:
                    lower_cost_option = LowerCostOption.EQUAL

            missing_quotes = set(direct_input_cost.missing_type_ids)
            insufficient_liquidity = set(
                direct_input_cost.insufficient_liquidity_type_ids
            )
            if direct_buy_fill.unit_price is None:
                missing_quotes.add(step.product_type_id)
            elif not direct_buy_fill.sufficient:
                insufficient_liquidity.add(step.product_type_id)

            comparisons.append(
                StepBuildBuyComparison(
                    product_type_id=step.product_type_id,
                    recipe_key=step.recipe.key,
                    required_quantity=step.required_quantity,
                    direct_inputs=direct_inputs,
                    direct_input_market_cost=direct_input_cost.amount,
                    installation_cost=job.installation_cost,
                    direct_build_cost=direct_build_cost,
                    surplus_quantity=step.surplus_quantity,
                    surplus_market_value=surplus_market_value,
                    surplus_net_value=surplus_net_value,
                    effective_build_cost=effective_build_cost,
                    buy_unit_price=direct_buy_fill.unit_price,
                    direct_buy_cost=direct_buy_cost,
                    savings_if_built=savings_if_built,
                    lower_cost_option=lower_cost_option,
                    missing_sell_quote_type_ids=tuple(sorted(missing_quotes)),
                    insufficient_sell_liquidity_type_ids=tuple(
                        sorted(insufficient_liquidity)
                    ),
                    missing_surplus_buy_quote=missing_surplus_buy_quote,
                    insufficient_surplus_buy_liquidity=(
                        insufficient_surplus_buy_liquidity
                    ),
                )
            )

        sales_tax = None
        broker_fee = None
        transaction_fees_total = None
        net_output_value = None
        if requested_output_value.amount is not None:
            sales_tax = requested_output_value.amount * inputs.fees.sales_tax_rate
            broker_fee = requested_output_value.amount * inputs.fees.broker_fee_rate
            transaction_fees_total = sales_tax + broker_fee
            net_output_value = requested_output_value.amount - transaction_fees_total

        total_cost = None
        profit = None
        profit_margin = None
        if (
            shopping_cost.amount is not None
            and base.installation_cost_total is not None
            and transaction_fees_total is not None
            and requested_output_value.amount is not None
        ):
            total_cost = (
                shopping_cost.amount
                + base.installation_cost_total
                + transaction_fees_total
            )
            profit = requested_output_value.amount - total_cost
            if requested_output_value.amount != ZERO:
                profit_margin = ExactDecimalRatio(
                    numerator=profit,
                    denominator=requested_output_value.amount,
                )

        sales_tax_including_surplus = None
        broker_fee_including_surplus = None
        transaction_fees_total_including_surplus = None
        net_output_value_including_surplus = None
        total_cost_including_surplus = None
        profit_including_surplus = None
        profit_margin_including_surplus = None
        if (
            shopping_cost.amount is not None
            and base.installation_cost_total is not None
            and marketable_inventory_value.amount is not None
        ):
            sales_tax_including_surplus = (
                marketable_inventory_value.amount * inputs.fees.sales_tax_rate
            )
            broker_fee_including_surplus = (
                marketable_inventory_value.amount * inputs.fees.broker_fee_rate
            )
            transaction_fees_total_including_surplus = (
                sales_tax_including_surplus + broker_fee_including_surplus
            )
            net_output_value_including_surplus = (
                marketable_inventory_value.amount
                - transaction_fees_total_including_surplus
            )
            total_cost_including_surplus = (
                shopping_cost.amount
                + base.installation_cost_total
                + transaction_fees_total_including_surplus
            )
            profit_including_surplus = (
                marketable_inventory_value.amount
                - total_cost_including_surplus
            )
            if marketable_inventory_value.amount != ZERO:
                profit_margin_including_surplus = ExactDecimalRatio(
                    numerator=profit_including_surplus,
                    denominator=marketable_inventory_value.amount,
                )

        missing_data = MissingValuationData(
            shopping_sell_quote_type_ids=shopping_cost.missing_type_ids,
            shopping_sell_liquidity_type_ids=(
                shopping_cost.insufficient_liquidity_type_ids
            ),
            output_buy_quote_type_ids=requested_output_value.missing_type_ids,
            output_buy_liquidity_type_ids=(
                requested_output_value.insufficient_liquidity_type_ids
            ),
            adjusted_price_type_ids=base.missing_data.adjusted_price_type_ids,
            system_cost_index_keys=base.missing_data.system_cost_index_keys,
        )

        return replace(
            base,
            shopping_list=shopping_list,
            shopping_list_cost=shopping_cost,
            requested_outputs=requested_outputs,
            requested_output_value=requested_output_value,
            surplus_inventory=surplus_inventory,
            surplus_inventory_value=surplus_inventory_value,
            marketable_inventory=marketable_inventory,
            marketable_inventory_value=marketable_inventory_value,
            sales_tax=sales_tax,
            broker_fee=broker_fee,
            transaction_fees_total=transaction_fees_total,
            net_output_value=net_output_value,
            total_cost=total_cost,
            profit=profit,
            profit_margin=profit_margin,
            sales_tax_including_surplus=sales_tax_including_surplus,
            broker_fee_including_surplus=broker_fee_including_surplus,
            transaction_fees_total_including_surplus=(
                transaction_fees_total_including_surplus
            ),
            net_output_value_including_surplus=(
                net_output_value_including_surplus
            ),
            total_cost_including_surplus=total_cost_including_surplus,
            profit_including_surplus=profit_including_surplus,
            profit_margin_including_surplus=(
                profit_margin_including_surplus
            ),
            step_comparisons=tuple(comparisons),
            missing_data=missing_data,
        )
