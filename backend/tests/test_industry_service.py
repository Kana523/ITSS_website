from collections.abc import Collection

import pytest

from app.industry.errors import (
    SdeNotImportedError,
    UnknownTypeError,
    UnpublishedTypeError,
)
from app.industry.models import (
    ActivityKind,
    BuildChoice,
    BuildDecision,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    ProductionProfile,
    RecipeKey,
    RigModifier,
)
from app.industry.service import IndustryPlanningService


class FakeIndustryRepository:
    def __init__(
        self,
        *,
        build_number: int | None = 1,
        unpublished_type_ids: Collection[int] = (),
    ) -> None:
        self.build_number = build_number
        self.unpublished_type_ids = set(unpublished_type_ids)
        self.recipe_loads: list[frozenset[int]] = []
        self.type_loads: list[frozenset[int]] = []

    def latest_sde_build_number(self) -> int | None:
        return self.build_number

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        self.type_loads.append(frozenset(type_ids))
        return {
            type_id: IndustryType(
                type_id=type_id,
                name=f"Type {type_id}",
                published=type_id not in self.unpublished_type_ids,
                group_id=1,
                group_name="Group",
                category_id=1,
                category_name="Category",
            )
            for type_id in type_ids
            if type_id != 9999
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        self.recipe_loads.append(frozenset(product_type_ids))
        return {type_id: () for type_id in product_type_ids}


def test_service_requires_imported_sde() -> None:
    service = IndustryPlanningService(
        FakeIndustryRepository(build_number=None)
    )

    with pytest.raises(SdeNotImportedError):
        service.create_plan((ItemQuantity(1001, 1),))


def test_service_rejects_unknown_root_type() -> None:
    service = IndustryPlanningService(FakeIndustryRepository())

    with pytest.raises(UnknownTypeError) as error:
        service.create_plan((ItemQuantity(9999, 1),))
    assert error.value.type_ids == (9999,)
    assert error.value.sde_build_number == 1


def test_service_rejects_unpublished_root_type() -> None:
    service = IndustryPlanningService(
        FakeIndustryRepository(unpublished_type_ids={1001})
    )

    with pytest.raises(UnpublishedTypeError) as error:
        service.create_plan((ItemQuantity(1001, 1),))

    assert error.value.type_ids == (1001,)
    assert error.value.sde_build_number == 1


def test_service_does_not_load_recipes_below_buy_root() -> None:
    repository = FakeIndustryRepository()
    service = IndustryPlanningService(repository)

    plan = service.create_plan(
        (ItemQuantity(1001, 2),),
        choices={1001: BuildChoice(BuildDecision.BUY)},
    )

    assert repository.recipe_loads == []
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [(1001, 2)]


def test_service_loads_product_metadata_for_scoped_rig_rules() -> None:
    class RecipeRepository(FakeIndustryRepository):
        def load_recipes_for_products(
            self,
            product_type_ids: Collection[int],
        ) -> dict[int, tuple[IndustryRecipe, ...]]:
            self.recipe_loads.append(frozenset(product_type_ids))
            recipe = IndustryRecipe(
                key=RecipeKey(2001, 1),
                blueprint_name="Test Blueprint",
                activity=ActivityKind.MANUFACTURING,
                time_seconds=60,
                max_production_limit=100,
                products=(ItemQuantity(1001, 1),),
                materials=(ItemQuantity(1002, 10),),
            )
            return {
                type_id: (recipe,) if type_id == 1001 else ()
                for type_id in product_type_ids
            }

    repository = RecipeRepository()
    service = IndustryPlanningService(repository)

    plan = service.create_plan(
        (ItemQuantity(1001, 1),),
        production_profile=ProductionProfile(
            rig_modifiers=(
                RigModifier(
                    ActivityKind.MANUFACTURING,
                    time_reduction_basis_points=2_000,
                    category_ids=(1,),
                ),
            )
        ),
    )

    assert repository.type_loads == [frozenset({1001}), frozenset({1001})]
    assert plan.build_steps[0].exact_job_time_seconds == 48
