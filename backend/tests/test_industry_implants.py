from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.industry_calculation import IndustryCalculationRequest
from app.industry.implants import (
    ManufacturingTimeImplant,
    apply_manufacturing_time_implant,
)
from app.industry.models import (
    ActivityKind,
    AppliedProductionModifiers,
    CharacterIndustrySkills,
    IndustryRecipe,
    ItemQuantity,
    ProductionPlan,
    ProductionStep,
    RecipeKey,
)
from app.industry.views import DescribedProductionPlan
from tests.test_industry_api import api_client  # noqa: F401


def _result(activity: ActivityKind) -> DescribedProductionPlan:
    recipe = IndustryRecipe(
        key=RecipeKey(9001, 1 if activity == ActivityKind.MANUFACTURING else 9),
        blueprint_name="Implant Test Blueprint",
        activity=activity,
        time_seconds=100,
        max_production_limit=100,
        products=(ItemQuantity(8001, 1),),
        materials=(ItemQuantity(7001, 10),),
    )
    step = ProductionStep(
        product_type_id=8001,
        recipe=recipe,
        required_quantity=1,
        output_per_run=1,
        runs=1,
        produced_quantity=1,
        surplus_quantity=0,
        blueprint_efficiency=None,
        production_modifiers=AppliedProductionModifiers(
            activity=activity,
            skills=CharacterIndustrySkills(),
        ),
        base_total_job_time_seconds=100,
        exact_job_time_seconds=Fraction(100),
        inputs=(ItemQuantity(7001, 10),),
    )
    plan = ProductionPlan(
        sde_build_number=1,
        requested=(ItemQuantity(8001, 1),),
        build_steps=(step,),
        purchases=(),
    )
    return DescribedProductionPlan(plan=plan, item_types=())


@pytest.mark.parametrize(
    ("implant", "expected"),
    [
        (ManufacturingTimeImplant.BX_801, Fraction(99, 1)),
        (ManufacturingTimeImplant.BX_802, Fraction(98, 1)),
        (ManufacturingTimeImplant.BX_804, Fraction(96, 1)),
    ],
)
def test_bx_implants_reduce_manufacturing_time_exactly(implant, expected) -> None:
    result = _result(ActivityKind.MANUFACTURING)
    adjusted = apply_manufacturing_time_implant(result, implant)

    assert adjusted.plan.build_steps[0].exact_job_time_seconds == expected
    assert adjusted.plan.build_steps[0].inputs == (ItemQuantity(7001, 10),)


def test_manufacturing_implant_does_not_affect_reactions() -> None:
    result = _result(ActivityKind.REACTION)
    adjusted = apply_manufacturing_time_implant(
        result,
        ManufacturingTimeImplant.BX_804,
    )

    assert adjusted.plan.build_steps[0].exact_job_time_seconds == 100


def test_request_accepts_only_supported_implant_type_ids() -> None:
    request = IndustryCalculationRequest.model_validate(
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {"manufacturing_time_implant": 27171},
        }
    )
    assert request.to_manufacturing_time_implant() == ManufacturingTimeImplant.BX_804

    with pytest.raises(ValueError):
        IndustryCalculationRequest.model_validate(
            {
                "demands": [{"type_id": 1003, "quantity": 1}],
                "production_profile": {"manufacturing_time_implant": 999999},
            }
        )


def test_api_applies_bx_804_without_changing_materials(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 3}],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "production_profile": {"manufacturing_time_implant": 27171},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_modifiers"] == ["manufacturing_implant_time"]
    step = body["build_steps"][0]
    assert step["exact_job_time_seconds"] == {
        "numerator": "4464",
        "denominator": "25",
    }
    assert step["display_job_time_seconds"] == 178
    assert step["total_job_time_centiseconds"] == "17856"
    assert step["inputs"][0]["total_quantity"] == 12
    assert step["production_modifiers"]["time_multiplier"] == {
        "numerator": "24",
        "denominator": "25",
    }
    assert "character_implants" not in body["excluded_modifiers"]


def test_api_rejects_unknown_manufacturing_implant(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {"manufacturing_time_implant": 999999},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_api_implant_does_not_affect_reaction_step(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1002, "quantity": 1}],
            "production_profile": {"manufacturing_time_implant": 27171},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_modifiers"] == []
    assert body["build_steps"][0]["activity"] == "reaction"
    assert body["build_steps"][0]["exact_job_time_seconds"] == {
        "numerator": "60",
        "denominator": "1",
    }
