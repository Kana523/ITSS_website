from collections import defaultdict
from collections.abc import Iterable, Mapping
from fractions import Fraction

from app.industry.errors import (
    AmbiguousRecipeError,
    BlueprintEfficiencyNotApplicableError,
    ConflictingRigModifiersError,
    InvalidIndustryDataError,
    InvalidRecipeChoiceError,
    MissingRecipeError,
    QuantityTooLargeError,
    RecipeCycleError,
    UnusedBlueprintEfficienciesError,
    UnusedBuildChoicesError,
    UnsupportedCoProductsError,
)
from app.industry.models import (
    ActivityKind,
    AppliedProductionModifiers,
    BlueprintEfficiency,
    BuildChoice,
    BuildDecision,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    MAX_SAFE_INTEGER,
    ProductionPlan,
    ProductionStep,
    PurchaseReason,
    PurchaseRequirement,
    RecipeKey,
    ProductionProfile,
)


def _require_safe_integer(value: int, field_name: str) -> int:
    if value > MAX_SAFE_INTEGER:
        raise QuantityTooLargeError(field_name, MAX_SAFE_INTEGER)
    return value


def _ceil_fraction(value: Fraction) -> int:
    return (value.numerator + value.denominator - 1) // value.denominator


def _job_material_quantity(
    quantity_per_run: int,
    runs: int,
    material_multiplier: Fraction,
) -> int:
    """Apply all whole-job material factors before EVE's final ceiling."""
    reduced_total = _ceil_fraction(
        quantity_per_run * runs * material_multiplier
    )
    # Every listed material requires at least one whole unit for every run.
    return max(runs, reduced_total)


def _resolve_production_modifiers(
    recipe: IndustryRecipe,
    product_type_id: int,
    production_profile: ProductionProfile,
    product_types: Mapping[int, IndustryType],
) -> AppliedProductionModifiers:
    facility = production_profile.facility_for(recipe.activity)
    relevant_rig_rules = tuple(
        modifier
        for modifier in production_profile.rig_modifiers
        if modifier.activity == recipe.activity
    )
    scoped_rig_rules = tuple(
        modifier
        for modifier in relevant_rig_rules
        if modifier.category_ids or modifier.group_ids
    )
    product_type = product_types.get(product_type_id)
    if product_type is not None and (
        not isinstance(product_type, IndustryType)
        or product_type.type_id != product_type_id
    ):
        raise InvalidIndustryDataError(
            f"Product metadata for type {product_type_id} is invalid"
        )
    if scoped_rig_rules and product_type is None:
        raise InvalidIndustryDataError(
            f"Product metadata is required to resolve rig modifiers for type "
            f"{product_type_id}"
        )

    matching_rig_rules = tuple(
        modifier
        for modifier in relevant_rig_rules
        if (
            (not modifier.category_ids and not modifier.group_ids)
            or (
                product_type is not None
                and modifier.applies_to(product_type)
            )
        )
    )
    material_rig_rules = tuple(
        modifier
        for modifier in matching_rig_rules
        if modifier.material_reduction_basis_points > 0
    )
    time_rig_rules = tuple(
        modifier
        for modifier in matching_rig_rules
        if modifier.time_reduction_basis_points > 0
    )
    if len(material_rig_rules) > 1:
        raise ConflictingRigModifiersError(recipe.key, "material requirements")
    if len(time_rig_rules) > 1:
        raise ConflictingRigModifiersError(recipe.key, "job time")

    return AppliedProductionModifiers(
        activity=recipe.activity,
        skills=production_profile.skills,
        facility_material_reduction_basis_points=(
            facility.material_reduction_basis_points
            if facility is not None
            else 0
        ),
        facility_time_reduction_basis_points=(
            facility.time_reduction_basis_points
            if facility is not None
            else 0
        ),
        rig_material_reduction_basis_points=(
            material_rig_rules[0].material_reduction_basis_points
            if material_rig_rules
            else 0
        ),
        rig_time_reduction_basis_points=(
            time_rig_rules[0].time_reduction_basis_points
            if time_rig_rules
            else 0
        ),
    )


def _index_recipes(
    recipes: Iterable[IndustryRecipe],
) -> dict[int, tuple[IndustryRecipe, ...]]:
    recipes_by_key: dict[RecipeKey, IndustryRecipe] = {}
    recipes_by_product: dict[int, list[IndustryRecipe]] = defaultdict(list)

    for recipe in recipes:
        if recipe.key in recipes_by_key:
            raise InvalidIndustryDataError(
                f"Duplicate industry recipe key: {recipe.key}"
            )
        recipes_by_key[recipe.key] = recipe
        for product in recipe.products:
            recipes_by_product[product.type_id].append(recipe)

    return {
        product_type_id: tuple(sorted(candidates, key=lambda recipe: recipe.key))
        for product_type_id, candidates in recipes_by_product.items()
    }


def _aggregate_demands(
    demands: Iterable[ItemQuantity],
) -> tuple[ItemQuantity, ...]:
    quantities: dict[int, int] = defaultdict(int)
    for demand in demands:
        quantities[demand.type_id] = _require_safe_integer(
            quantities[demand.type_id] + demand.quantity,
            f"Requested quantity for type {demand.type_id}",
        )

    if not quantities:
        raise InvalidIndustryDataError("At least one production demand is required")

    return tuple(
        ItemQuantity(type_id=type_id, quantity=quantity)
        for type_id, quantity in sorted(quantities.items())
    )


def normalize_build_choices(
    choices: Mapping[int, BuildChoice] | None,
) -> dict[int, BuildChoice]:
    normalized: dict[int, BuildChoice] = {}
    for type_id, choice in (choices or {}).items():
        if isinstance(type_id, bool) or not isinstance(type_id, int) or type_id <= 0:
            raise InvalidIndustryDataError(
                "Build choice type IDs must be positive integers"
            )
        if not isinstance(choice, BuildChoice):
            raise InvalidIndustryDataError(
                f"Build choice for type {type_id} must be a BuildChoice"
            )
        normalized[type_id] = choice
    return {type_id: normalized[type_id] for type_id in sorted(normalized)}


def normalize_blueprint_efficiencies(
    efficiencies: Mapping[RecipeKey, BlueprintEfficiency] | None,
) -> dict[RecipeKey, BlueprintEfficiency]:
    normalized: dict[RecipeKey, BlueprintEfficiency] = {}
    for recipe_key, efficiency in (efficiencies or {}).items():
        if not isinstance(recipe_key, RecipeKey):
            raise InvalidIndustryDataError(
                "Blueprint efficiency keys must be RecipeKey values"
            )
        if not isinstance(efficiency, BlueprintEfficiency):
            raise InvalidIndustryDataError(
                f"Blueprint efficiency for {recipe_key} must be a "
                "BlueprintEfficiency"
            )
        normalized[recipe_key] = efficiency
    return {
        recipe_key: normalized[recipe_key]
        for recipe_key in sorted(normalized)
    }


def resolve_recipe_choice(
    product_type_id: int,
    candidates: Iterable[IndustryRecipe],
    choice: BuildChoice,
) -> IndustryRecipe | None:
    """Resolve one global build/buy decision for a product type."""
    candidates = tuple(sorted(candidates, key=lambda recipe: recipe.key))
    for candidate in candidates:
        if candidate.output_quantity_for(product_type_id) is None:
            raise InvalidIndustryDataError(
                f"Recipe {candidate.key} does not produce type {product_type_id}"
            )

    if choice.decision == BuildDecision.BUY:
        return None
    if not candidates:
        if choice.decision == BuildDecision.BUILD:
            raise MissingRecipeError(product_type_id)
        return None

    if choice.recipe_key is not None:
        selected = next(
            (
                candidate
                for candidate in candidates
                if candidate.key == choice.recipe_key
            ),
            None,
        )
        if selected is None:
            raise InvalidRecipeChoiceError(product_type_id, choice.recipe_key)
    elif len(candidates) > 1:
        raise AmbiguousRecipeError(
            product_type_id,
            tuple(candidate.key for candidate in candidates),
        )
    else:
        selected = candidates[0]

    if len(selected.products) != 1:
        raise UnsupportedCoProductsError(selected.key)
    return selected


def plan_production(
    demands: Iterable[ItemQuantity],
    recipes: Iterable[IndustryRecipe],
    *,
    sde_build_number: int,
    choices: Mapping[int, BuildChoice] | None = None,
    blueprint_efficiencies: Mapping[RecipeKey, BlueprintEfficiency] | None = None,
    production_profile: ProductionProfile | None = None,
    product_types: Mapping[int, IndustryType] | None = None,
) -> ProductionPlan:
    """Create a deterministic production plan without database access."""
    if (
        isinstance(sde_build_number, bool)
        or not isinstance(sde_build_number, int)
        or sde_build_number <= 0
    ):
        raise InvalidIndustryDataError(
            "sde_build_number must be a positive integer"
        )

    requested = _aggregate_demands(demands)
    recipes_by_product = _index_recipes(recipes)
    choice_by_type = normalize_build_choices(choices)
    efficiency_by_recipe = normalize_blueprint_efficiencies(
        blueprint_efficiencies
    )
    if production_profile is None:
        production_profile = ProductionProfile()
    elif not isinstance(production_profile, ProductionProfile):
        raise InvalidIndustryDataError(
            "production_profile must be a ProductionProfile"
        )
    product_type_by_id = product_types or {}

    selected_recipes: dict[int, IndustryRecipe] = {}
    purchase_reasons: dict[int, PurchaseReason] = {}
    dependency_order: list[int] = []
    visit_state: dict[int, int] = {}
    active_path: list[int] = []

    def visit(product_type_id: int) -> None:
        state = visit_state.get(product_type_id, 0)
        if state == 2:
            return
        if state == 1:
            cycle_start = active_path.index(product_type_id)
            raise RecipeCycleError(
                tuple(active_path[cycle_start:] + [product_type_id])
            )

        visit_state[product_type_id] = 1
        active_path.append(product_type_id)
        choice = choice_by_type.get(product_type_id, BuildChoice())
        selected = resolve_recipe_choice(
            product_type_id,
            recipes_by_product.get(product_type_id, ()),
            choice,
        )
        if selected is not None:
            selected_recipes[product_type_id] = selected
            for material in selected.materials:
                visit(material.type_id)
            dependency_order.append(product_type_id)
        elif choice.decision == BuildDecision.BUY:
            purchase_reasons[product_type_id] = PurchaseReason.BUY_OVERRIDE
        else:
            purchase_reasons[product_type_id] = PurchaseReason.NO_RECIPE
        active_path.pop()
        visit_state[product_type_id] = 2

    for demand in requested:
        visit(demand.type_id)

    unused_choice_type_ids = tuple(
        sorted(set(choice_by_type) - set(visit_state))
    )
    if unused_choice_type_ids:
        raise UnusedBuildChoicesError(unused_choice_type_ids)

    selected_recipe_keys = {
        recipe.key for recipe in selected_recipes.values()
    }
    unused_efficiency_keys = tuple(
        sorted(set(efficiency_by_recipe) - selected_recipe_keys)
    )
    if unused_efficiency_keys:
        raise UnusedBlueprintEfficienciesError(unused_efficiency_keys)

    for recipe in selected_recipes.values():
        if (
            recipe.key in efficiency_by_recipe
            and recipe.activity != ActivityKind.MANUFACTURING
        ):
            raise BlueprintEfficiencyNotApplicableError(
                recipe.key,
                recipe.activity,
            )

    required_quantities: dict[int, int] = defaultdict(int)
    for demand in requested:
        required_quantities[demand.type_id] += demand.quantity

    steps_by_product: dict[int, ProductionStep] = {}
    for product_type_id in reversed(dependency_order):
        recipe = selected_recipes[product_type_id]
        required_quantity = required_quantities[product_type_id]
        output_per_run = recipe.output_quantity_for(product_type_id)
        if output_per_run is None:
            raise InvalidIndustryDataError(
                f"Recipe {recipe.key} does not contain product {product_type_id}"
            )

        _require_safe_integer(
            output_per_run,
            f"Output per run for type {product_type_id}",
        )
        runs = _require_safe_integer(
            (required_quantity + output_per_run - 1) // output_per_run,
            f"Run count for type {product_type_id}",
        )
        produced_quantity = _require_safe_integer(
            runs * output_per_run,
            f"Produced quantity for type {product_type_id}",
        )
        base_total_job_time_seconds = _require_safe_integer(
            runs * recipe.time_seconds,
            f"Total job time for type {product_type_id}",
        )
        efficiency = (
            efficiency_by_recipe.get(recipe.key, BlueprintEfficiency())
            if recipe.activity == ActivityKind.MANUFACTURING
            else None
        )
        production_modifiers = _resolve_production_modifiers(
            recipe,
            product_type_id,
            production_profile,
            product_type_by_id,
        )
        blueprint_material_multiplier = (
            Fraction(100 - efficiency.material_efficiency, 100)
            if efficiency is not None
            else Fraction(1)
        )
        blueprint_time_multiplier = (
            Fraction(100 - efficiency.time_efficiency, 100)
            if efficiency is not None
            else Fraction(1)
        )
        material_multiplier = (
            blueprint_material_multiplier
            * production_modifiers.material_multiplier
        )
        exact_job_time_seconds = (
            Fraction(base_total_job_time_seconds)
            * blueprint_time_multiplier
            * production_modifiers.time_multiplier
        )
        inputs_list: list[ItemQuantity] = []
        for material in recipe.materials:
            base_total_quantity = _require_safe_integer(
                material.quantity * runs,
                f"Base input quantity for type {material.type_id}",
            )
            adjusted_quantity = _job_material_quantity(
                material.quantity,
                runs,
                material_multiplier,
            )
            inputs_list.append(
                ItemQuantity(
                    type_id=material.type_id,
                    quantity=_require_safe_integer(
                        adjusted_quantity,
                        f"Adjusted input quantity for type {material.type_id}",
                    ),
                )
            )
        inputs = tuple(inputs_list)
        for material in inputs:
            required_quantities[material.type_id] = _require_safe_integer(
                required_quantities[material.type_id] + material.quantity,
                f"Required quantity for type {material.type_id}",
            )

        steps_by_product[product_type_id] = ProductionStep(
            product_type_id=product_type_id,
            recipe=recipe,
            required_quantity=required_quantity,
            output_per_run=output_per_run,
            runs=runs,
            produced_quantity=produced_quantity,
            surplus_quantity=produced_quantity - required_quantity,
            blueprint_efficiency=efficiency,
            production_modifiers=production_modifiers,
            base_total_job_time_seconds=base_total_job_time_seconds,
            exact_job_time_seconds=exact_job_time_seconds,
            inputs=inputs,
        )

    purchases = tuple(
        PurchaseRequirement(
            type_id=type_id,
            quantity=required_quantities[type_id],
            reason=reason,
        )
        for type_id, reason in sorted(purchase_reasons.items())
        if required_quantities[type_id] > 0
    )
    build_steps = tuple(
        steps_by_product[product_type_id] for product_type_id in dependency_order
    )

    return ProductionPlan(
        sde_build_number=sde_build_number,
        requested=requested,
        build_steps=build_steps,
        purchases=purchases,
    )
