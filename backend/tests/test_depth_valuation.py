from decimal import Decimal

from app.industry.depth_valuation import (
    MarketDepthQuote,
    calculate_depth_aware_industry_economics,
)
from app.industry.models import (
    ItemQuantity,
    ProductionPlan,
    PurchaseReason,
    PurchaseRequirement,
)
from app.industry.valuation import (
    AdjustedPriceSnapshot,
    IndustryFeeRates,
    IndustryValuationInputs,
    MarketQuote,
    MarketQuoteSnapshot,
    SystemCostIndexSnapshot,
)
from app.market.domain import MarketPriceLevel


def _inputs() -> IndustryValuationInputs:
    return IndustryValuationInputs(
        market=MarketQuoteSnapshot(
            quotes=(
                MarketQuote(34, Decimal("9"), 2, Decimal("10"), 2),
                MarketQuote(35, Decimal("20"), 2, Decimal("21"), 2),
            )
        ),
        adjusted_prices=AdjustedPriceSnapshot(prices=()),
        system_cost_indices=SystemCostIndexSnapshot(indices=()),
        fees=IndustryFeeRates(
            solar_system_id=30_000_142,
            facility_tax_rate=Decimal("0"),
            scc_surcharge_rate=Decimal("0"),
            alpha_clone_tax_rate=Decimal("0"),
            sales_tax_rate=Decimal("0"),
            broker_fee_rate=Decimal("0"),
        ),
    )


def test_depth_valuation_uses_volume_weighted_fills() -> None:
    plan = ProductionPlan(
        sde_build_number=1,
        requested=(ItemQuantity(35, 5),),
        build_steps=(),
        purchases=(PurchaseRequirement(34, 5, PurchaseReason.NO_RECIPE),),
    )
    depth = {
        34: MarketDepthQuote(
            34,
            buy_levels=(),
            sell_levels=(
                MarketPriceLevel(Decimal("10"), 2),
                MarketPriceLevel(Decimal("11"), 3),
            ),
        ),
        35: MarketDepthQuote(
            35,
            buy_levels=(
                MarketPriceLevel(Decimal("20"), 2),
                MarketPriceLevel(Decimal("19"), 3),
            ),
            sell_levels=(),
        ),
    }

    economics = calculate_depth_aware_industry_economics(
        plan,
        _inputs(),
        depth,
    )

    assert economics.shopping_list_cost.amount == Decimal("53")
    assert economics.shopping_list[0].unit_price == Decimal("10.6")
    assert economics.requested_output_value.amount == Decimal("97")
    assert economics.requested_outputs[0].unit_price == Decimal("19.4")
    assert economics.missing_data.has_missing_data is False


def test_depth_valuation_preserves_insufficient_liquidity_reporting() -> None:
    plan = ProductionPlan(
        sde_build_number=1,
        requested=(ItemQuantity(35, 5),),
        build_steps=(),
        purchases=(PurchaseRequirement(34, 6, PurchaseReason.NO_RECIPE),),
    )
    depth = {
        34: MarketDepthQuote(
            34,
            buy_levels=(),
            sell_levels=(
                MarketPriceLevel(Decimal("10"), 2),
                MarketPriceLevel(Decimal("11"), 3),
            ),
        ),
        35: MarketDepthQuote(
            35,
            buy_levels=(MarketPriceLevel(Decimal("20"), 5),),
            sell_levels=(),
        ),
    }

    economics = calculate_depth_aware_industry_economics(
        plan,
        _inputs(),
        depth,
    )

    assert economics.shopping_list_cost.amount is None
    assert economics.shopping_list[0].available_volume == 5
    assert economics.shopping_list[0].has_sufficient_liquidity is False
    assert economics.missing_data.shopping_sell_liquidity_type_ids == (34,)
