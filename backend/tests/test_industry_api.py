from collections.abc import Collection, Iterator
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api.dependencies import get_industry_application_service
from app.industry.application import IndustryApplicationService
from app.industry.errors import (
    AmbiguousRecipeError,
    InvalidIndustryDataError,
    InvalidRecipeChoiceError,
    MissingRecipeError,
    PlanTooLargeError,
    RecipeCycleError,
    SdeNotImportedError,
    UnsupportedCoProductsError,
)
from app.industry.models import (
    ActivityKind,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    MAX_SAFE_INTEGER,
    RecipeKey,
)
from app.main import create_app


def _response_fraction(value: dict[str, str]) -> Fraction:
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def _type(
    type_id: int,
    name: str,
    *,
    published: bool = True,
) -> IndustryType:
    return IndustryType(
        type_id=type_id,
        name=name,
        published=published,
        group_id=10,
        group_name="Test Group",
        category_id=1,
        category_name="Test Category",
    )


REACTION_RECIPE = IndustryRecipe(
    key=RecipeKey(2001, 9),
    blueprint_name="Component Reaction Formula",
    activity=ActivityKind.REACTION,
    time_seconds=60,
    max_production_limit=1000,
    products=(ItemQuantity(1002, 2),),
    materials=(ItemQuantity(1001, 3),),
)
MANUFACTURING_RECIPE = IndustryRecipe(
    key=RecipeKey(2002, 1),
    blueprint_name="Final Product Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=62,
    max_production_limit=100,
    products=(ItemQuantity(1003, 1),),
    materials=(ItemQuantity(1002, 4),),
)
CYCLE_RECIPE = IndustryRecipe(
    key=RecipeKey(2004, 1),
    blueprint_name="Cycle Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=30,
    max_production_limit=10,
    products=(ItemQuantity(1004, 1),),
    materials=(ItemQuantity(1004, 1),),
)
AMBIGUOUS_RECIPE_A = IndustryRecipe(
    key=RecipeKey(2005, 1),
    blueprint_name="First Ambiguous Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=30,
    max_production_limit=10,
    products=(ItemQuantity(1006, 1),),
    materials=(ItemQuantity(1001, 1),),
)
AMBIGUOUS_RECIPE_B = IndustryRecipe(
    key=RecipeKey(2006, 1),
    blueprint_name="Second Ambiguous Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=30,
    max_production_limit=10,
    products=(ItemQuantity(1006, 1),),
    materials=(ItemQuantity(1001, 2),),
)


class FakeIndustryDataRepository:
    def __init__(self) -> None:
        self.types = {
            item.type_id: item
            for item in (
                _type(1001, "Raw Resource"),
                _type(1002, "Reacted Component"),
                _type(1003, "Final Product"),
                _type(1004, "Cycle Product"),
                _type(1005, "Unpublished Product", published=False),
                _type(1006, "Ambiguous Product"),
                _type(2001, "Component Reaction Formula"),
                _type(2002, "Final Product Blueprint"),
                _type(2004, "Cycle Blueprint"),
                _type(2005, "First Ambiguous Blueprint"),
                _type(2006, "Second Ambiguous Blueprint"),
            )
        }
        self.recipes = (
            REACTION_RECIPE,
            MANUFACTURING_RECIPE,
            CYCLE_RECIPE,
            AMBIGUOUS_RECIPE_B,
            AMBIGUOUS_RECIPE_A,
        )

    def latest_sde_build_number(self) -> int | None:
        return 9_000_001

    def search_types(
        self,
        query: str,
        *,
        published_only: bool = True,
        producible_only: bool = False,
        limit: int = 20,
    ) -> tuple[IndustryType, ...]:
        producible_ids = {
            product.type_id
            for recipe in self.recipes
            for product in recipe.products
        }
        matches = tuple(
            item
            for item in sorted(self.types.values(), key=lambda item: item.type_id)
            if query.casefold() in item.name.casefold()
            and (not published_only or item.published)
            and (not producible_only or item.type_id in producible_ids)
        )
        return matches[:limit]

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        return {
            type_id: self.types[type_id]
            for type_id in type_ids
            if type_id in self.types
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        return {
            type_id: tuple(
                recipe
                for recipe in self.recipes
                if recipe.output_quantity_for(type_id) is not None
            )
            for type_id in product_type_ids
        }


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    application = create_app()
    service = IndustryApplicationService(FakeIndustryDataRepository())
    application.dependency_overrides[get_industry_application_service] = (
        lambda: service
    )
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


def test_type_search_contract(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/industry/types",
        params={"search": "Final", "producible_only": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "sde_build_number": 9_000_001,
        "query": "Final",
        "result_count": 1,
        "limit": 20,
        "items": [
            {
                "type_id": 1003,
                "name": "Final Product",
                "published": True,
                "group_id": 10,
                "group_name": "Test Group",
                "category_id": 1,
                "category_name": "Test Category",
            }
        ],
    }


def test_recipe_detail_contract_and_empty_recipe_list(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/industry/recipes/1003")

    assert response.status_code == 200
    body = response.json()
    assert body["sde_build_number"] == 9_000_001
    assert body["product"]["name"] == "Final Product"
    assert body["recipes"][0]["recipe_key"] == {
        "blueprint_type_id": 2002,
        "activity_id": 1,
    }
    assert body["recipes"][0]["materials"] == [
        {
            "item": {"type_id": 1002, "name": "Reacted Component"},
            "quantity_per_run": 4,
        }
    ]
    assert body["recipes"][0]["planning_limitations"] == []

    cycle_response = api_client.get("/api/industry/recipes/1004")
    assert cycle_response.status_code == 200
    assert cycle_response.json()["recipes"][0]["planning_limitations"] == [
        "self_dependency"
    ]

    raw_response = api_client.get("/api/industry/recipes/1001")
    assert raw_response.status_code == 200
    assert raw_response.json()["recipes"] == []


def test_calculation_contract_aggregates_demands_and_honors_buy(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [
                {"type_id": 1003, "quantity": 1},
                {"type_id": 1003, "quantity": 2},
            ],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "expected_sde_build_number": 9_000_001,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sde_build_number"] == 9_000_001
    assert body["calculation_basis"] == "sde_base_quantities"
    assert body["applied_modifiers"] == []
    assert body["requested"] == [
        {
            "item": {"type_id": 1003, "name": "Final Product"},
            "quantity": 3,
        }
    ]
    assert len(body["build_steps"]) == 1
    step = body["build_steps"][0]
    assert step["product"]["type_id"] == 1003
    assert step["runs"] == 3
    assert step["blueprint_efficiency"] == {
        "material_efficiency": 0,
        "time_efficiency": 0,
    }
    assert step["base_total_job_time_seconds"] == 186
    assert step["display_job_time_seconds"] == 186
    assert step["exact_job_time_seconds"] == {
        "numerator": "186",
        "denominator": "1",
    }
    assert step["total_job_time_centiseconds"] == "18600"
    assert step["production_modifiers"] == {
        "skills": {
            "industry_level": 0,
            "advanced_industry_level": 0,
            "reactions_level": 0,
        },
        "character_time_multiplier": {"numerator": "1", "denominator": "1"},
        "facility_material_reduction_basis_points": 0,
        "facility_time_reduction_basis_points": 0,
        "rig_material_reduction_basis_points": 0,
        "rig_time_reduction_basis_points": 0,
        "facility_material_multiplier": {"numerator": "1", "denominator": "1"},
        "facility_time_multiplier": {"numerator": "1", "denominator": "1"},
        "rig_material_multiplier": {"numerator": "1", "denominator": "1"},
        "rig_time_multiplier": {"numerator": "1", "denominator": "1"},
        "material_multiplier": {"numerator": "1", "denominator": "1"},
        "time_multiplier": {"numerator": "1", "denominator": "1"},
    }
    assert step["inputs"][0] == {
        "item": {"type_id": 1002, "name": "Reacted Component"},
        "quantity_per_run": 4,
        "base_total_quantity": 12,
        "total_quantity": 12,
    }
    assert body["purchases"] == [
        {
            "item": {"type_id": 1002, "name": "Reacted Component"},
            "quantity": 12,
            "reason": "buy_override",
        }
    ]


def test_calculation_applies_blueprint_me_te_exactly(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 3}],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_modifiers"] == [
        "blueprint_material_efficiency",
        "blueprint_time_efficiency",
    ]
    step = body["build_steps"][0]
    assert step["blueprint_efficiency"] == {
        "material_efficiency": 10,
        "time_efficiency": 20,
    }
    assert step["inputs"][0]["base_total_quantity"] == 12
    assert step["inputs"][0]["total_quantity"] == 11
    assert step["base_total_job_time_seconds"] == 186
    assert step["exact_job_time_seconds"] == {
        "numerator": "744",
        "denominator": "5",
    }
    assert step["total_job_time_centiseconds"] == "14880"
    assert step["display_job_time_seconds"] == 148
    assert body["purchases"][0]["quantity"] == 11


def test_calculation_applies_exact_manufacturing_production_profile(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 3}],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            ],
            "production_profile": {
                "industry_level": 5,
                "advanced_industry_level": 5,
                "reactions_level": 5,
                "facility_modifiers": [
                    {
                        "activity": "manufacturing",
                        "material_reduction_basis_points": 100,
                        "time_reduction_basis_points": 1500,
                    }
                ],
                "rig_modifiers": [
                    {
                        "activity": "manufacturing",
                        "material_reduction_basis_points": 504,
                        "time_reduction_basis_points": 5040,
                        "category_ids": [1],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_modifiers"] == [
        "blueprint_material_efficiency",
        "blueprint_time_efficiency",
        "industry_skill_time",
        "advanced_industry_skill_time",
        "facility_material_efficiency",
        "facility_time_efficiency",
        "rig_material_efficiency",
        "rig_time_efficiency",
    ]
    step = body["build_steps"][0]
    assert step["inputs"][0]["base_total_quantity"] == 12
    assert step["inputs"][0]["total_quantity"] == 11
    assert step["production_modifiers"]["skills"] == {
        "industry_level": 5,
        "advanced_industry_level": 5,
        "reactions_level": 5,
    }
    assert _response_fraction(
        step["production_modifiers"]["character_time_multiplier"]
    ) == Fraction(17, 25)
    assert _response_fraction(
        step["production_modifiers"]["material_multiplier"]
    ) == Fraction(117_513, 125_000)
    expected_time = (
        Fraction(186)
        * Fraction(80, 100)
        * Fraction(80, 100)
        * Fraction(85, 100)
        * Fraction(85, 100)
        * Fraction(4_960, 10_000)
    )
    assert _response_fraction(step["exact_job_time_seconds"]) == expected_time
    assert step["display_job_time_seconds"] == 42
    assert step["total_job_time_centiseconds"] is None


def test_reaction_profile_uses_only_reaction_time_skill(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1002, "quantity": 1}],
            "production_profile": {
                "industry_level": 5,
                "advanced_industry_level": 5,
                "reactions_level": 5,
                "facility_modifiers": [
                    {
                        "activity": "reaction",
                        "material_reduction_basis_points": 100,
                        "time_reduction_basis_points": 2500,
                    }
                ],
                "rig_modifiers": [
                    {
                        "activity": "reaction",
                        "material_reduction_basis_points": 264,
                        "time_reduction_basis_points": 2640,
                        "group_ids": [10],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_modifiers"] == [
        "reactions_skill_time",
        "facility_material_efficiency",
        "facility_time_efficiency",
        "rig_material_efficiency",
        "rig_time_efficiency",
    ]
    step = body["build_steps"][0]
    assert step["activity"] == "reaction"
    assert step["blueprint_efficiency"] is None
    assert step["inputs"][0]["total_quantity"] == 3
    assert _response_fraction(
        step["production_modifiers"]["character_time_multiplier"]
    ) == Fraction(4, 5)
    assert _response_fraction(step["exact_job_time_seconds"]) == (
        Fraction(60)
        * Fraction(4, 5)
        * Fraction(3, 4)
        * Fraction(736, 1000)
    )
    assert step["total_job_time_centiseconds"] is None


@pytest.mark.parametrize(
    ("material_efficiency", "time_efficiency", "expected_modifiers"),
    [
        (10, 0, ["blueprint_material_efficiency"]),
        (0, 20, ["blueprint_time_efficiency"]),
    ],
)
def test_calculation_reports_only_nonzero_blueprint_modifiers(
    api_client: TestClient,
    material_efficiency: int,
    time_efficiency: int,
    expected_modifiers: list[str],
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": material_efficiency,
                    "time_efficiency": time_efficiency,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["applied_modifiers"] == expected_modifiers


@pytest.mark.parametrize(
    "body",
    [
        {"demands": [{"type_id": "1003", "quantity": 1}]},
        {"demands": [{"type_id": True, "quantity": 1}]},
        {"demands": [{"type_id": 1003, "quantity": 0}]},
        {
            "demands": [
                {"type_id": 1003, "quantity": MAX_SAFE_INTEGER + 1}
            ]
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "choices": [
                {"type_id": 1002, "decision": "buy"},
                {"type_id": 1002, "decision": "build"},
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "choices": [
                {
                    "type_id": 1002,
                    "decision": "buy",
                    "recipe_key": {
                        "blueprint_type_id": 2001,
                        "activity_id": 9,
                    },
                }
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "unexpected": True,
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 11,
                    "time_efficiency": 20,
                }
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": True,
                    "time_efficiency": 20,
                }
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 3,
                }
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                },
                {
                    "recipe_key": {
                        "blueprint_type_id": 2002,
                        "activity_id": 1,
                    },
                    "material_efficiency": 0,
                    "time_efficiency": 0,
                },
            ],
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {"industry_level": 6},
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {"reactions_level": True},
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {
                "facility_modifiers": [
                    {
                        "activity": "manufacturing",
                        "time_reduction_basis_points": 10_000,
                    }
                ]
            },
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {
                "facility_modifiers": [
                    {
                        "activity": "manufacturing",
                        "time_reduction_basis_points": 100,
                    },
                    {
                        "activity": "manufacturing",
                        "material_reduction_basis_points": 100,
                    },
                ]
            },
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {
                "rig_modifiers": [
                    {
                        "activity": "manufacturing",
                        "time_reduction_basis_points": 100,
                        "category_ids": [1, 1],
                    }
                ]
            },
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {
                "rig_modifiers": [
                    {
                        "activity": "manufacturing",
                        "time_reduction_basis_points": 100,
                        "group_ids": [0],
                    }
                ]
            },
        },
        {
            "demands": [{"type_id": 1003, "quantity": 1}],
            "production_profile": {
                "rig_modifiers": [{"activity": "manufacturing"}]
            },
        },
    ],
)
def test_calculation_request_validation(
    api_client: TestClient,
    body: dict,
) -> None:
    response = api_client.post("/api/industry/calculate", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_overlapping_rig_scopes_have_a_structured_error(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "choices": [{"type_id": 1002, "decision": "buy"}],
            "production_profile": {
                "rig_modifiers": [
                    {
                        "activity": "manufacturing",
                        "material_reduction_basis_points": 200,
                        "category_ids": [1],
                    },
                    {
                        "activity": "manufacturing",
                        "material_reduction_basis_points": 240,
                        "group_ids": [10],
                    },
                ]
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "conflicting_rig_modifiers",
            "message": (
                "Multiple rig modifiers affect material requirements for "
                "recipe 2002:1"
            ),
            "details": {
                "recipe_key": {
                    "blueprint_type_id": 2002,
                    "activity_id": 1,
                },
                "dimension": "material requirements",
            },
        },
        "sde_build_number": 9_000_001,
    }


def test_query_and_path_validation_use_error_envelope(
    api_client: TestClient,
) -> None:
    for path in (
        "/api/industry/types?search=%20%20%20",
        "/api/industry/types?search=test&limit=101",
        "/api/industry/recipes/0",
    ):
        response = api_client.get(path)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_unknown_type_and_sde_version_errors(api_client: TestClient) -> None:
    missing = api_client.get("/api/industry/recipes/9999")
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "unknown_type",
        "message": "Unknown EVE type ID(s): 9999",
        "details": {"type_ids": [9999]},
    }
    assert missing.json()["sde_build_number"] == 9_000_001

    mismatch = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "expected_sde_build_number": 8_000_000,
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "sde_version_mismatch"
    assert mismatch.json()["error"]["details"] == {
        "expected_sde_build_number": 8_000_000,
        "current_sde_build_number": 9_000_001,
    }
    assert mismatch.json()["sde_build_number"] == 9_000_001


def test_expected_sde_build_number_accepts_bigint_values(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "expected_sde_build_number": 3_000_000_000,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sde_version_mismatch"


def test_unpublished_public_targets_are_rejected(api_client: TestClient) -> None:
    recipe_response = api_client.get("/api/industry/recipes/1005")
    assert recipe_response.status_code == 404
    assert recipe_response.json()["error"]["code"] == "unknown_type"

    calculation_response = api_client.post(
        "/api/industry/calculate",
        json={"demands": [{"type_id": 1005, "quantity": 1}]},
    )
    assert calculation_response.status_code == 422
    assert calculation_response.json()["error"]["code"] == "unpublished_type"
    assert calculation_response.json()["sde_build_number"] == 9_000_001


def test_cycle_error_is_structured(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={"demands": [{"type_id": 1004, "quantity": 1}]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "recipe_cycle"
    assert response.json()["error"]["details"]["type_path"] == [1004, 1004]
    assert response.json()["sde_build_number"] == 9_000_001


def test_ambiguous_recipe_error_has_sorted_candidates_and_sde_build(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/industry/calculate",
        json={"demands": [{"type_id": 1006, "quantity": 1}]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ambiguous_recipe"
    assert response.json()["error"]["details"]["candidates"] == [
        {"blueprint_type_id": 2005, "activity_id": 1},
        {"blueprint_type_id": 2006, "activity_id": 1},
    ]
    assert response.json()["sde_build_number"] == 9_000_001


def test_unused_choice_and_computed_quantity_limit_are_structured(
    api_client: TestClient,
) -> None:
    unused = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "choices": [{"type_id": 9999, "decision": "buy"}],
        },
    )
    assert unused.status_code == 422
    assert unused.json()["error"]["code"] == "unused_build_choices"
    assert unused.json()["error"]["details"] == {"type_ids": [9999]}
    assert unused.json()["sde_build_number"] == 9_000_001

    too_large = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [
                {"type_id": 1003, "quantity": MAX_SAFE_INTEGER}
            ]
        },
    )
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "quantity_too_large"
    assert too_large.json()["error"]["details"]["maximum_safe_integer"] == (
        MAX_SAFE_INTEGER
    )
    assert too_large.json()["sde_build_number"] == 9_000_001


def test_blueprint_efficiency_errors_are_structured(
    api_client: TestClient,
) -> None:
    unused = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1003, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 9999,
                        "activity_id": 1,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            ],
        },
    )
    assert unused.status_code == 422
    assert unused.json()["error"]["code"] == (
        "unused_blueprint_efficiencies"
    )
    assert unused.json()["error"]["details"] == {
        "recipe_keys": [
            {"blueprint_type_id": 9999, "activity_id": 1}
        ]
    }

    reaction = api_client.post(
        "/api/industry/calculate",
        json={
            "demands": [{"type_id": 1002, "quantity": 1}],
            "blueprint_efficiencies": [
                {
                    "recipe_key": {
                        "blueprint_type_id": 2001,
                        "activity_id": 9,
                    },
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            ],
        },
    )
    assert reaction.status_code == 422
    assert reaction.json()["error"]["code"] == (
        "blueprint_efficiency_not_applicable"
    )
    assert reaction.json()["error"]["details"]["activity"] == "reaction"


class RaisingIndustryService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create_plan(self, *_args, **_kwargs):
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            AmbiguousRecipeError(1003, (RecipeKey(2001, 1), RecipeKey(2002, 1))),
            409,
            "ambiguous_recipe",
        ),
        (MissingRecipeError(1003), 409, "missing_recipe"),
        (
            InvalidRecipeChoiceError(1003, RecipeKey(2001, 1)),
            409,
            "invalid_recipe_choice",
        ),
        (
            UnsupportedCoProductsError(RecipeKey(2001, 1)),
            409,
            "unsupported_co_products",
        ),
        (PlanTooLargeError(5_000), 422, "plan_too_large"),
        (SdeNotImportedError("No SDE"), 503, "sde_not_imported"),
        (
            InvalidIndustryDataError("postgresql+psycopg://secret"),
            500,
            "industry_data_error",
        ),
    ],
)
def test_domain_error_mapping(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    application = create_app()
    application.dependency_overrides[get_industry_application_service] = (
        lambda: RaisingIndustryService(error)
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/industry/calculate",
            json={"demands": [{"type_id": 1003, "quantity": 1}]},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert "postgresql" not in response.text


def test_database_operational_error_does_not_leak_details() -> None:
    error = OperationalError(
        "SELECT secret",
        {"password": "secret"},
        Exception("database secret"),
    )
    application = create_app()
    application.dependency_overrides[get_industry_application_service] = (
        lambda: RaisingIndustryService(error)
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/industry/calculate",
            json={"demands": [{"type_id": 1003, "quantity": 1}]},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "secret" not in response.text


def test_generic_database_error_uses_json_envelope_without_details() -> None:
    error = SQLAlchemyError("postgresql+psycopg://secret")
    application = create_app()
    application.dependency_overrides[get_industry_application_service] = (
        lambda: RaisingIndustryService(error)
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/industry/calculate",
            json={"demands": [{"type_id": 1003, "quantity": 1}]},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "database_error"
    assert "secret" not in response.text


def test_openapi_documents_the_shared_error_envelope() -> None:
    schema = create_app().openapi()
    responses = schema["paths"]["/api/industry/recipes/{product_type_id}"][
        "get"
    ]["responses"]

    for status_code in ("422", "500"):
        response_schema = responses[status_code]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith("/ErrorResponse")


def test_cors_allows_only_the_configured_frontend_origin() -> None:
    application = create_app(
        cors_origins=("http://127.0.0.1:5500",),
    )
    preflight_headers = {
        "Origin": "http://127.0.0.1:5500",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    with TestClient(application) as client:
        allowed = client.options(
            "/api/industry/calculate",
            headers=preflight_headers,
        )
        rejected = client.options(
            "/api/industry/calculate",
            headers={
                **preflight_headers,
                "Origin": "https://untrusted.example",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5500"
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
