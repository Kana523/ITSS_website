"""Pure industry cost and profitability calculations.

This module deliberately knows nothing about SQLAlchemy, ESI, or FastAPI.  Callers
load cached market/reference data first, turn it into the immutable input objects
below, and then value an already-completed :class:`ProductionPlan`.

Rates are decimal fractions: ``Decimal("0.04")`` means four percent.  Money is
never rounded here; presentation and settlement rounding belong at the API/UI
boundary.  Missing data is represented by ``None`` plus explicit missing-key
collections, never by a zero price or zero cost.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from app.industry.models import (
    ActivityKind,
    ProductionPlan,
    RecipeKey,
)


ZERO = Decimal("0")
ONE = Decimal("1")
_CALCULATION_PRECISION = 512
_MAX_DECIMAL_DIGITS = 64
_MAX_DECIMAL_PLACES = 64
_MAX_INTEGER_DIGITS = 64


class InvalidValuationDataError(ValueError):
    """Raised when valuation inputs cannot describe a valid calculation."""


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidValuationDataError(
            f"{field_name} must be a positive integer"
        )


def _require_decimal(
    value: Decimal,
    field_name: str,
    *,
    minimum: Decimal | None = ZERO,
    maximum: Decimal | None = None,
) -> None:
    if not isinstance(value, Decimal):
        raise InvalidValuationDataError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise InvalidValuationDataError(f"{field_name} must be finite")
    if len(value.as_tuple().digits) > _MAX_DECIMAL_DIGITS:
        raise InvalidValuationDataError(
            f"{field_name} must contain at most {_MAX_DECIMAL_DIGITS} digits"
        )
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise InvalidValuationDataError(f"{field_name} has an invalid exponent")
    decimal_places = max(-exponent, 0)
    integer_digits = max(len(value.as_tuple().digits) + exponent, 0)
    if decimal_places > _MAX_DECIMAL_PLACES:
        raise InvalidValuationDataError(
            f"{field_name} must contain at most "
            f"{_MAX_DECIMAL_PLACES} decimal places"
        )
    if integer_digits > _MAX_INTEGER_DIGITS:
        raise InvalidValuationDataError(
            f"{field_name} must contain at most "
            f"{_MAX_INTEGER_DIGITS} integer digits"
        )
    if minimum is not None and value < minimum:
        raise InvalidValuationDataError(
            f"{field_name} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise InvalidValuationDataError(
            f"{field_name} must not exceed {maximum}"
        )


def _require_optional_price(
    value: Decimal | None,
    field_name: str,
) -> None:
    if value is not None:
        _require_decimal(value, field_name)


def _require_optional_non_negative_int(
    value: int | None,
    field_name: str,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidValuationDataError(
            f"{field_name} must be a non-negative integer or None"
        )


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Best prices for one type at the selected market location.

    ``best_sell_price`` is the price paid when buying immediately. In this
    application the buy side is the best cached order with ``min_volume == 1``;
    it is the conservative immediately executable sale price for arbitrary
    quantities at that price level.
    """

    type_id: int
    best_buy_price: Decimal | None
    best_buy_volume: int | None
    best_sell_price: Decimal | None
    best_sell_volume: int | None

    def __post_init__(self) -> None:
        _require_positive_int(self.type_id, "type_id")
        _require_optional_price(self.best_buy_price, "best_buy_price")
        _require_optional_non_negative_int(
            self.best_buy_volume,
            "best_buy_volume",
        )
        _require_optional_price(self.best_sell_price, "best_sell_price")
        _require_optional_non_negative_int(
            self.best_sell_volume,
            "best_sell_volume",
        )


@dataclass(frozen=True, slots=True)
class MarketQuoteSnapshot:
    quotes: tuple[MarketQuote, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(quote, MarketQuote) for quote in self.quotes):
            raise InvalidValuationDataError(
                "quotes must contain only MarketQuote values"
            )
        quotes = tuple(sorted(self.quotes, key=lambda quote: quote.type_id))
        type_ids = tuple(quote.type_id for quote in quotes)
        if len(type_ids) != len(set(type_ids)):
            raise InvalidValuationDataError(
                "market quote snapshot repeats a type_id"
            )
        object.__setattr__(self, "quotes", quotes)


@dataclass(frozen=True, slots=True)
class AdjustedPrice:
    """One ESI adjusted price used to calculate estimated item value (EIV)."""

    type_id: int
    price: Decimal | None

    def __post_init__(self) -> None:
        _require_positive_int(self.type_id, "type_id")
        _require_optional_price(self.price, "price")


@dataclass(frozen=True, slots=True)
class AdjustedPriceSnapshot:
    prices: tuple[AdjustedPrice, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(price, AdjustedPrice) for price in self.prices):
            raise InvalidValuationDataError(
                "prices must contain only AdjustedPrice values"
            )
        prices = tuple(sorted(self.prices, key=lambda price: price.type_id))
        type_ids = tuple(price.type_id for price in prices)
        if len(type_ids) != len(set(type_ids)):
            raise InvalidValuationDataError(
                "adjusted price snapshot repeats a type_id"
            )
        object.__setattr__(self, "prices", prices)


@dataclass(frozen=True, slots=True)
class SystemCostIndex:
    solar_system_id: int
    activity: ActivityKind
    cost_index: Decimal | None

    def __post_init__(self) -> None:
        _require_positive_int(self.solar_system_id, "solar_system_id")
        if not isinstance(self.activity, ActivityKind):
            raise InvalidValuationDataError(
                "activity must be an ActivityKind"
            )
        if self.cost_index is not None:
            _require_decimal(
                self.cost_index,
                "cost_index",
                maximum=ONE,
            )


@dataclass(frozen=True, slots=True)
class SystemCostIndexSnapshot:
    indices: tuple[SystemCostIndex, ...]

    def __post_init__(self) -> None:
        if any(
            not isinstance(index, SystemCostIndex) for index in self.indices
        ):
            raise InvalidValuationDataError(
                "indices must contain only SystemCostIndex values"
            )
        indices = tuple(
            sorted(
                self.indices,
                key=lambda index: (
                    index.solar_system_id,
                    index.activity.value,
                ),
            )
        )
        keys = tuple(
            (index.solar_system_id, index.activity) for index in indices
        )
        if len(keys) != len(set(keys)):
            raise InvalidValuationDataError(
                "system cost index snapshot repeats a system/activity"
            )
        object.__setattr__(self, "indices", indices)


@dataclass(frozen=True, slots=True)
class RecipeJobCostModifier:
    """Resolved facility/rig cost multiplier for a selected recipe.

    This is keyed by recipe rather than only by activity so a production-profile
    resolver can apply group/category-specific bonuses before valuation.
    """

    recipe_key: RecipeKey
    multiplier: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.recipe_key, RecipeKey):
            raise InvalidValuationDataError(
                "recipe_key must be a RecipeKey"
            )
        _require_decimal(
            self.multiplier,
            "multiplier",
            maximum=ONE,
        )


@dataclass(frozen=True, slots=True)
class ActivityFeeRates:
    """Installation-fee context for one industry activity.

    Manufacturing and reactions commonly run in different systems and
    facilities.  Keeping the context activity-scoped prevents a reaction job
    from silently inheriting a manufacturing system cost index or facility
    rate.
    """

    activity: ActivityKind
    solar_system_id: int
    facility_tax_rate: Decimal
    scc_surcharge_rate: Decimal
    default_job_cost_modifier: Decimal = ONE

    def __post_init__(self) -> None:
        if not isinstance(self.activity, ActivityKind):
            raise InvalidValuationDataError(
                "activity must be an ActivityKind"
            )
        _require_positive_int(self.solar_system_id, "solar_system_id")
        for field_name in (
            "facility_tax_rate",
            "scc_surcharge_rate",
            "default_job_cost_modifier",
        ):
            _require_decimal(
                getattr(self, field_name),
                field_name,
                maximum=ONE,
            )


@dataclass(frozen=True, slots=True)
class RecipeFeeRates:
    """Installation-fee context resolved for one selected recipe."""

    recipe_key: RecipeKey
    activity: ActivityKind
    solar_system_id: int
    facility_tax_rate: Decimal
    scc_surcharge_rate: Decimal
    default_job_cost_modifier: Decimal = ONE

    def __post_init__(self) -> None:
        if not isinstance(self.recipe_key, RecipeKey):
            raise InvalidValuationDataError(
                "recipe_key must be a RecipeKey"
            )
        if not isinstance(self.activity, ActivityKind):
            raise InvalidValuationDataError(
                "activity must be an ActivityKind"
            )
        _require_positive_int(self.solar_system_id, "solar_system_id")
        for field_name in (
            "facility_tax_rate",
            "scc_surcharge_rate",
            "default_job_cost_modifier",
        ):
            _require_decimal(
                getattr(self, field_name),
                field_name,
                maximum=ONE,
            )


@dataclass(frozen=True, slots=True)
class IndustryFeeRates:
    """Explicit rates used by one valuation run.

    All rates are fractions, not percentages or basis points.  A recipe without
    an override uses ``default_job_cost_modifier``.
    """

    solar_system_id: int
    facility_tax_rate: Decimal
    scc_surcharge_rate: Decimal
    sales_tax_rate: Decimal
    broker_fee_rate: Decimal
    default_job_cost_modifier: Decimal = ONE
    activity_fee_rates: tuple[ActivityFeeRates, ...] = ()
    recipe_job_cost_modifiers: tuple[RecipeJobCostModifier, ...] = ()
    recipe_fee_rates: tuple[RecipeFeeRates, ...] = ()

    def __post_init__(self) -> None:
        _require_positive_int(self.solar_system_id, "solar_system_id")
        for field_name in (
            "facility_tax_rate",
            "scc_surcharge_rate",
            "sales_tax_rate",
            "broker_fee_rate",
            "default_job_cost_modifier",
        ):
            _require_decimal(
                getattr(self, field_name),
                field_name,
                maximum=ONE,
            )

        if any(
            not isinstance(rate, ActivityFeeRates)
            for rate in self.activity_fee_rates
        ):
            raise InvalidValuationDataError(
                "activity_fee_rates must contain only ActivityFeeRates values"
            )
        activity_rates = tuple(
            sorted(self.activity_fee_rates, key=lambda item: item.activity.value)
        )
        activities = tuple(item.activity for item in activity_rates)
        if len(activities) != len(set(activities)):
            raise InvalidValuationDataError(
                "activity fee rates repeat an activity"
            )
        object.__setattr__(self, "activity_fee_rates", activity_rates)

        if any(
            not isinstance(rate, RecipeFeeRates)
            for rate in self.recipe_fee_rates
        ):
            raise InvalidValuationDataError(
                "recipe_fee_rates must contain only RecipeFeeRates values"
            )
        recipe_rates = tuple(
            sorted(self.recipe_fee_rates, key=lambda item: item.recipe_key)
        )
        recipe_rate_keys = tuple(item.recipe_key for item in recipe_rates)
        if len(recipe_rate_keys) != len(set(recipe_rate_keys)):
            raise InvalidValuationDataError(
                "recipe fee rates repeat a recipe_key"
            )
        object.__setattr__(self, "recipe_fee_rates", recipe_rates)

        if any(
            not isinstance(modifier, RecipeJobCostModifier)
            for modifier in self.recipe_job_cost_modifiers
        ):
            raise InvalidValuationDataError(
                "recipe_job_cost_modifiers must contain only "
                "RecipeJobCostModifier values"
            )
        modifiers = tuple(
            sorted(
                self.recipe_job_cost_modifiers,
                key=lambda item: item.recipe_key,
            )
        )
        recipe_keys = tuple(item.recipe_key for item in modifiers)
        if len(recipe_keys) != len(set(recipe_keys)):
            raise InvalidValuationDataError(
                "recipe job-cost modifiers repeat a recipe_key"
            )
        object.__setattr__(self, "recipe_job_cost_modifiers", modifiers)

    def for_activity(self, activity: ActivityKind) -> ActivityFeeRates:
        for rates in self.activity_fee_rates:
            if rates.activity == activity:
                return rates
        if self.activity_fee_rates:
            raise InvalidValuationDataError(
                f"No fee context was supplied for {activity.value}"
            )
        return ActivityFeeRates(
            activity=activity,
            solar_system_id=self.solar_system_id,
            facility_tax_rate=self.facility_tax_rate,
            scc_surcharge_rate=self.scc_surcharge_rate,
            default_job_cost_modifier=self.default_job_cost_modifier,
        )

    def for_recipe(
        self,
        recipe_key: RecipeKey,
        activity: ActivityKind,
    ) -> RecipeFeeRates | ActivityFeeRates:
        if not isinstance(recipe_key, RecipeKey):
            raise InvalidValuationDataError(
                "recipe_key must be a RecipeKey"
            )
        if not isinstance(activity, ActivityKind):
            raise InvalidValuationDataError(
                "activity must be an ActivityKind"
            )
        for rates in self.recipe_fee_rates:
            if rates.recipe_key != recipe_key:
                continue
            if rates.activity != activity:
                raise InvalidValuationDataError(
                    "recipe fee context activity does not match the recipe"
                )
            return rates
        return self.for_activity(activity)


@dataclass(frozen=True, slots=True)
class RecordedInventoryCost:
    type_id: int
    unit_cost: Decimal

    def __post_init__(self) -> None:
        _require_positive_int(self.type_id, "recorded inventory type_id")
        _require_decimal(self.unit_cost, "recorded inventory unit_cost")


class InventoryValuationMethod(StrEnum):
    REPLACEMENT_COST = "replacement_cost"
    RECORDED_COST = "recorded_cost"


@dataclass(frozen=True, slots=True)
class IndustryValuationInputs:
    market: MarketQuoteSnapshot
    adjusted_prices: AdjustedPriceSnapshot
    system_cost_indices: SystemCostIndexSnapshot
    fees: IndustryFeeRates
    inventory_valuation_method: InventoryValuationMethod = InventoryValuationMethod.REPLACEMENT_COST
    recorded_inventory_costs: tuple[RecordedInventoryCost, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.inventory_valuation_method, InventoryValuationMethod):
            raise InvalidValuationDataError("Invalid inventory valuation method")
        if any(not isinstance(cost, RecordedInventoryCost) for cost in self.recorded_inventory_costs):
            raise InvalidValuationDataError("Invalid recorded inventory cost")
        ids = [cost.type_id for cost in self.recorded_inventory_costs]
        if len(ids) != len(set(ids)):
            raise InvalidValuationDataError("Recorded inventory costs repeat a type_id")
        if not isinstance(self.market, MarketQuoteSnapshot):
            raise InvalidValuationDataError(
                "market must be a MarketQuoteSnapshot"
            )
        if not isinstance(self.adjusted_prices, AdjustedPriceSnapshot):
            raise InvalidValuationDataError(
                "adjusted_prices must be an AdjustedPriceSnapshot"
            )
        if not isinstance(self.system_cost_indices, SystemCostIndexSnapshot):
            raise InvalidValuationDataError(
                "system_cost_indices must be a SystemCostIndexSnapshot"
            )
        if not isinstance(self.fees, IndustryFeeRates):
            raise InvalidValuationDataError(
                "fees must be IndustryFeeRates"
            )


@dataclass(frozen=True, slots=True)
class ValuedItem:
    type_id: int
    quantity: int
    unit_price: Decimal | None
    available_volume: int | None
    has_sufficient_liquidity: bool | None
    total: Decimal | None


@dataclass(frozen=True, slots=True)
class ValuationSubtotal:
    amount: Decimal | None
    missing_type_ids: tuple[int, ...] = ()
    insufficient_liquidity_type_ids: tuple[int, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.amount is not None


@dataclass(frozen=True, slots=True)
class JobCostEstimate:
    product_type_id: int
    recipe_key: RecipeKey
    activity: ActivityKind
    solar_system_id: int
    runs: int
    estimated_item_value: Decimal | None
    system_cost_index: Decimal | None
    job_cost_modifier: Decimal
    installation_rate: Decimal | None
    installation_cost: Decimal | None
    missing_adjusted_price_type_ids: tuple[int, ...]
    missing_system_cost_index: bool

    @property
    def is_complete(self) -> bool:
        return self.installation_cost is not None


class LowerCostOption(StrEnum):
    BUILD = "build"
    BUY = "buy"
    EQUAL = "equal"


@dataclass(frozen=True, slots=True)
class StepBuildBuyComparison:
    """Informational direct-input comparison; it never changes the plan."""

    product_type_id: int
    recipe_key: RecipeKey
    required_quantity: int
    direct_inputs: tuple[ValuedItem, ...]
    direct_input_market_cost: Decimal | None
    installation_cost: Decimal | None
    direct_build_cost: Decimal | None
    surplus_quantity: int
    surplus_market_value: Decimal | None
    surplus_net_value: Decimal | None
    effective_build_cost: Decimal | None
    buy_unit_price: Decimal | None
    direct_buy_cost: Decimal | None
    savings_if_built: Decimal | None
    lower_cost_option: LowerCostOption | None
    missing_sell_quote_type_ids: tuple[int, ...]
    insufficient_sell_liquidity_type_ids: tuple[int, ...]
    missing_surplus_buy_quote: bool
    insufficient_surplus_buy_liquidity: bool

    @property
    def is_complete(self) -> bool:
        return (
            self.effective_build_cost is not None
            and self.direct_buy_cost is not None
        )


@dataclass(frozen=True, slots=True)
class ExactDecimalRatio:
    """An exact ratio whose decimal expansion may otherwise require rounding."""

    numerator: Decimal
    denominator: Decimal

    def __post_init__(self) -> None:
        _require_decimal(
            self.numerator,
            "numerator",
            minimum=None,
        )
        _require_decimal(self.denominator, "denominator")
        if self.denominator == ZERO:
            raise InvalidValuationDataError(
                "denominator must not be zero"
            )


@dataclass(frozen=True, slots=True)
class MissingValuationData:
    shopping_sell_quote_type_ids: tuple[int, ...]
    shopping_sell_liquidity_type_ids: tuple[int, ...]
    output_buy_quote_type_ids: tuple[int, ...]
    output_buy_liquidity_type_ids: tuple[int, ...]
    adjusted_price_type_ids: tuple[int, ...]
    system_cost_index_keys: tuple[tuple[int, ActivityKind], ...]
    inventory_cost_type_ids: tuple[int, ...] = ()
    inventory_sell_liquidity_type_ids: tuple[int, ...] = ()

    @property
    def has_missing_data(self) -> bool:
        return any(
            (
                self.shopping_sell_quote_type_ids,
                self.shopping_sell_liquidity_type_ids,
                self.output_buy_quote_type_ids,
                self.output_buy_liquidity_type_ids,
                self.adjusted_price_type_ids,
                self.system_cost_index_keys,
                self.inventory_cost_type_ids,
                self.inventory_sell_liquidity_type_ids,
            )
        )


@dataclass(frozen=True, slots=True)
class IndustryEconomics:
    shopping_list: tuple[ValuedItem, ...]
    shopping_list_cost: ValuationSubtotal
    requested_outputs: tuple[ValuedItem, ...]
    requested_output_value: ValuationSubtotal
    surplus_inventory: tuple[ValuedItem, ...]
    surplus_inventory_value: ValuationSubtotal
    marketable_inventory: tuple[ValuedItem, ...]
    marketable_inventory_value: ValuationSubtotal
    job_costs: tuple[JobCostEstimate, ...]
    estimated_item_value_total: Decimal | None
    installation_cost_total: Decimal | None
    sales_tax: Decimal | None
    broker_fee: Decimal | None
    transaction_fees_total: Decimal | None
    net_output_value: Decimal | None
    total_cost: Decimal | None
    profit: Decimal | None
    profit_margin: ExactDecimalRatio | None
    sales_tax_including_surplus: Decimal | None
    broker_fee_including_surplus: Decimal | None
    transaction_fees_total_including_surplus: Decimal | None
    net_output_value_including_surplus: Decimal | None
    total_cost_including_surplus: Decimal | None
    profit_including_surplus: Decimal | None
    profit_margin_including_surplus: ExactDecimalRatio | None
    step_comparisons: tuple[StepBuildBuyComparison, ...]
    missing_data: MissingValuationData
    consumed_inventory: tuple[ValuedItem, ...] = ()
    consumed_inventory_value: ValuationSubtotal = ValuationSubtotal(ZERO, (), ())
    cash_required: Decimal | None = None
    cash_surplus: Decimal | None = None
    cash_surplus_including_surplus: Decimal | None = None

    @property
    def is_complete(self) -> bool:
        """Whether requested-output profitability has every required value."""
        return self.profit is not None and not self.missing_data.has_missing_data


def _value_items(
    quantities: tuple[tuple[int, int], ...],
    unit_prices: dict[int, Decimal | None],
    available_volumes: dict[int, int | None],
) -> tuple[tuple[ValuedItem, ...], ValuationSubtotal]:
    lines: list[ValuedItem] = []
    missing_type_ids: list[int] = []
    insufficient_liquidity_type_ids: list[int] = []
    total = ZERO

    for type_id, quantity in quantities:
        unit_price = unit_prices.get(type_id)
        available_volume = available_volumes.get(type_id)
        has_sufficient_liquidity = None
        if unit_price is None:
            missing_type_ids.append(type_id)
        else:
            has_sufficient_liquidity = (
                available_volume is not None and available_volume >= quantity
            )
            if not has_sufficient_liquidity:
                insufficient_liquidity_type_ids.append(type_id)
        line_total = (
            unit_price * Decimal(quantity)
            if unit_price is not None and has_sufficient_liquidity
            else None
        )
        if line_total is not None:
            total += line_total
        lines.append(
            ValuedItem(
                type_id=type_id,
                quantity=quantity,
                unit_price=unit_price,
                available_volume=available_volume,
                has_sufficient_liquidity=has_sufficient_liquidity,
                total=line_total,
            )
        )

    missing = tuple(sorted(set(missing_type_ids)))
    insufficient = tuple(sorted(set(insufficient_liquidity_type_ids)))
    return (
        tuple(lines),
        ValuationSubtotal(
            amount=None if missing or insufficient else total,
            missing_type_ids=missing,
            insufficient_liquidity_type_ids=insufficient,
        ),
    )


def calculate_industry_economics(
    plan: ProductionPlan,
    inputs: IndustryValuationInputs,
) -> IndustryEconomics:
    """Value a production plan using cached data and explicit rates.

    EIV intentionally uses the SDE recipe's base material quantities multiplied
    by runs.  It does not use ME/facility-adjusted ``ProductionStep.inputs``.
    Cash input cost uses ``plan.purchases``. Consumed owned inventory is valued
    separately; intermediates produced by another step are not charged twice.
    """
    if not isinstance(plan, ProductionPlan):
        raise InvalidValuationDataError("plan must be a ProductionPlan")
    if not isinstance(inputs, IndustryValuationInputs):
        raise InvalidValuationDataError(
            "inputs must be IndustryValuationInputs"
        )

    quote_by_type = {quote.type_id: quote for quote in inputs.market.quotes}
    best_sell_by_type = {
        type_id: quote.best_sell_price
        for type_id, quote in quote_by_type.items()
    }
    best_sell_volume_by_type = {
        type_id: quote.best_sell_volume
        for type_id, quote in quote_by_type.items()
    }
    best_buy_by_type = {
        type_id: quote.best_buy_price
        for type_id, quote in quote_by_type.items()
    }
    best_buy_volume_by_type = {
        type_id: quote.best_buy_volume
        for type_id, quote in quote_by_type.items()
    }
    adjusted_price_by_type = {
        price.type_id: price.price for price in inputs.adjusted_prices.prices
    }
    index_by_key = {
        (index.solar_system_id, index.activity): index.cost_index
        for index in inputs.system_cost_indices.indices
    }
    modifier_by_recipe = {
        modifier.recipe_key: modifier.multiplier
        for modifier in inputs.fees.recipe_job_cost_modifiers
    }

    with localcontext() as context:
        # Input decimals are bounded in both scale and precision.  This
        # deliberately generous local precision keeps every finite operation
        # here exact without depending on the process-wide Decimal context.
        context.prec = _CALCULATION_PRECISION

        shopping_list, shopping_cost = _value_items(
            tuple(
                (purchase.type_id, purchase.quantity)
                for purchase in plan.purchases
            ),
            best_sell_by_type,
            best_sell_volume_by_type,
        )
        requested_outputs, requested_output_value = _value_items(
            tuple(
                (requested.type_id, requested.quantity)
                for requested in plan.requested
            ),
            best_buy_by_type,
            best_buy_volume_by_type,
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
            best_buy_by_type,
            best_buy_volume_by_type,
        )
        marketable_quantities: dict[int, int] = dict(surplus_quantities)
        for requested in plan.requested:
            marketable_quantities[requested.type_id] = (
                marketable_quantities.get(requested.type_id, 0)
                + requested.quantity
            )
        marketable_inventory, marketable_inventory_value = _value_items(
            tuple(sorted(marketable_quantities.items())),
            best_buy_by_type,
            best_buy_volume_by_type,
        )

        job_costs: list[JobCostEstimate] = []
        missing_adjusted_price_ids: set[int] = set()
        missing_index_keys: set[tuple[int, ActivityKind]] = set()
        eiv_total = ZERO
        installation_total = ZERO
        all_eiv_complete = True
        all_installation_complete = True

        for step in plan.build_steps:
            missing_for_job = tuple(
                sorted(
                    material.type_id
                    for material in step.recipe.materials
                    if adjusted_price_by_type.get(material.type_id) is None
                )
            )
            missing_adjusted_price_ids.update(missing_for_job)
            eiv = None
            if not missing_for_job:
                eiv = sum(
                    (
                        adjusted_price_by_type[material.type_id]
                        * Decimal(material.quantity)
                        * Decimal(step.runs)
                        for material in step.recipe.materials
                    ),
                    start=ZERO,
                )
                eiv_total += eiv
            else:
                all_eiv_complete = False

            activity_fees = inputs.fees.for_recipe(
                step.recipe.key,
                step.recipe.activity,
            )
            index_key = (
                activity_fees.solar_system_id,
                step.recipe.activity,
            )
            system_cost_index = index_by_key.get(index_key)
            # A zero EIV makes every installation-fee term zero regardless of
            # the system index. This matters for legitimate zero-input jobs and
            # zero adjusted prices; do not make an otherwise exact result look
            # incomplete merely because that irrelevant index is absent.
            missing_system_cost_index = (
                system_cost_index is None and eiv != ZERO
            )
            if missing_system_cost_index:
                missing_index_keys.add(index_key)

            job_cost_modifier = modifier_by_recipe.get(
                step.recipe.key,
                activity_fees.default_job_cost_modifier,
            )
            installation_rate = None
            installation_cost = None
            if eiv == ZERO:
                installation_cost = ZERO
                installation_total += installation_cost
            elif eiv is not None and system_cost_index is not None:
                installation_rate = (
                    system_cost_index * job_cost_modifier
                    + activity_fees.facility_tax_rate
                    + activity_fees.scc_surcharge_rate
                )
                installation_cost = eiv * installation_rate
                installation_total += installation_cost
            else:
                all_installation_complete = False

            job_costs.append(
                JobCostEstimate(
                    product_type_id=step.product_type_id,
                    recipe_key=step.recipe.key,
                    activity=step.recipe.activity,
                    solar_system_id=activity_fees.solar_system_id,
                    runs=step.runs,
                    estimated_item_value=eiv,
                    system_cost_index=system_cost_index,
                    job_cost_modifier=job_cost_modifier,
                    installation_rate=installation_rate,
                    installation_cost=installation_cost,
                    missing_adjusted_price_type_ids=missing_for_job,
                    missing_system_cost_index=missing_system_cost_index,
                )
            )

        job_by_recipe = {job.recipe_key: job for job in job_costs}
        comparisons: list[StepBuildBuyComparison] = []
        for step in plan.build_steps:
            direct_inputs, direct_input_cost = _value_items(
                tuple(
                    (material.type_id, material.quantity)
                    for material in step.inputs
                ),
                best_sell_by_type,
                best_sell_volume_by_type,
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

            buy_unit_price = best_sell_by_type.get(step.product_type_id)
            buy_available_volume = best_sell_volume_by_type.get(
                step.product_type_id
            )
            has_buy_liquidity = (
                buy_unit_price is not None
                and buy_available_volume is not None
                and buy_available_volume >= step.required_quantity
            )
            direct_buy_cost = (
                buy_unit_price * Decimal(step.required_quantity)
                if has_buy_liquidity
                else None
            )
            surplus_market_value = ZERO if step.surplus_quantity == 0 else None
            surplus_net_value = ZERO if step.surplus_quantity == 0 else None
            missing_surplus_buy_quote = False
            insufficient_surplus_buy_liquidity = False
            if step.surplus_quantity:
                surplus_unit_price = best_buy_by_type.get(step.product_type_id)
                surplus_available_volume = best_buy_volume_by_type.get(
                    step.product_type_id
                )
                if surplus_unit_price is None:
                    missing_surplus_buy_quote = True
                elif (
                    surplus_available_volume is None
                    or surplus_available_volume < step.surplus_quantity
                ):
                    insufficient_surplus_buy_liquidity = True
                else:
                    surplus_market_value = (
                        surplus_unit_price * Decimal(step.surplus_quantity)
                    )
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

            missing_comparison_quotes = set(
                direct_input_cost.missing_type_ids
            )
            insufficient_comparison_liquidity = set(
                direct_input_cost.insufficient_liquidity_type_ids
            )
            if buy_unit_price is None:
                missing_comparison_quotes.add(step.product_type_id)
            elif not has_buy_liquidity:
                insufficient_comparison_liquidity.add(step.product_type_id)
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
                    buy_unit_price=buy_unit_price,
                    direct_buy_cost=direct_buy_cost,
                    savings_if_built=savings_if_built,
                    lower_cost_option=lower_cost_option,
                    missing_sell_quote_type_ids=tuple(
                        sorted(missing_comparison_quotes)
                    ),
                    insufficient_sell_liquidity_type_ids=tuple(
                        sorted(insufficient_comparison_liquidity)
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
            sales_tax = (
                requested_output_value.amount * inputs.fees.sales_tax_rate
            )
            broker_fee = (
                requested_output_value.amount * inputs.fees.broker_fee_rate
            )
            transaction_fees_total = sales_tax + broker_fee
            net_output_value = (
                requested_output_value.amount - transaction_fees_total
            )

        installation_cost_total = (
            installation_total if all_installation_complete else None
        )
        estimated_item_value_total = eiv_total if all_eiv_complete else None
        total_cost = None
        profit = None
        profit_margin = None
        if (
            shopping_cost.amount is not None
            and installation_cost_total is not None
            and transaction_fees_total is not None
            and requested_output_value.amount is not None
        ):
            total_cost = (
                shopping_cost.amount
                + installation_cost_total
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
            and installation_cost_total is not None
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
                + installation_cost_total
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
            adjusted_price_type_ids=tuple(
                sorted(missing_adjusted_price_ids)
            ),
            system_cost_index_keys=tuple(
                sorted(
                    missing_index_keys,
                    key=lambda key: (key[0], key[1].value),
                )
            ),
        )

        economics = IndustryEconomics(
            shopping_list=shopping_list,
            shopping_list_cost=shopping_cost,
            requested_outputs=requested_outputs,
            requested_output_value=requested_output_value,
            surplus_inventory=surplus_inventory,
            surplus_inventory_value=surplus_inventory_value,
            marketable_inventory=marketable_inventory,
            marketable_inventory_value=marketable_inventory_value,
            job_costs=tuple(job_costs),
            estimated_item_value_total=estimated_item_value_total,
            installation_cost_total=installation_cost_total,
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
        from app.industry.inventory_valuation import apply_inventory_valuation

        return apply_inventory_valuation(
            plan, inputs, economics,
            lambda quantities: _value_items(quantities, best_sell_by_type, best_sell_volume_by_type),
        )
