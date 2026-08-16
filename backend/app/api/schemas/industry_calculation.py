from typing import Annotated, Self

from pydantic import Field, model_validator

from app.api.schemas.industry import (
    ApiModel,
    CalculationRequest,
    ItemQuantityRequest,
    Quantity,
    RecipeKeyRequest,
)
from app.industry.models import RecipeKey


class BlueprintCopyRunLimitRequest(ApiModel):
    recipe_key: RecipeKeyRequest
    runs_per_copy: Quantity

    def to_domain(self) -> tuple[RecipeKey, int]:
        return self.recipe_key.to_domain(), self.runs_per_copy


class IndustryCalculationRequest(CalculationRequest):
    """Backward-compatible calculation request with additive planner inputs."""

    owned_materials: Annotated[
        list[ItemQuantityRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)
    blueprint_copy_run_limits: Annotated[
        list[BlueprintCopyRunLimitRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_additive_inputs(self) -> Self:
        owned_type_ids = [item.type_id for item in self.owned_materials]
        if len(owned_type_ids) != len(set(owned_type_ids)):
            raise ValueError(
                "owned_materials must contain at most one entry per type_id"
            )
        copy_recipe_keys = [
            item.recipe_key.to_domain()
            for item in self.blueprint_copy_run_limits
        ]
        if len(copy_recipe_keys) != len(set(copy_recipe_keys)):
            raise ValueError(
                "blueprint_copy_run_limits must contain at most one entry per recipe"
            )
        return self

    def to_owned_materials(self) -> dict[int, int]:
        return {
            item.type_id: item.quantity
            for item in self.owned_materials
        }

    def to_blueprint_copy_run_limits(self) -> dict[RecipeKey, int]:
        return dict(
            item.to_domain()
            for item in self.blueprint_copy_run_limits
        )
