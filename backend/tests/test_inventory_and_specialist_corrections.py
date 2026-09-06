from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_industry_application_service
from app.industry.application import IndustryApplicationService
from app.industry.depth_valuation import MarketDepthQuote, calculate_depth_aware_industry_economics
from app.industry.models import (
    ActivityKind, CharacterIndustrySkills, FacilityModifier, IndustryRecipe,
    IndustryType, ItemQuantity, ProductionPlan, ProductionProfile, RecipeKey,
    PurchaseRequirement, PurchaseReason,
)
from app.industry.planner import plan_production
from app.industry.service import IndustryPlanningService
from app.industry.specialist_skills import MissingSpecialistSkillsError, SpecialistSkillRequirement
from app.industry.valuation import (
    AdjustedPriceSnapshot, IndustryFeeRates, IndustryValuationInputs,
    InventoryValuationMethod, MarketQuote, MarketQuoteSnapshot,
    RecordedInventoryCost, SystemCostIndexSnapshot, calculate_industry_economics,
)
from app.main import create_app
from app.market.domain import MarketPriceLevel


def recipe(product=100, material=200, *, seconds=60, activity=ActivityKind.MANUFACTURING):
    return IndustryRecipe(
        key=RecipeKey(product + 1000, 1 if activity == ActivityKind.MANUFACTURING else 9),
        blueprint_name="Test blueprint", activity=activity, time_seconds=seconds,
        max_production_limit=None, products=(ItemQuantity(product, 1),),
        materials=(ItemQuantity(material, 3),),
    )


class Repository:
    def __init__(self, recipes, requirements):
        self.recipes = recipes
        self.requirements = requirements

    def latest_sde_build_number(self):
        return 1

    def load_types(self, ids):
        return {i: IndustryType(i, f"Type {i}", True, 1, "Group", 1, "Category") for i in ids}

    def load_recipes_for_products(self, ids):
        return {i: tuple(r for r in self.recipes if r.products[0].type_id == i) for i in ids}

    def load_recipe_skill_requirements(self, keys):
        return {key: self.requirements.get(key, ()) for key in keys}


def test_specialist_levels_change_exact_time_and_api_breakdown():
    r = recipe()
    repository = Repository((r,), {r.key: (SpecialistSkillRequirement(11443, 4),)})
    service = IndustryPlanningService(repository)
    profile = ProductionProfile(skills=CharacterIndustrySkills(5, 5, 0))
    for level in (4, 5):
        plan = service.create_plan(
            (ItemQuantity(100, 1),), production_profile=profile,
            specialist_skill_levels={11443: level}, manufacturing_time_multiplier=Fraction(24, 25),
        )
        assert plan.build_steps[0].exact_job_time_seconds == (
            60 * Fraction(4, 5) * Fraction(17, 20) * Fraction(100 - level, 100) * Fraction(24, 25)
        )

    app = create_app()
    app.dependency_overrides[get_industry_application_service] = lambda: IndustryApplicationService(repository)
    with TestClient(app) as client:
        response = client.post("/api/industry/calculate", json={
            "demands": [{"type_id": 100, "quantity": 1}],
            "specialist_skills": [{"type_id": 11443, "level": 5}],
            "production_profile": {"manufacturing_time_implant": 27170},
        })
    assert response.status_code == 200, response.text
    body = response.json()
    modifiers = body["build_steps"][0]["production_modifiers"]
    assert "specialist_skill_time" in body["applied_modifiers"]
    assert modifiers["specialist_time_multiplier"] == {"numerator": "19", "denominator": "20"}
    assert modifiers["specialist_skills"][0]["type_id"] == 11443
    multiplier = modifiers["time_multiplier"]
    duration = body["build_steps"][0]["exact_job_time_seconds"]
    assert Fraction(int(duration["numerator"]), int(duration["denominator"])) == (
        60 * Fraction(int(multiplier["numerator"]), int(multiplier["denominator"]))
    )


@pytest.mark.parametrize("activity", [ActivityKind.MANUFACTURING, ActivityKind.REACTION])
def test_only_required_bonus_skills_apply_and_reactions_are_unchanged(activity):
    r = recipe(activity=activity)
    requirements = tuple(SpecialistSkillRequirement(i, 1) for i in (3395, 11443, 81896, 3402, 22242))
    service = IndustryPlanningService(Repository((r,), {r.key: requirements}))
    plan = service.create_plan(
        (ItemQuantity(100, 1),), specialist_skill_levels={i: 5 for i in (3395, 11443, 81896, 3402, 22242, 11452)},
    )
    step = plan.build_steps[0]
    assert step.exact_job_time_seconds == (
        60 * Fraction(95, 100) ** 2 * Fraction(90, 100)
        if activity == ActivityKind.MANUFACTURING else 60
    )
    assert {s.type_id for s in step.production_modifiers.specialist_skills} == (
        {3395, 11443, 81896} if activity == ActivityKind.MANUFACTURING else set()
    )


def test_specialist_time_changes_thirty_day_splitting_and_material_rounding():
    r = recipe(seconds=15 * 86400 + 43200)
    service = IndustryPlanningService(Repository((r,), {r.key: (SpecialistSkillRequirement(11443, 1),)}))
    profile = ProductionProfile(facility_modifiers=(FacilityModifier(
        activity=ActivityKind.MANUFACTURING, material_reduction_basis_points=2000,
    ),))
    baseline = service.create_plan((ItemQuantity(100, 2),), production_profile=profile)
    skilled = service.create_plan(
        (ItemQuantity(100, 2),), production_profile=profile, specialist_skill_levels={11443: 5},
    )
    assert baseline.purchases[0].quantity == 6  # Two jobs, each rounded up.
    assert skilled.purchases[0].quantity == 5  # Both runs fit in one job.


@pytest.mark.parametrize("owned", [3, 4])
def test_owned_component_removes_its_skill_requirements_and_consumes_only_needed_units(owned):
    final, component = recipe(), recipe(200, 300)
    service = IndustryPlanningService(Repository(
        (final, component), {component.key: (SpecialistSkillRequirement(11443, 4),)},
    ))
    plan = service.create_plan(
        (ItemQuantity(100, 1),), owned_materials={200: owned, 999: 20}, specialist_skill_levels={},
    )
    assert [step.product_type_id for step in plan.build_steps] == [100]
    assert plan.consumed_inventory == (ItemQuantity(200, 3),)
    assert plan.purchases == ()


def test_partially_owned_component_still_requires_skills_and_attaches_sde_version():
    final, component = recipe(), recipe(200, 300)
    service = IndustryPlanningService(Repository(
        (final, component), {component.key: (SpecialistSkillRequirement(11443, 4),)},
    ))
    with pytest.raises(MissingSpecialistSkillsError) as error:
        service.create_plan((ItemQuantity(100, 1),), owned_materials={200: 2}, specialist_skill_levels={})
    assert error.value.missing[0][0] == component.key
    assert error.value.sde_build_number == 1


def test_fully_owned_root_needs_no_manufacturing_skills():
    r = recipe()
    service = IndustryPlanningService(Repository((r,), {r.key: (SpecialistSkillRequirement(11443, 4),)}))
    plan = service.create_plan((ItemQuantity(100, 2),), owned_materials={100: 2}, specialist_skill_levels={})
    assert plan.build_steps == ()
    assert plan.purchases == ()
    assert plan.consumed_inventory == (ItemQuantity(100, 2),)


def inputs():
    return IndustryValuationInputs(
        market=MarketQuoteSnapshot((MarketQuote(100, Decimal(20), 100, Decimal(21), 100),)),
        adjusted_prices=AdjustedPriceSnapshot(()), system_cost_indices=SystemCostIndexSnapshot(()),
        fees=IndustryFeeRates(
            solar_system_id=30000142, facility_tax_rate=Decimal(0), scc_surcharge_rate=Decimal(0),
            sales_tax_rate=Decimal("0.04"), broker_fee_rate=Decimal(0),
        ),
    )


def owned_plan():
    return plan_production((ItemQuantity(100, 6),), (), sde_build_number=1, owned_materials={100: 9})


@pytest.mark.parametrize("depth", [False, True])
def test_owned_output_has_cash_proceeds_but_not_free_inventory_profit(depth):
    plan, data = owned_plan(), inputs()
    if depth:
        result = calculate_depth_aware_industry_economics(plan, data, {
            100: MarketDepthQuote(100, (MarketPriceLevel(Decimal(20), 100),), (MarketPriceLevel(Decimal(21), 100),)),
        })
    else:
        result = calculate_industry_economics(plan, data)
    assert plan.consumed_inventory == (ItemQuantity(100, 6),)
    assert result.cash_required == 0
    assert result.cash_surplus == Decimal("115.20")
    assert result.consumed_inventory_value.amount == 126
    assert result.total_cost == Decimal("130.80")
    assert result.profit == Decimal("-10.80")
    assert result.profit_including_surplus == result.profit


def test_recorded_cost_is_exact_and_does_not_require_a_replacement_quote():
    data = replace(inputs(),
        inventory_valuation_method=InventoryValuationMethod.RECORDED_COST,
        recorded_inventory_costs=(RecordedInventoryCost(100, Decimal("10.12345678")),),
    )
    result = calculate_depth_aware_industry_economics(owned_plan(), data, {
        100: MarketDepthQuote(100, (MarketPriceLevel(Decimal(20), 6),), ()),
    })
    assert result.consumed_inventory_value.amount == Decimal("60.74074068")
    assert result.profit == Decimal("54.45925932")
    assert result.is_complete


@pytest.mark.parametrize("method", list(InventoryValuationMethod))
def test_missing_inventory_cost_preserves_cash_flow_but_blocks_profit(method):
    data = replace(inputs(), inventory_valuation_method=method)
    result = calculate_depth_aware_industry_economics(owned_plan(), data, {
        100: MarketDepthQuote(100, (MarketPriceLevel(Decimal(20), 6),), ()),
    })
    assert result.cash_required == 0
    assert result.cash_surplus == Decimal("115.20")
    assert result.profit is None
    assert result.profit_including_surplus is None
    assert result.consumed_inventory_value.amount is None
    assert result.missing_data.inventory_cost_type_ids == (100,)
    assert not result.is_complete


@pytest.mark.parametrize("available", [5, 4])
def test_replacement_valuation_reserves_purchase_depth_first(available):
    plan = ProductionPlan(1, (ItemQuantity(100, 1),), (),
        (PurchaseRequirement(200, 2, PurchaseReason.NO_RECIPE),), (ItemQuantity(200, 3),))
    result = calculate_depth_aware_industry_economics(plan, inputs(), {
        100: MarketDepthQuote(100, (MarketPriceLevel(Decimal(100), 1),), ()),
        200: MarketDepthQuote(200, (), (
            MarketPriceLevel(Decimal(10), 2), MarketPriceLevel(Decimal(20), available - 2),
        )),
    })
    assert result.cash_required == 20
    assert result.cash_surplus == 76
    if available == 5:
        assert result.consumed_inventory_value.amount == 60
        assert result.profit == 16
    else:
        assert result.consumed_inventory_value.amount is None
        assert result.profit is None
        assert result.missing_data.inventory_sell_liquidity_type_ids == (200,)
