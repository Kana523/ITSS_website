from collections.abc import Iterable, Mapping
from fractions import Fraction

from app.industry.errors import (
    IndustryPlanningError,
    InvalidIndustryDataError,
    InvalidScheduleError,
    PlanTooLargeError,
    SdeNotImportedError,
    SdeVersionMismatchError,
    UnknownTypeError,
    UnpublishedTypeError,
)
from app.industry.models import (
    ActivityKind,
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
    normalize_blueprint_copy_run_limits,
    normalize_build_choices,
    normalize_owned_materials,
    plan_production,
    resolve_recipe_choice,
)
from app.industry.repository import IndustryRepository
from app.industry.blueprint_library import BlueprintSelection, BlueprintStockError, normalize_selections, group_selections
from app.industry.specialist_skills import (
    MissingSpecialistSkillsError,
    SpecialistSkillRequirement,
    effective_required_skill_level,
    manufacturing_skill_bonuses,
    normalize_specialist_skill_levels,
)


class IndustryPlanningService:
    MAX_EXPANDED_TYPES = 5_000

    def __init__(self, repository: IndustryRepository) -> None:
        self._repository = repository

    def create_plan(
        self,
        demands: Iterable[ItemQuantity],
        *,
        choices: Mapping[int, BuildChoice] | None = None,
        blueprint_efficiencies: Mapping[RecipeKey, BlueprintEfficiency] | None = None,
        production_profile: ProductionProfile | None = None,
        owned_materials: Mapping[int, int] | None = None,
        blueprint_copy_run_limits: Mapping[RecipeKey, int] | None = None,
        blueprint_selections: Iterable[BlueprintSelection] | None = None,
        require_owned_blueprints: bool = False,
        schedule_max_runs: int | None = None,
        specialist_skill_levels: Mapping[int, int] | None = None,
        manufacturing_time_multiplier: Fraction = Fraction(1),
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
        owned_by_type = normalize_owned_materials(owned_materials)
        copy_run_limits = normalize_blueprint_copy_run_limits(
            blueprint_copy_run_limits
        )
        selection_values = tuple(blueprint_selections or ())
        lots = group_selections(selection_values)
        selections = ({key: rows[0] for key, rows in lots.items()} if schedule_max_runs is not None
                      else normalize_selections(selection_values))
        if set(selections).intersection(set(blueprint_efficiencies or {}) | set(copy_run_limits)):
            raise InvalidIndustryDataError("Library selections replace manual efficiencies and copy limits")
        enforce_specialist_skills = specialist_skill_levels is not None
        specialist_levels = normalize_specialist_skill_levels(
            dict(specialist_skill_levels or {})
        )

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
                owned_by_type,
                copy_run_limits,
                specialist_levels,
                enforce_specialist_skills,
                manufacturing_time_multiplier,
                build_number,
                root_type_ids,
                selections,
                require_owned_blueprints,
                lots,
                schedule_max_runs,
            )
        except IndustryPlanningError as exc:
            exc.attach_sde_build_number(build_number)
            raise

    def _create_plan_for_snapshot(
        self,
        demand_tuple: tuple[ItemQuantity, ...],
        choice_by_type: Mapping[int, BuildChoice],
        blueprint_efficiencies: Mapping[RecipeKey, BlueprintEfficiency] | None,
        production_profile: ProductionProfile | None,
        owned_materials: Mapping[int, int],
        blueprint_copy_run_limits: Mapping[RecipeKey, int],
        specialist_skill_levels: Mapping[int, int],
        enforce_specialist_skills: bool,
        manufacturing_time_multiplier: Fraction,
        build_number: int,
        root_type_ids: set[int],
        selections: Mapping[RecipeKey, BlueprintSelection],
        require_owned_blueprints: bool,
        lots: Mapping,
        schedule_max_runs: int | None,
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
                self._repository.load_recipes_for_products(recipe_lookup_type_ids)
                if recipe_lookup_type_ids
                else {}
            )
            next_frontier: set[int] = set()
            for product_type_id in sorted(current_type_ids):
                choice = choice_by_type.get(product_type_id, BuildChoice())
                candidates = recipes_by_product.get(product_type_id, ())
                selected_candidates = [recipe for recipe in candidates if recipe.key in selections]
                if choice.decision == BuildDecision.AUTO and len(selected_candidates) == 1:
                    choice = BuildChoice(BuildDecision.BUILD, selected_candidates[0].key)
                selected_recipe = resolve_recipe_choice(
                    product_type_id,
                    candidates,
                    choice,
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
        requirements_by_recipe: Mapping[
            RecipeKey, tuple[SpecialistSkillRequirement, ...]
        ] = {}
        if enforce_specialist_skills and recipes_by_key:
            skill_loader = getattr(
                self._repository,
                "load_recipe_skill_requirements",
                None,
            )
            requirements_by_recipe = (
                skill_loader(tuple(recipes_by_key))
                if callable(skill_loader)
                else {}
            )

        product_metadata_type_ids = {
            recipe.products[0].type_id
            for recipe in recipes_by_key.values()
            if (
                recipe.activity == ActivityKind.MANUFACTURING
                and bool(profile.setup_overrides)
            )
            or any(
                modifier.activity == recipe.activity
                and (modifier.category_ids or modifier.group_ids)
                for modifier in profile.rig_modifiers
            )
        }
        product_types = (
            self._repository.load_types(product_metadata_type_ids)
            if product_metadata_type_ids
            else {}
        )
        missing_product_type_ids = tuple(
            sorted(product_metadata_type_ids - product_types.keys())
        )
        if missing_product_type_ids:
            raise InvalidIndustryDataError(
                "Production recipes reference missing product type ID(s): "
                + ", ".join(str(type_id) for type_id in missing_product_type_ids)
            )

        efficiencies = dict(blueprint_efficiencies or {})
        copy_limits = dict(blueprint_copy_run_limits)
        for key, selection in selections.items():
            if key not in recipes_by_key:
                continue
            efficiencies[key] = selection.efficiency
            if schedule_max_runs is None and selection.kind == "bpc" and selection.remaining_runs:
                copy_limits[key] = selection.remaining_runs
            if schedule_max_runs is not None:
                maximum = recipes_by_key[key].max_production_limit
                if maximum is not None and any(lot.kind == "bpc" and lot.remaining_runs > maximum for lot in lots[key]):
                    raise InvalidScheduleError(f"Copy runs exceed the SDE maximum for blueprint {key.blueprint_type_id}. Correct the selected lot's remaining runs.")

        plan = plan_production(
            demand_tuple,
            tuple(sorted(recipes_by_key.values(), key=lambda recipe: recipe.key)),
            sde_build_number=build_number,
            choices=choice_by_type,
            blueprint_efficiencies=efficiencies,
            production_profile=profile,
            product_types=product_types,
            owned_materials=owned_materials,
            blueprint_copy_run_limits=copy_limits,
            scheduled_lots=lots,
            schedule_max_runs=schedule_max_runs,
            manufacturing_time_multiplier=manufacturing_time_multiplier,
            specialist_skill_bonuses={
                key: manufacturing_skill_bonuses(requirements, specialist_skill_levels)
                for key, requirements in requirements_by_recipe.items()
                if recipes_by_key[key].activity == ActivityKind.MANUFACTURING
            },
        )
        # Inventory can remove entire jobs and their dependency chains. Check
        # eligibility only after the final quantities and timed job splits exist.
        missing: list[tuple[RecipeKey, SpecialistSkillRequirement, int]] = []
        for step in plan.build_steps:
            selection = selections.get(step.recipe.key)
            if schedule_max_runs is None and selection and selection.available_runs is not None and step.runs > selection.available_runs:
                raise BlueprintStockError(step.recipe.key, step.runs, selection.available_runs)
            if require_owned_blueprints and step.recipe.activity == ActivityKind.MANUFACTURING and selection is None:
                raise BlueprintStockError(step.recipe.key, step.runs, 0)
        if enforce_specialist_skills:
            for step in sorted(plan.build_steps, key=lambda step: step.recipe.key):
                for requirement in requirements_by_recipe.get(step.recipe.key, ()):
                    current_level = effective_required_skill_level(
                        requirement.type_id, specialist_skill_levels, profile.skills,
                    )
                    if current_level < requirement.level:
                        missing.append((step.recipe.key, requirement, current_level))
        if missing:
            raise MissingSpecialistSkillsError(tuple(missing))
        return plan
