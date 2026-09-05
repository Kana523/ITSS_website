from collections.abc import Collection

import pytest

from app.industry.errors import (
    InvalidIndustryDataError,
    SdeNotImportedError,
    UnknownTypeError,
    UnpublishedTypeError,
)
from app.industry.models import (
    ActivityKind,
    BuildChoice,
    BuildDecision,
    IndustryRecipe,
    IndustrySetupOverride,
    IndustryType,
    ItemQuantity,
    ProductionProfile,
    RecipeKey,
    RigModifier,
)
from app.industry.service import IndustryPlanningService
from app.industry.setup_categories import IndustrySetupCategory


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


class SetupOverrideRecipeRepository(FakeIndustryRepository):
    def __init__(self, *, omit_metadata_type_id: int | None = None) -> None:
        super().__init__()
        self.omit_metadata_type_id = omit_metadata_type_id

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        self.type_loads.append(frozenset(type_ids))
        return {
            type_id: IndustryType(
                type_id=type_id,
                name=f"Type {type_id}",
                published=True,
                group_id=25,
                group_name="Frigate",
                category_id=6,
                category_name="Ship",
            )
            for type_id in type_ids
            if not (
                len(type_ids) > 1
                and type_id == self.omit_metadata_type_id
            )
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        self.recipe_loads.append(frozenset(product_type_ids))
        recipes = {
            1001: IndustryRecipe(
                key=RecipeKey(2001, 1),
                blueprint_name="Final Blueprint",
                activity=ActivityKind.MANUFACTURING,
                time_seconds=60,
                max_production_limit=100,
                products=(ItemQuantity(1001, 1),),
                materials=(ItemQuantity(1002, 2),),
            ),
            1002: IndustryRecipe(
                key=RecipeKey(2002, 1),
                blueprint_name="Component Blueprint",
                activity=ActivityKind.MANUFACTURING,
                time_seconds=60,
                max_production_limit=100,
                products=(ItemQuantity(1002, 1),),
                materials=(ItemQuantity(1003, 3),),
            ),
        }
        return {
            type_id: (recipes[type_id],) if type_id in recipes else ()
            for type_id in product_type_ids
        }


def _setup_override_profile() -> ProductionProfile:
    return ProductionProfile(
        setup_overrides=(
            IndustrySetupOverride(
                category=IndustrySetupCategory.T1_SMALL_SHIPS,
                solar_system_id=30_002_665,
                facility_material_reduction_basis_points=100,
                rig_material_reduction_basis_points=200,
                job_cost_reduction_basis_points=300,
            ),
        )
    )


def test_service_loads_all_built_product_metadata_for_setup_overrides() -> None:
    repository = SetupOverrideRecipeRepository()

    plan = IndustryPlanningService(repository).create_plan(
        (ItemQuantity(1001, 1),),
        production_profile=_setup_override_profile(),
    )

    assert repository.type_loads == [
        frozenset({1001}),
        frozenset({1001, 1002}),
    ]
    assert len(plan.build_steps) == 2
    assert all(
        step.industry_setup_override is not None
        for step in plan.build_steps
    )


def test_service_rejects_missing_setup_override_product_metadata() -> None:
    repository = SetupOverrideRecipeRepository(omit_metadata_type_id=1002)

    with pytest.raises(
        InvalidIndustryDataError,
        match=r"missing product type ID\(s\): 1002",
    ):
        IndustryPlanningService(repository).create_plan(
            (ItemQuantity(1001, 1),),
            production_profile=_setup_override_profile(),
        )
