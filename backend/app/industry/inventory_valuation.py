"""Separate cash flow from the value of stock consumed by a production plan."""

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal, localcontext

from app.industry.models import ProductionPlan
from app.industry.valuation import (
    ExactDecimalRatio,
    IndustryEconomics,
    IndustryValuationInputs,
    InventoryValuationMethod,
    ValuationSubtotal,
    ValuedItem,
)

ZERO = Decimal(0)
ValueItems = Callable[
    [tuple[tuple[int, int], ...]],
    tuple[tuple[ValuedItem, ...], ValuationSubtotal],
]


def apply_inventory_valuation(
    plan: ProductionPlan,
    inputs: IndustryValuationInputs,
    economics: IndustryEconomics,
    value_replacements: ValueItems,
) -> IndustryEconomics:
    """Value consumed units only; missing costs never become zero-cost stock.

    Replacement valuation reserves the actual shopping quantities first. The
    hypothetical replacement uses the remaining order depth, so purchases and
    owned inventory cannot both consume the same cheap sell orders.
    """
    with localcontext() as context:
        context.prec = 512
        recorded = {cost.type_id: cost.unit_cost for cost in inputs.recorded_inventory_costs}
        purchases = {line.type_id: line for line in economics.shopping_list}
        lines: list[ValuedItem] = []
        for item in plan.consumed_inventory:
            if inputs.inventory_valuation_method == InventoryValuationMethod.RECORDED_COST:
                unit_cost = recorded.get(item.type_id)
                lines.append(ValuedItem(
                    item.type_id, item.quantity, unit_cost, None, None,
                    unit_cost * item.quantity if unit_cost is not None else None,
                ))
                continue

            purchase = purchases.get(item.type_id)
            purchased_quantity = purchase.quantity if purchase else 0
            combined, _ = value_replacements(((
                item.type_id, purchased_quantity + item.quantity,
            ),))
            quote = combined[0]
            purchased_cost = purchase.total if purchase else ZERO
            total = (
                quote.total - purchased_cost
                if quote.total is not None and purchased_cost is not None else None
            )
            lines.append(ValuedItem(
                item.type_id, item.quantity,
                total / item.quantity if total is not None else quote.unit_price,
                max(0, quote.available_volume - purchased_quantity)
                if quote.available_volume is not None else None,
                quote.has_sufficient_liquidity, total,
            ))

        missing = tuple(sorted(line.type_id for line in lines if line.unit_price is None))
        insufficient = tuple(sorted(
            line.type_id for line in lines if line.has_sufficient_liquidity is False
        ))
        inventory_value = ValuationSubtotal(
            sum((line.total for line in lines), ZERO)
            if all(line.total is not None for line in lines) else None,
            missing, insufficient,
        )
        cash_required = (
            economics.shopping_list_cost.amount + economics.installation_cost_total
            if economics.shopping_list_cost.amount is not None
            and economics.installation_cost_total is not None else None
        )
        production_cost = (
            cash_required + inventory_value.amount
            if cash_required is not None and inventory_value.amount is not None else None
        )

        def difference(left: Decimal | None, right: Decimal | None) -> Decimal | None:
            return left - right if left is not None and right is not None else None

        def total_cost(fees: Decimal | None) -> Decimal | None:
            return production_cost + fees if production_cost is not None and fees is not None else None

        def margin(profit: Decimal | None, revenue: Decimal | None) -> ExactDecimalRatio | None:
            return ExactDecimalRatio(profit, revenue) if profit is not None and revenue else None

        profit = difference(economics.net_output_value, production_cost)
        profit_with_surplus = difference(economics.net_output_value_including_surplus, production_cost)
        return replace(
            economics,
            consumed_inventory=tuple(lines),
            consumed_inventory_value=inventory_value,
            cash_required=cash_required,
            cash_surplus=difference(economics.net_output_value, cash_required),
            cash_surplus_including_surplus=difference(economics.net_output_value_including_surplus, cash_required),
            total_cost=total_cost(economics.transaction_fees_total),
            profit=profit,
            profit_margin=margin(profit, economics.requested_output_value.amount),
            total_cost_including_surplus=total_cost(economics.transaction_fees_total_including_surplus),
            profit_including_surplus=profit_with_surplus,
            profit_margin_including_surplus=margin(profit_with_surplus, economics.marketable_inventory_value.amount),
            missing_data=replace(
                economics.missing_data,
                inventory_cost_type_ids=missing,
                inventory_sell_liquidity_type_ids=insufficient,
            ),
        )
