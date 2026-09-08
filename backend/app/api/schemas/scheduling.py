from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator
from app.api.schemas.industry import ApiModel, RecipeKeyRequest, Quantity, TypeId, ExactFractionResponse, ItemQuantityRequest

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Slots = Annotated[int, Field(strict=True, ge=0, le=11)]


class ScheduleWorker(ApiModel):
    id: Identifier
    name: Label
    manufacturing_slots: Slots = 1
    reaction_slots: Slots = 1
    available_from: AwareDatetime | None = None


class ScheduleFacility(ApiModel):
    id: Identifier
    name: Label
    activity: Literal["manufacturing", "reaction"]
    solar_system_id: TypeId
    slots: Annotated[int, Field(strict=True, ge=1, le=100)] = 1


class ScheduleAssignment(ApiModel):
    recipe_key: RecipeKeyRequest
    worker_id: Identifier | None = None
    facility_id: Identifier | None = None


class ScheduleRequest(ApiModel):
    start_at: AwareDatetime
    max_runs_per_job: Quantity = 100
    workers: Annotated[list[ScheduleWorker], Field(min_length=1, max_length=20)]
    facilities: Annotated[list[ScheduleFacility], Field(min_length=1, max_length=50)]
    assignments: Annotated[list[ScheduleAssignment], Field(max_length=500)] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resources(self) -> Self:
        workers = {row.id for row in self.workers}
        facilities = {row.id for row in self.facilities}
        if len(workers) != len(self.workers) or len(facilities) != len(self.facilities):
            raise ValueError("Schedule resource IDs must be unique")
        keys = [row.recipe_key.to_domain() for row in self.assignments]
        if len(keys) != len(set(keys)):
            raise ValueError("A recipe can have only one schedule assignment")
        for row in self.assignments:
            if (row.worker_id is not None and row.worker_id not in workers) or (row.facility_id is not None and row.facility_id not in facilities):
                raise ValueError("Schedule assignment refers to an unknown resource")
        self.start_at = self.start_at.astimezone(UTC)
        return self


class ScheduledJob(ApiModel):
    job_id: int
    product_type_id: TypeId
    recipe_key: RecipeKeyRequest
    activity: Literal["manufacturing", "reaction"]
    runs: Quantity
    output_quantity: Quantity
    lot_id: str | None
    blueprint_instance: int
    material_efficiency: int
    time_efficiency: int
    worker_id: str
    worker_slot: int
    facility_id: str
    facility_slot: int
    start_at: datetime
    end_at: datetime
    duration_seconds: ExactFractionResponse
    inputs: list[ItemQuantityRequest]
    dependency_product_type_ids: list[TypeId]


class ScheduleResponse(ApiModel):
    start_at: datetime
    end_at: datetime
    jobs: list[ScheduledJob]
    assumptions: list[str]
