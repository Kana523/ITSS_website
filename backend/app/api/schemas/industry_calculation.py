from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.api.schemas.industry import (
    ApiModel,
    CalculationRequest,
    CalculationResponse,
    ItemQuantityRequest,
    ProductionProfileRequest,
    Quantity,
    RecipeKeyRequest,
    SkillLevel,
    TypeId,
    calculation_response,
)
from app.industry.implants import ManufacturingTimeImplant
from app.industry.models import RecipeKey
from app.industry.views import DescribedProductionPlan


class BlueprintCopyRunLimitRequest(ApiModel):
    recipe_key: RecipeKeyRequest
    runs_per_copy: Quantity

    def to_domain(self) -> tuple[RecipeKey, int]:
        return self.recipe_key.to_domain(), self.runs_per_copy


class SpecialistSkillLevelRequest(ApiModel):
    type_id: TypeId
    level: SkillLevel


class ImplantProductionProfileRequest(ProductionProfileRequest):
    """Production profile with the supported manufacturing-time hardwiring."""

    manufacturing_time_implant: ManufacturingTimeImplant | None = None


AppliedModifier = Literal[
    "owned_materials",
    "blueprint_material_efficiency",
    "blueprint_time_efficiency",
    "industry_skill_time",
    "advanced_industry_skill_time",
    "specialist_skill_time",
    "reactions_skill_time",
    "manufacturing_implant_time",
    "facility_material_efficiency",
    "facility_time_efficiency",
    "rig_material_efficiency",
    "rig_time_efficiency",
]


class IndustryCalculationResponse(CalculationResponse):
    """Calculation response with the additive implant modifier label."""

    applied_modifiers: tuple[AppliedModifier, ...]


class IndustryCalculationRequest(CalculationRequest):
    """Backward-compatible calculation request with additive planner inputs."""

    production_profile: ImplantProductionProfileRequest | None = None
    owned_materials: Annotated[
        list[ItemQuantityRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)
    blueprint_copy_run_limits: Annotated[
        list[BlueprintCopyRunLimitRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)
    specialist_skills: Annotated[
        list[SpecialistSkillLevelRequest],
        Field(max_length=500),
    ] | None = None

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
        if self.specialist_skills is not None:
            skill_type_ids = [item.type_id for item in self.specialist_skills]
            if len(skill_type_ids) != len(set(skill_type_ids)):
                raise ValueError(
                    "specialist_skills must contain at most one entry per type_id"
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

    def to_specialist_skill_levels(self) -> dict[int, int] | None:
        if self.specialist_skills is None:
            return None
        return {
            item.type_id: item.level
            for item in self.specialist_skills
        }

    def to_manufacturing_time_implant(self) -> ManufacturingTimeImplant | None:
        if self.production_profile is None:
            return None
        return self.production_profile.manufacturing_time_implant


def _multiply_fraction_payload(
    payload: dict[str, str],
    multiplier: Fraction,
) -> dict[str, str]:
    value = Fraction(int(payload["numerator"]), int(payload["denominator"]))
    value *= multiplier
    return {
        "numerator": str(value.numerator),
        "denominator": str(value.denominator),
    }


def industry_calculation_response(
    result: DescribedProductionPlan,
    implant: ManufacturingTimeImplant | None,
    *,
    owned_materials_included: bool,
) -> IndustryCalculationResponse:
    """Build the stable calculation response plus implant-specific metadata."""
    base = calculation_response(result)
    payload = base.model_dump(mode="python")

    labels = list(payload["applied_modifiers"])
    if owned_materials_included:
        labels.insert(0, "owned_materials")

    has_manufacturing = any(
        step["activity"] == "manufacturing"
        for step in payload["build_steps"]
    )
    if implant is not None and has_manufacturing:
        multiplier = implant.time_multiplier
        insert_at = next(
            (
                index
                for index, label in enumerate(labels)
                if label.startswith("facility_") or label.startswith("rig_")
            ),
            len(labels),
        )
        labels.insert(insert_at, "manufacturing_implant_time")
        for step in payload["build_steps"]:
            if step["activity"] != "manufacturing":
                continue
            modifiers = step["production_modifiers"]
            modifiers["time_multiplier"] = _multiply_fraction_payload(
                modifiers["time_multiplier"],
                multiplier,
            )
    payload["applied_modifiers"] = tuple(labels)

    included_modifiers = set()
    if owned_materials_included:
        included_modifiers.add("owned_materials")
    if implant is not None and has_manufacturing:
        included_modifiers.add("character_implants")
    payload["excluded_modifiers"] = tuple(
        modifier
        for modifier in payload["excluded_modifiers"]
        if modifier not in included_modifiers
    )
    return IndustryCalculationResponse.model_validate(payload)
