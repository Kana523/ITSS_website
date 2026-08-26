from fractions import Fraction

import pytest

from app.industry.errors import QuantityTooLargeError
from app.industry.models import (
    ActivityKind,
    BlueprintEfficiency,
    FacilityModifier,
    IndustryRecipe,
    ItemQuantity,
    MAX_SAFE_INTEGER,
    ProductionProfile,
    RecipeKey,
    RigModifier,
)
from app.industry.planner import plan_production


def _recipe(
    *,
    max_runs: int | None = None,
    time_seconds: int = 60,
    material_quantity: int = 3,
) -> IndustryRecipe:
    return IndustryRecipe(
        key=RecipeKey(1000, 1),
        blueprint_name="Test Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=time_seconds,
        max_production_limit=max_runs,
        products=(ItemQuantity(100, 1),),
        materials=(ItemQuantity(200, material_quantity),),
    )


def test_owned_leaf_materials_reduce_shopping_quantity() -> None:
    plan = plan_production(
        (ItemQuantity(100, 5),),
        (_recipe(),),
        sde_build_number=1,
        owned_materials={200: 4},
    )

    assert len(plan.build_steps) == 1
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 15),)
    assert len(plan.purchases) == 1
    assert plan.purchases[0].type_id == 200
    assert plan.purchases[0].quantity == 11


def test_owned_intermediate_reduces_the_number_of_jobs_needed() -> None:
    component = IndustryRecipe(
        key=RecipeKey(2000, 1),
        blueprint_name="Component Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=10,
        max_production_limit=None,
        products=(ItemQuantity(200, 1),),
        materials=(ItemQuantity(300, 2),),
    )
    final = IndustryRecipe(
        key=RecipeKey(1000, 1),
        blueprint_name="Final Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=20,
        max_production_limit=None,
        products=(ItemQuantity(100, 1),),
        materials=(ItemQuantity(200, 1),),
    )

    plan = plan_production(
        (ItemQuantity(100, 5),),
        (component, final),
        sde_build_number=1,
        owned_materials={200: 2},
    )

    component_step = next(
        step for step in plan.build_steps if step.product_type_id == 200
    )
    assert component_step.required_quantity == 3
    assert component_step.runs == 3
    assert plan.purchases[0].type_id == 300
    assert plan.purchases[0].quantity == 6


def test_sde_copy_limit_does_not_split_an_unspecified_bpo_job() -> None:
    key = RecipeKey(1000, 1)
    plan = plan_production(
        (ItemQuantity(100, 5),),
        (_recipe(max_runs=2),),
        sde_build_number=1,
        blueprint_efficiencies={
            key: BlueprintEfficiency(material_efficiency=10, time_efficiency=0)
        },
    )

    # A BPO-backed five-run job rounds once: ceil(3 * 5 * .9) = 14.
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 14),)
    assert plan.purchases[0].quantity == 14


def test_explicit_blueprint_copy_limit_splits_before_material_rounding() -> None:
    key = RecipeKey(1000, 1)
    plan = plan_production(
        (ItemQuantity(100, 5),),
        (_recipe(max_runs=2),),
        sde_build_number=1,
        blueprint_efficiencies={
            key: BlueprintEfficiency(material_efficiency=10, time_efficiency=0)
        },
        blueprint_copy_run_limits={key: 2},
    )

    # Five runs are split 2 + 2 + 1. Each job is rounded independently:
    # ceil(3 * 2 * .9) + ceil(3 * 2 * .9) + ceil(3 * 1 * .9) = 6 + 6 + 3.
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 15),)
    assert plan.purchases[0].quantity == 15


def test_copy_splitting_is_constant_time_for_maximum_safe_run_count() -> None:
    key = RecipeKey(1000, 1)
    recipe = _recipe(
        max_runs=1,
        time_seconds=1,
        material_quantity=1,
    )

    plan = plan_production(
        (ItemQuantity(100, MAX_SAFE_INTEGER),),
        (recipe,),
        sde_build_number=1,
        blueprint_copy_run_limits={key: 1},
    )

    assert plan.build_steps[0].runs == MAX_SAFE_INTEGER
    assert plan.build_steps[0].inputs == (
        ItemQuantity(200, MAX_SAFE_INTEGER),
    )


def test_thirty_day_job_limit_rounds_materials_once_per_job() -> None:
    profile = ProductionProfile(
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=300,
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(100, 61),),
        (_recipe(time_seconds=24 * 60 * 60, material_quantity=2),),
        sde_build_number=1,
        production_profile=profile,
    )

    # Jobs are 30 + 30 + 1 runs. Each 30-run job needs ceil(60 * .97) = 59.
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 120),)


def test_thirty_day_limit_uses_final_implant_adjusted_time() -> None:
    profile = ProductionProfile(
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=162,
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(100, 300),),
        (_recipe(time_seconds=24 * 60 * 60, material_quantity=2),),
        sde_build_number=1,
        production_profile=profile,
        manufacturing_time_multiplier=Fraction(24, 25),
    )

    # The 4% implant permits 31 runs per job instead of 30.
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 591),)
    assert plan.build_steps[0].exact_job_time_seconds == Fraction(
        300 * 24 * 60 * 60 * 24,
        25,
    )


def test_oversized_base_input_quantity_is_a_domain_error() -> None:
    key = RecipeKey(1000, 1)
    profile = ProductionProfile(
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=9_999,
            ),
        ),
        rig_modifiers=(
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=9_999,
            ),
        ),
    )

    with pytest.raises(QuantityTooLargeError) as raised:
        plan_production(
            (ItemQuantity(100, MAX_SAFE_INTEGER),),
            (_recipe(time_seconds=1, material_quantity=2),),
            sde_build_number=1,
            production_profile=profile,
        )

    assert raised.value.field_name == "Base input quantity for type 200"
