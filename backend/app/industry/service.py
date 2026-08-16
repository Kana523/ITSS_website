from collections.abc import Iterable, Mapping

from app.industry.errors import (
    IndustryPlanningError,
    InvalidIndustryDataError,
    PlanTooLargeError,
    SdeNotImportedError,
    SdeVersionMismatchError,
    UnknownTypeError,
    UnpublishedTypeError,
)
from app.industry.models import (
    BlueprintEfficiency,
    BuildChoice,
    BuildDecision,
    IndustryRecipe,
    ItemQuantity,
    ProductionPlan,
    ProductionProfile,
    RecipeKey,
)
from app.industry.planner import (
    normalize_build_choices,
    plan_production,
    resolve_recipe_choice,
)
from app.industry.repository import IndustryRepository


class IndustryPlanningService:
    MAX_EXPANDED_TYPES = 5_000

    def __init__(self, repository: IndustryRepository) -> None:
        self._repository = repository

    def create_plan(
        self,
        demands: Iterable[ItemQuantity],
        *,
        choices: Mapping[int, BuildChoice] | None = None,
        blueprint_efficiencies: Mapping[
            RecipeKey,
            BlueprintEfficiency,
        ]
        | None = None,
        production_profile: ProductionProfile | None = None,
        expected_sde_build_number: int | None = None,
    ) -> ProductionPlan:
        demand_tuple = tuple(demands)
        if not demand_tuple:
            raise InvalidIndustryDataError(
                "At least one production demand is required"
            )
        if (
            production_profile is not None
            and not isinstance(production_profile, ProductionProfile)
        ):
            raise InvalidIndustryDataError(
                "production_profile must be a ProductionProfile"
            )
        choice_by_type = normalize_build_choices(choices)

        build_number = self._repository.latest_sde_build_number()
        if build_number is None:
            raise SdeNotImportedError(
                "An EVE SDE snapshot must be imported before planning"
            )
        if (
            expected_sde_build_number is not None
            and expected_sde_build_number != build_number
        ):
            raise SdeVersionMismatchError(
                expected_sde_build_number,
                build_number,
            )

        root_type_ids = {demand.type_id for demand in demand_tuple}
        known_root_types = self._repository.load_types(root_type_ids)
        missing_type_ids = tuple(sorted(root_type_ids - known_root_types.keys()))
        if missing_type_ids:
            raise UnknownTypeError(
                missing_type_ids,
                sde_build_number=build_number,
            )
        unpublished_type_ids = tuple(
            sorted(
                type_id
                for type_id, item_type in known_root_types.items()
                if not item_type.published
            )
        )
        if unpublished_type_ids:
            raise UnpublishedTypeError(
                unpublished_type_ids,
                sde_build_number=build_number,
            )

        try:
            return self._create_plan_for_snapshot(
                demand_tuple,
                choice_by_type,
                blueprint_efficiencies,
                production_profile,
                build_number,
                root_type_ids,
            )
        except IndustryPlanningError as exc:
            exc.attach_sde_build_number(build_number)
            raise

    def _create_plan_for_snapshot(
        self,
        demand_tuple: tuple[ItemQuantity, ...],
        choice_by_type: Mapping[int, BuildChoice],
        blueprint_efficiencies: Mapping[
            RecipeKey,
            BlueprintEfficiency,
        ]
        | None,
        production_profile: ProductionProfile | None,
        build_number: int,
        root_type_ids: set[int],
    ) -> ProductionPlan:

        recipes_by_key: dict[RecipeKey, IndustryRecipe] = {}
        visited_type_ids: set[int] = set()
        frontier = root_type_ids

        while frontier:
            current_type_ids = frontier - visited_type_ids
            if not current_type_ids:
                break
            visited_type_ids.update(current_type_ids)
            if len(visited_type_ids) > self.MAX_EXPANDED_TYPES:
                raise PlanTooLargeError(self.MAX_EXPANDED_TYPES)

            recipe_lookup_type_ids = {
                type_id
                for type_id in current_type_ids
                if choice_by_type.get(type_id, BuildChoice()).decision
                != BuildDecision.BUY
            }
            recipes_by_product = (
                self._repository.load_recipes_for_products(
                    recipe_lookup_type_ids
                )
                if recipe_lookup_type_ids
                else {}
            )
            next_frontier: set[int] = set()
            for product_type_id in sorted(current_type_ids):
                selected_recipe = resolve_recipe_choice(
                    product_type_id,
                    recipes_by_product.get(product_type_id, ()),
                    choice_by_type.get(product_type_id, BuildChoice()),
                )
                if selected_recipe is None:
                    continue

                existing = recipes_by_key.get(selected_recipe.key)
                if existing is not None and existing != selected_recipe:
                    raise InvalidIndustryDataError(
                        f"Conflicting data for recipe {selected_recipe.key}"
                    )
                recipes_by_key[selected_recipe.key] = selected_recipe
                next_frontier.update(
                    material.type_id for material in selected_recipe.materials
                )
            frontier = next_frontier

        profile = production_profile or ProductionProfile()
        scoped_rig_product_type_ids = {
            recipe.products[0].type_id
            for recipe in recipes_by_key.values()
            if any(
                modifier.activity == recipe.activity
                and (modifier.category_ids or modifier.group_ids)
                for modifier in profile.rig_modifiers
            )
        }
        product_types = (
            self._repository.load_types(scoped_rig_product_type_ids)
            if scoped_rig_product_type_ids
            else {}
        )
        missing_product_type_ids = tuple(
            sorted(scoped_rig_product_type_ids - product_types.keys())
        )
        if missing_product_type_ids:
            raise InvalidIndustryDataError(
                "Production recipes reference missing product type ID(s): "
                + ", ".join(
                    str(type_id) for type_id in missing_product_type_ids
                )
            )

        return plan_production(
            demand_tuple,
            tuple(sorted(recipes_by_key.values(), key=lambda recipe: recipe.key)),
            sde_build_number=build_number,
            choices=choice_by_type,
            blueprint_efficiencies=blueprint_efficiencies,
            production_profile=profile,
            product_types=product_types,
        )
