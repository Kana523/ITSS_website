from app.industry.models import (
    ActivityKind,
    BlueprintEfficiency,
    IndustryRecipe,
    ItemQuantity,
    RecipeKey,
)
from app.industry.planner import plan_production


def _recipe(*, max_runs: int | None = None) -> IndustryRecipe:
    return IndustryRecipe(
        key=RecipeKey(1000, 1),
        blueprint_name="Test Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=max_runs,
        products=(ItemQuantity(100, 1),),
        materials=(ItemQuantity(200, 3),),
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

    component_step = next(step for step in plan.build_steps if step.product_type_id == 200)
    assert component_step.required_quantity == 3
    assert component_step.runs == 3
    assert plan.purchases[0].type_id == 300
    assert plan.purchases[0].quantity == 6


def test_blueprint_copy_limit_splits_jobs_before_material_rounding() -> None:
    key = RecipeKey(1000, 1)
    plan = plan_production(
        (ItemQuantity(100, 5),),
        (_recipe(max_runs=2),),
        sde_build_number=1,
        blueprint_efficiencies={
            key: BlueprintEfficiency(material_efficiency=10, time_efficiency=0)
        },
    )

    # Five runs are split 2 + 2 + 1. Each job is rounded independently:
    # ceil(3 * 2 * .9) + ceil(3 * 2 * .9) + ceil(3 * 1 * .9) = 6 + 6 + 3.
    assert plan.build_steps[0].inputs == (ItemQuantity(200, 15),)
    assert plan.purchases[0].quantity == 15
