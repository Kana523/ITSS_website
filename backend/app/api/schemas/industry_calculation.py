from typing import Annotated, Self

from pydantic import Field, model_validator

from app.api.schemas.industry import CalculationRequest, ItemQuantityRequest


class IndustryCalculationRequest(CalculationRequest):
    """Backward-compatible calculation request with optional owned inventory."""

    owned_materials: Annotated[
        list[ItemQuantityRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_owned_materials(self) -> Self:
        type_ids = [item.type_id for item in self.owned_materials]
        if len(type_ids) != len(set(type_ids)):
            raise ValueError(
                "owned_materials must contain at most one entry per type_id"
            )
        return self

    def to_owned_materials(self) -> dict[int, int]:
        return {
            item.type_id: item.quantity
            for item in self.owned_materials
        }
