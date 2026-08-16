from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.industry.models import ActivityKind, RecipeKey


class IndustryError(Exception):
    """Base error for industry data access and planning."""


class InvalidIndustryDataError(IndustryError, ValueError):
    """Raised when domain data violates the calculator's invariants."""


class SdeNotImportedError(IndustryError):
    """Raised when planning is attempted before an SDE import exists."""


class SdeVersionMismatchError(IndustryError):
    def __init__(self, expected_build: int, current_build: int) -> None:
        self.expected_build = expected_build
        self.current_build = current_build
        super().__init__(
            f"Expected SDE build {expected_build}, but current build is "
            f"{current_build}"
        )


class UnknownTypeError(IndustryError):
    def __init__(
        self,
        type_ids: tuple[int, ...],
        *,
        sde_build_number: int | None = None,
    ) -> None:
        self.type_ids = type_ids
        self.sde_build_number = sde_build_number
        joined_ids = ", ".join(str(type_id) for type_id in type_ids)
        super().__init__(f"Unknown EVE type ID(s): {joined_ids}")


class UnpublishedTypeError(IndustryError):
    def __init__(
        self,
        type_ids: tuple[int, ...],
        *,
        sde_build_number: int,
    ) -> None:
        self.type_ids = type_ids
        self.sde_build_number = sde_build_number
        joined_ids = ", ".join(str(type_id) for type_id in type_ids)
        super().__init__(f"Unpublished EVE type ID(s): {joined_ids}")


class IndustryPlanningError(IndustryError):
    """Base error for a production plan that cannot be resolved."""

    def __init__(self, message: str) -> None:
        self.sde_build_number: int | None = None
        super().__init__(message)

    def attach_sde_build_number(self, build_number: int) -> None:
        self.sde_build_number = build_number


class PlanTooLargeError(IndustryPlanningError):
    def __init__(self, maximum_types: int) -> None:
        self.maximum_types = maximum_types
        super().__init__(
            f"Production plan exceeds the limit of {maximum_types} expanded types"
        )


class QuantityTooLargeError(IndustryPlanningError):
    def __init__(self, field_name: str, maximum: int) -> None:
        self.field_name = field_name
        self.maximum = maximum
        super().__init__(
            f"{field_name} exceeds the maximum safe integer {maximum}"
        )


class UnusedBuildChoicesError(IndustryPlanningError):
    def __init__(self, type_ids: tuple[int, ...]) -> None:
        self.type_ids = type_ids
        joined_ids = ", ".join(str(type_id) for type_id in type_ids)
        super().__init__(
            f"Build choices do not apply to the selected production graph: "
            f"{joined_ids}"
        )


class UnusedBlueprintEfficienciesError(IndustryPlanningError):
    def __init__(self, recipe_keys: tuple[RecipeKey, ...]) -> None:
        self.recipe_keys = recipe_keys
        joined_keys = ", ".join(str(recipe_key) for recipe_key in recipe_keys)
        super().__init__(
            "Blueprint efficiency settings do not apply to the selected "
            f"production graph: {joined_keys}"
        )


class BlueprintEfficiencyNotApplicableError(IndustryPlanningError):
    def __init__(
        self,
        recipe_key: RecipeKey,
        activity: ActivityKind,
    ) -> None:
        self.recipe_key = recipe_key
        self.activity = activity
        super().__init__(
            f"Blueprint ME/TE does not apply to {activity.value} recipe "
            f"{recipe_key}"
        )


class ConflictingRigModifiersError(IndustryPlanningError):
    def __init__(
        self,
        recipe_key: RecipeKey,
        dimension: str,
    ) -> None:
        self.recipe_key = recipe_key
        self.dimension = dimension
        super().__init__(
            f"Multiple rig modifiers affect {dimension} for recipe {recipe_key}"
        )


class MissingActivityPricingError(IndustryPlanningError):
    def __init__(self, activities: tuple[ActivityKind, ...]) -> None:
        self.activities = activities
        joined = ", ".join(activity.value for activity in activities)
        super().__init__(
            "Pricing requires a job-cost context for each selected activity; "
            f"missing: {joined}"
        )


class AmbiguousRecipeError(IndustryPlanningError):
    def __init__(
        self,
        product_type_id: int,
        candidates: tuple[RecipeKey, ...],
    ) -> None:
        self.product_type_id = product_type_id
        self.candidates = candidates
        joined_candidates = ", ".join(str(candidate) for candidate in candidates)
        super().__init__(
            f"Type {product_type_id} has multiple production recipes: "
            f"{joined_candidates}"
        )


class MissingRecipeError(IndustryPlanningError):
    def __init__(self, product_type_id: int) -> None:
        self.product_type_id = product_type_id
        super().__init__(
            f"Type {product_type_id} was explicitly marked for building but has "
            "no supported recipe"
        )


class InvalidRecipeChoiceError(IndustryPlanningError):
    def __init__(
        self,
        product_type_id: int,
        recipe_key: RecipeKey,
    ) -> None:
        self.product_type_id = product_type_id
        self.recipe_key = recipe_key
        super().__init__(
            f"Recipe {recipe_key} does not produce type {product_type_id}"
        )


class RecipeCycleError(IndustryPlanningError):
    def __init__(self, type_path: tuple[int, ...]) -> None:
        self.type_path = type_path
        joined_path = " -> ".join(str(type_id) for type_id in type_path)
        super().__init__(f"Production cycle detected: {joined_path}")


class UnsupportedCoProductsError(IndustryPlanningError):
    def __init__(self, recipe_key: RecipeKey) -> None:
        self.recipe_key = recipe_key
        super().__init__(
            f"Recipe {recipe_key} has multiple products; co-product planning is "
            "not supported yet"
        )
