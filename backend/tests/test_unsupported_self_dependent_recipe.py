import asyncio
import json

import pytest

from app.api.errors import industry_error_handler
from app.industry.errors import RecipeCycleError, UnsupportedSelfDependentRecipeError
from app.industry.models import (
    ActivityKind,
    BuildChoice,
    BuildDecision,
    IndustryRecipe,
    ItemQuantity,
    PurchaseReason,
    RecipeKey,
)
from app.industry.planner import plan_production


def _recipe(
    blueprint_type_id: int,
    product_type_id: int,
    materials: tuple[tuple[int, int], ...],
) -> IndustryRecipe:
    return IndustryRecipe(
        key=RecipeKey(blueprint_type_id, 1),
        blueprint_name=f"Blueprint {blueprint_type_id}",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(product_type_id, 1),),
        materials=tuple(ItemQuantity(type_id, quantity) for type_id, quantity in materials),
    )


def test_self_dependent_blueprint_is_rejected_before_cycle_detection() -> None:
    recipe = _recipe(2742, 25270, ((25270, 1),))

    with pytest.raises(UnsupportedSelfDependentRecipeError) as error:
        plan_production(
            (ItemQuantity(25270, 1),),
            (recipe,),
            sde_build_number=3_473_160,
        )

    assert error.value.recipe_key == recipe.key
    assert error.value.product_type_id == 25270


def test_buy_override_does_not_try_to_use_self_dependent_blueprint() -> None:
    recipe = _recipe(2742, 25270, ((25270, 1),))

    plan = plan_production(
        (ItemQuantity(25270, 2),),
        (recipe,),
        sde_build_number=3_473_160,
        choices={25270: BuildChoice(decision=BuildDecision.BUY)},
    )

    assert plan.build_steps == ()
    assert [(item.type_id, item.quantity, item.reason) for item in plan.purchases] == [
        (25270, 2, PurchaseReason.BUY_OVERRIDE)
    ]


def test_real_multi_recipe_cycle_still_uses_cycle_error() -> None:
    first = _recipe(5001, 1001, ((1002, 1),))
    second = _recipe(5002, 1002, ((1001, 1),))

    with pytest.raises(RecipeCycleError):
        plan_production(
            (ItemQuantity(1001, 1),),
            (first, second),
            sde_build_number=1,
        )


def test_api_maps_self_dependent_blueprint_to_specific_409() -> None:
    error = UnsupportedSelfDependentRecipeError(RecipeKey(2742, 1), 25270)
    error.attach_sde_build_number(3_473_160)

    response = asyncio.run(industry_error_handler(None, error))
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload == {
        "error": {
            "code": "unsupported_self_dependent_recipe",
            "message": str(error),
            "details": {
                "product_type_id": 25270,
                "recipe_key": {
                    "blueprint_type_id": 2742,
                    "activity_id": 1,
                },
            },
        },
        "sde_build_number": 3_473_160,
    }
