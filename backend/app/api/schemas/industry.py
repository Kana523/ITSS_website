from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.api.schemas.economics import (
    IndustryPricingRequest,
    ValuationResponse,
    valuation_response,
)
from app.industry.economics_service import IndustryPricingOptions

from app.industry.models import (
    ActivityKind,
    BlueprintEfficiency,
    BuildChoice,
    BuildDecision,
    CharacterIndustrySkills,
    FacilityModifier,
    IndustrySetupOverride,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    MAX_REDUCTION_BASIS_POINTS,
    MAX_SAFE_INTEGER,
    ProductionProfile,
    PurchaseReason,
    RecipeKey,
    RigModifier,
)
from app.industry.setup_categories import IndustrySetupCategory
from app.industry.views import (
    DescribedProductionPlan,
    ProductRecipesResult,
    SolarSystemSearchResult,
    TypeSearchResult,
)


TypeId = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]
SdeBuildNumber = Annotated[
    int,
    Field(strict=True, gt=0, le=9_223_372_036_854_775_807),
]
Quantity = Annotated[
    int,
    Field(strict=True, gt=0, le=MAX_SAFE_INTEGER),
]
NonNegativeQuantity = Annotated[
    int,
    Field(strict=True, ge=0, le=MAX_SAFE_INTEGER),
]
MaterialEfficiencyPercent = Annotated[
    int,
    Field(strict=True, ge=0, le=10),
]
TimeEfficiencyPercent = Annotated[
    int,
    Field(strict=True, ge=0, le=20, multiple_of=2),
]
SkillLevel = Annotated[int, Field(strict=True, ge=0, le=5)]
ReductionBasisPoints = Annotated[
    int,
    Field(
        strict=True,
        ge=0,
        le=MAX_REDUCTION_BASIS_POINTS,
        description="Exact reduction in basis points; 100 basis points is 1%.",
    ),
]
RateBasisPoints = Annotated[int, Field(strict=True, ge=0, le=10_000)]
SearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
ExactPositiveInteger = Annotated[
    str,
    StringConstraints(pattern=r"^[1-9][0-9]*$"),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TypeSearchQuery(ApiModel):
    search: SearchText
    producible_only: bool = False
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class SolarSystemSearchQuery(ApiModel):
    search: SearchText
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class ItemQuantityRequest(ApiModel):
    type_id: TypeId
    quantity: Quantity

    def to_domain(self) -> ItemQuantity:
        return ItemQuantity(type_id=self.type_id, quantity=self.quantity)


class RecipeKeyRequest(ApiModel):
    blueprint_type_id: TypeId
    activity_id: TypeId

    def to_domain(self) -> RecipeKey:
        return RecipeKey(
            blueprint_type_id=self.blueprint_type_id,
            activity_id=self.activity_id,
        )


class BuildChoiceRequest(ApiModel):
    type_id: TypeId
    decision: BuildDecision
    recipe_key: RecipeKeyRequest | None = None

    @model_validator(mode="after")
    def validate_recipe_key(self) -> Self:
        if self.decision != BuildDecision.BUILD and self.recipe_key is not None:
            raise ValueError("recipe_key is only valid when decision is 'build'")
        return self

    def to_domain(self) -> BuildChoice:
        return BuildChoice(
            decision=self.decision,
            recipe_key=(
                self.recipe_key.to_domain()
                if self.recipe_key is not None
                else None
            ),
        )


class BlueprintEfficiencyRequest(ApiModel):
    recipe_key: RecipeKeyRequest
    material_efficiency: MaterialEfficiencyPercent
    time_efficiency: TimeEfficiencyPercent

    def to_domain(self) -> tuple[RecipeKey, BlueprintEfficiency]:
        return (
            self.recipe_key.to_domain(),
            BlueprintEfficiency(
                material_efficiency=self.material_efficiency,
                time_efficiency=self.time_efficiency,
            ),
        )


class FacilityModifierRequest(ApiModel):
    """Exact final facility bonuses for one industry activity."""

    activity: ActivityKind
    material_reduction_basis_points: ReductionBasisPoints = 0
    time_reduction_basis_points: ReductionBasisPoints = 0

    @model_validator(mode="after")
    def require_effect(self) -> Self:
        if (
            self.material_reduction_basis_points == 0
            and self.time_reduction_basis_points == 0
        ):
            raise ValueError(
                "facility modifier must reduce material requirements or job time"
            )
        return self

    def to_domain(self) -> FacilityModifier:
        return FacilityModifier(
            activity=self.activity,
            material_reduction_basis_points=(
                self.material_reduction_basis_points
            ),
            time_reduction_basis_points=self.time_reduction_basis_points,
        )


class RigModifierRequest(ApiModel):
    """Exact final rig bonuses, scoped to a union of categories and groups."""

    activity: ActivityKind
    material_reduction_basis_points: ReductionBasisPoints = 0
    time_reduction_basis_points: ReductionBasisPoints = 0
    category_ids: Annotated[list[TypeId], Field(max_length=100)] = Field(
        default_factory=list
    )
    group_ids: Annotated[list[TypeId], Field(max_length=100)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def reject_duplicate_scope_ids(self) -> Self:
        if (
            self.material_reduction_basis_points == 0
            and self.time_reduction_basis_points == 0
        ):
            raise ValueError(
                "rig modifier must reduce material requirements or job time"
            )
        if len(self.category_ids) != len(set(self.category_ids)):
            raise ValueError("category_ids must not contain duplicates")
        if len(self.group_ids) != len(set(self.group_ids)):
            raise ValueError("group_ids must not contain duplicates")
        return self

    def to_domain(self) -> RigModifier:
        return RigModifier(
            activity=self.activity,
            material_reduction_basis_points=(
                self.material_reduction_basis_points
            ),
            time_reduction_basis_points=self.time_reduction_basis_points,
            category_ids=tuple(self.category_ids),
            group_ids=tuple(self.group_ids),
        )


class IndustrySetupOverrideRequest(ApiModel):
    """Exact manufacturing setup for one supported product class."""

    category: IndustrySetupCategory
    solar_system_id: TypeId
    facility_material_reduction_basis_points: ReductionBasisPoints = 0
    facility_time_reduction_basis_points: ReductionBasisPoints = 0
    rig_material_reduction_basis_points: ReductionBasisPoints = 0
    rig_time_reduction_basis_points: ReductionBasisPoints = 0
    job_cost_reduction_basis_points: RateBasisPoints = 0

    def to_domain(self) -> IndustrySetupOverride:
        return IndustrySetupOverride(
            category=self.category,
            solar_system_id=self.solar_system_id,
            facility_material_reduction_basis_points=(
                self.facility_material_reduction_basis_points
            ),
            facility_time_reduction_basis_points=(
                self.facility_time_reduction_basis_points
            ),
            rig_material_reduction_basis_points=(
                self.rig_material_reduction_basis_points
            ),
            rig_time_reduction_basis_points=(
                self.rig_time_reduction_basis_points
            ),
            job_cost_reduction_basis_points=(
                self.job_cost_reduction_basis_points
            ),
        )


class ProductionProfileRequest(ApiModel):
    """Request-scoped skills and exact production modifiers.

    Rig reductions must already include their security-space multiplier. No
    facility or rig name is inferred from incomplete static-data metadata.
    """

    industry_level: SkillLevel = 0
    advanced_industry_level: SkillLevel = 0
    reactions_level: SkillLevel = 0
    facility_modifiers: Annotated[
        list[FacilityModifierRequest],
        Field(max_length=2),
    ] = Field(default_factory=list)
    rig_modifiers: Annotated[
        list[RigModifierRequest],
        Field(max_length=100),
    ] = Field(default_factory=list)
    setup_overrides: Annotated[
        list[IndustrySetupOverrideRequest],
        Field(max_length=14),
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_facility_activities(self) -> Self:
        activities = [
            modifier.activity for modifier in self.facility_modifiers
        ]
        if len(activities) != len(set(activities)):
            raise ValueError(
                "facility_modifiers may contain only one entry per activity"
            )
        categories = [override.category for override in self.setup_overrides]
        if len(categories) != len(set(categories)):
            raise ValueError(
                "setup_overrides may contain only one entry per category"
            )
        return self

    def to_domain(self) -> ProductionProfile:
        return ProductionProfile(
            skills=CharacterIndustrySkills(
                industry_level=self.industry_level,
                advanced_industry_level=self.advanced_industry_level,
                reactions_level=self.reactions_level,
            ),
            facility_modifiers=tuple(
                modifier.to_domain()
                for modifier in self.facility_modifiers
            ),
            rig_modifiers=tuple(
                modifier.to_domain() for modifier in self.rig_modifiers
            ),
            setup_overrides=tuple(
                override.to_domain() for override in self.setup_overrides
            ),
        )


class CalculationRequest(ApiModel):
    demands: Annotated[
        list[ItemQuantityRequest],
        Field(min_length=1, max_length=50),
    ]
    choices: Annotated[
        list[BuildChoiceRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)
    blueprint_efficiencies: Annotated[
        list[BlueprintEfficiencyRequest],
        Field(max_length=500),
    ] = Field(default_factory=list)
    production_profile: ProductionProfileRequest | None = None
    pricing: IndustryPricingRequest | None = None
    expected_sde_build_number: SdeBuildNumber | None = None

    @model_validator(mode="after")
    def reject_duplicate_choices(self) -> Self:
        type_ids = [choice.type_id for choice in self.choices]
        if len(type_ids) != len(set(type_ids)):
            raise ValueError("choices must contain at most one entry per type_id")
        recipe_keys = [
            (
                setting.recipe_key.blueprint_type_id,
                setting.recipe_key.activity_id,
            )
            for setting in self.blueprint_efficiencies
        ]
        if len(recipe_keys) != len(set(recipe_keys)):
            raise ValueError(
                "blueprint_efficiencies must contain at most one entry per "
                "recipe_key"
            )
        return self

    def to_demands(self) -> tuple[ItemQuantity, ...]:
        return tuple(demand.to_domain() for demand in self.demands)

    def to_choices(self) -> dict[int, BuildChoice]:
        return {choice.type_id: choice.to_domain() for choice in self.choices}

    def to_blueprint_efficiencies(
        self,
    ) -> dict[RecipeKey, BlueprintEfficiency]:
        return dict(setting.to_domain() for setting in self.blueprint_efficiencies)

    def to_production_profile(self) -> ProductionProfile:
        if self.production_profile is None:
            return ProductionProfile()
        return self.production_profile.to_domain()

    def to_pricing_options(self) -> IndustryPricingOptions | None:
        return self.pricing.to_domain() if self.pricing is not None else None


class IndustryTypeResponse(ApiModel):
    type_id: int
    name: str
    published: bool
    group_id: int
    group_name: str
    category_id: int
    category_name: str


class ItemReferenceResponse(ApiModel):
    type_id: int
    name: str


class ItemQuantityResponse(ApiModel):
    item: ItemReferenceResponse
    quantity: Quantity


class RecipeKeyResponse(ApiModel):
    blueprint_type_id: int
    activity_id: int


class RecipeItemResponse(ApiModel):
    item: ItemReferenceResponse
    quantity_per_run: Quantity


class IndustryRecipeResponse(ApiModel):
    recipe_key: RecipeKeyResponse
    blueprint: ItemReferenceResponse
    activity: ActivityKind
    time_seconds_per_run: int
    max_production_limit: int | None
    products: tuple[RecipeItemResponse, ...]
    materials: tuple[RecipeItemResponse, ...]
    planning_limitations: tuple[
        Literal["co_products_not_supported", "self_dependency"],
        ...,
    ]


class TypeSearchResponse(ApiModel):
    sde_build_number: SdeBuildNumber
    query: str
    result_count: int
    limit: int
    items: tuple[IndustryTypeResponse, ...]


class RigScopeGroupResponse(ApiModel):
    group_id: TypeId
    group_name: str
    category_id: TypeId
    category_name: str


class SolarSystemResponse(ApiModel):
    solar_system_id: TypeId
    name: str
    security_status: float | None
    security_space: Literal["highsec", "lowsec", "nullsec", "wormhole"] | None


class SolarSystemSearchResponse(ApiModel):
    sde_build_number: SdeBuildNumber
    query: str
    result_count: int
    limit: int
    systems: tuple[SolarSystemResponse, ...]


class ProductRecipesResponse(ApiModel):
    sde_build_number: SdeBuildNumber
    product: IndustryTypeResponse
    recipes: tuple[IndustryRecipeResponse, ...]


class ProductionInputResponse(ApiModel):
    item: ItemReferenceResponse
    quantity_per_run: Quantity
    base_total_quantity: Quantity
    total_quantity: Quantity


class BlueprintEfficiencyResponse(ApiModel):
    material_efficiency: MaterialEfficiencyPercent
    time_efficiency: TimeEfficiencyPercent


class ExactFractionResponse(ApiModel):
    """A reduced rational number encoded as strings for JSON integer safety."""

    numerator: ExactPositiveInteger
    denominator: ExactPositiveInteger


class CharacterIndustrySkillsResponse(ApiModel):
    industry_level: SkillLevel
    advanced_industry_level: SkillLevel
    reactions_level: SkillLevel


class AppliedSpecialistSkillResponse(ApiModel):
    type_id: TypeId
    level: SkillLevel
    time_reduction_per_level_basis_points: ReductionBasisPoints
    time_multiplier: ExactFractionResponse


class AppliedProductionModifiersResponse(ApiModel):
    specialist_skills: tuple[AppliedSpecialistSkillResponse, ...]
    specialist_time_multiplier: ExactFractionResponse
    skills: CharacterIndustrySkillsResponse
    character_time_multiplier: ExactFractionResponse
    facility_material_reduction_basis_points: ReductionBasisPoints
    facility_time_reduction_basis_points: ReductionBasisPoints
    rig_material_reduction_basis_points: ReductionBasisPoints
    rig_time_reduction_basis_points: ReductionBasisPoints
    facility_material_multiplier: ExactFractionResponse
    facility_time_multiplier: ExactFractionResponse
    rig_material_multiplier: ExactFractionResponse
    rig_time_multiplier: ExactFractionResponse
    material_multiplier: ExactFractionResponse
    time_multiplier: ExactFractionResponse


class ProductionStepResponse(ApiModel):
    product: ItemReferenceResponse
    recipe_key: RecipeKeyResponse
    blueprint: ItemReferenceResponse
    activity: ActivityKind
    required_quantity: Quantity
    output_per_run: Quantity
    runs: Quantity
    produced_quantity: Quantity
    surplus_quantity: NonNegativeQuantity
    blueprint_efficiency: BlueprintEfficiencyResponse | None
    production_modifiers: AppliedProductionModifiersResponse
    time_seconds_per_run: int
    base_total_job_time_seconds: Quantity
    display_job_time_seconds: NonNegativeQuantity
    exact_job_time_seconds: ExactFractionResponse
    total_job_time_centiseconds: ExactPositiveInteger | None
    inputs: tuple[ProductionInputResponse, ...]


class PurchaseRequirementResponse(ApiModel):
    item: ItemReferenceResponse
    quantity: Quantity
    reason: PurchaseReason


class CalculationResponse(ApiModel):
    sde_build_number: SdeBuildNumber
    calculation_basis: Literal["sde_base_quantities"]
    applied_modifiers: tuple[
        Literal[
            "blueprint_material_efficiency",
            "blueprint_time_efficiency",
            "industry_skill_time",
            "advanced_industry_skill_time",
            "specialist_skill_time",
            "reactions_skill_time",
            "facility_material_efficiency",
            "facility_time_efficiency",
            "rig_material_efficiency",
            "rig_time_efficiency",
        ],
        ...,
    ]
    excluded_modifiers: tuple[str, ...]
    requested: tuple[ItemQuantityResponse, ...]
    consumed_inventory: tuple[ItemQuantityResponse, ...]
    build_steps: tuple[ProductionStepResponse, ...]
    purchases: tuple[PurchaseRequirementResponse, ...]
    valuation: ValuationResponse | None


def _type_response(item: IndustryType) -> IndustryTypeResponse:
    return IndustryTypeResponse(
        type_id=item.type_id,
        name=item.name,
        published=item.published,
        group_id=item.group_id,
        group_name=item.group_name,
        category_id=item.category_id,
        category_name=item.category_name,
    )


def _item_reference(
    type_id: int,
    item_types: dict[int, IndustryType],
) -> ItemReferenceResponse:
    item = item_types[type_id]
    return ItemReferenceResponse(type_id=item.type_id, name=item.name)


def _fraction_response(value: Fraction) -> ExactFractionResponse:
    return ExactFractionResponse(
        numerator=str(value.numerator),
        denominator=str(value.denominator),
    )


def _recipe_response(
    recipe: IndustryRecipe,
    item_types: dict[int, IndustryType],
    *,
    requested_product_type_id: int,
) -> IndustryRecipeResponse:
    planning_limitations: list[
        Literal["co_products_not_supported", "self_dependency"]
    ] = []
    if len(recipe.products) != 1:
        planning_limitations.append("co_products_not_supported")
    if any(
        material.type_id == requested_product_type_id
        for material in recipe.materials
    ):
        planning_limitations.append("self_dependency")
    return IndustryRecipeResponse(
        recipe_key=RecipeKeyResponse(
            blueprint_type_id=recipe.key.blueprint_type_id,
            activity_id=recipe.key.activity_id,
        ),
        blueprint=_item_reference(recipe.key.blueprint_type_id, item_types),
        activity=recipe.activity,
        time_seconds_per_run=recipe.time_seconds,
        max_production_limit=recipe.max_production_limit,
        products=tuple(
            RecipeItemResponse(
                item=_item_reference(item.type_id, item_types),
                quantity_per_run=item.quantity,
            )
            for item in recipe.products
        ),
        materials=tuple(
            RecipeItemResponse(
                item=_item_reference(item.type_id, item_types),
                quantity_per_run=item.quantity,
            )
            for item in recipe.materials
        ),
        planning_limitations=tuple(planning_limitations),
    )


def type_search_response(
    result: TypeSearchResult,
    *,
    query: str,
    limit: int,
) -> TypeSearchResponse:
    return TypeSearchResponse(
        sde_build_number=result.sde_build_number,
        query=query,
        result_count=len(result.items),
        limit=limit,
        items=tuple(_type_response(item) for item in result.items),
    )


def solar_system_search_response(
    result: SolarSystemSearchResult,
    *,
    query: str,
    limit: int,
) -> SolarSystemSearchResponse:
    return SolarSystemSearchResponse(
        sde_build_number=result.sde_build_number,
        query=query,
        result_count=len(result.systems),
        limit=limit,
        systems=tuple(
            SolarSystemResponse(
                solar_system_id=system.solar_system_id,
                name=system.name,
                security_status=system.security_status,
                security_space=system.security_space,
            )
            for system in result.systems
        ),
    )


def product_recipes_response(
    result: ProductRecipesResult,
) -> ProductRecipesResponse:
    item_types = {item.type_id: item for item in result.item_types}
    return ProductRecipesResponse(
        sde_build_number=result.sde_build_number,
        product=_type_response(result.product),
        recipes=tuple(
            _recipe_response(
                recipe,
                item_types,
                requested_product_type_id=result.product.type_id,
            )
            for recipe in result.recipes
        ),
    )


def calculation_response(
    result: DescribedProductionPlan,
) -> CalculationResponse:
    plan = result.plan
    item_types = {item.type_id: item for item in result.item_types}
    steps: list[ProductionStepResponse] = []
    for step in plan.build_steps:
        total_inputs = {item.type_id: item.quantity for item in step.inputs}
        steps.append(
            ProductionStepResponse(
                product=_item_reference(step.product_type_id, item_types),
                recipe_key=RecipeKeyResponse(
                    blueprint_type_id=step.recipe.key.blueprint_type_id,
                    activity_id=step.recipe.key.activity_id,
                ),
                blueprint=_item_reference(
                    step.recipe.key.blueprint_type_id,
                    item_types,
                ),
                activity=step.recipe.activity,
                required_quantity=step.required_quantity,
                output_per_run=step.output_per_run,
                runs=step.runs,
                produced_quantity=step.produced_quantity,
                surplus_quantity=step.surplus_quantity,
                blueprint_efficiency=(
                    BlueprintEfficiencyResponse(
                        material_efficiency=(
                            step.blueprint_efficiency.material_efficiency
                        ),
                        time_efficiency=(
                            step.blueprint_efficiency.time_efficiency
                        ),
                    )
                    if step.blueprint_efficiency is not None
                    else None
                ),
                production_modifiers=AppliedProductionModifiersResponse(
                    specialist_skills=tuple(
                        AppliedSpecialistSkillResponse(
                            type_id=skill.type_id,
                            level=skill.level,
                            time_reduction_per_level_basis_points=skill.time_reduction_per_level_basis_points,
                            time_multiplier=_fraction_response(skill.time_multiplier),
                        )
                        for skill in step.production_modifiers.specialist_skills
                    ),
                    specialist_time_multiplier=_fraction_response(
                        step.production_modifiers.specialist_time_multiplier
                    ),
                    skills=CharacterIndustrySkillsResponse(
                        industry_level=(
                            step.production_modifiers.skills.industry_level
                        ),
                        advanced_industry_level=(
                            step.production_modifiers.skills
                            .advanced_industry_level
                        ),
                        reactions_level=(
                            step.production_modifiers.skills.reactions_level
                        ),
                    ),
                    character_time_multiplier=_fraction_response(
                        step.production_modifiers.character_time_multiplier
                    ),
                    facility_material_reduction_basis_points=(
                        step.production_modifiers
                        .facility_material_reduction_basis_points
                    ),
                    facility_time_reduction_basis_points=(
                        step.production_modifiers
                        .facility_time_reduction_basis_points
                    ),
                    rig_material_reduction_basis_points=(
                        step.production_modifiers
                        .rig_material_reduction_basis_points
                    ),
                    rig_time_reduction_basis_points=(
                        step.production_modifiers
                        .rig_time_reduction_basis_points
                    ),
                    facility_material_multiplier=_fraction_response(
                        step.production_modifiers
                        .facility_material_multiplier
                    ),
                    facility_time_multiplier=_fraction_response(
                        step.production_modifiers.facility_time_multiplier
                    ),
                    rig_material_multiplier=_fraction_response(
                        step.production_modifiers.rig_material_multiplier
                    ),
                    rig_time_multiplier=_fraction_response(
                        step.production_modifiers.rig_time_multiplier
                    ),
                    material_multiplier=_fraction_response(
                        step.production_modifiers.material_multiplier
                    ),
                    time_multiplier=_fraction_response(
                        step.production_modifiers.time_multiplier
                    ),
                ),
                time_seconds_per_run=step.recipe.time_seconds,
                base_total_job_time_seconds=(
                    step.base_total_job_time_seconds
                ),
                display_job_time_seconds=step.display_job_time_seconds,
                exact_job_time_seconds=_fraction_response(
                    step.exact_job_time_seconds
                ),
                total_job_time_centiseconds=(
                    str(step.total_job_time_centiseconds)
                    if step.total_job_time_centiseconds is not None
                    else None
                ),
                inputs=tuple(
                    ProductionInputResponse(
                        item=_item_reference(material.type_id, item_types),
                        quantity_per_run=material.quantity,
                        base_total_quantity=material.quantity * step.runs,
                        total_quantity=total_inputs[material.type_id],
                    )
                    for material in step.recipe.materials
                ),
            )
        )

    applied_modifiers: list[
        Literal[
            "blueprint_material_efficiency",
            "blueprint_time_efficiency",
            "industry_skill_time",
            "advanced_industry_skill_time",
            "reactions_skill_time",
            "facility_material_efficiency",
            "facility_time_efficiency",
            "rig_material_efficiency",
            "rig_time_efficiency",
        ]
    ] = []
    if any(
        step.blueprint_efficiency is not None
        and step.blueprint_efficiency.material_efficiency > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("blueprint_material_efficiency")
    if any(
        step.blueprint_efficiency is not None
        and step.blueprint_efficiency.time_efficiency > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("blueprint_time_efficiency")
    if any(
        step.recipe.activity == ActivityKind.MANUFACTURING
        and step.production_modifiers.skills.industry_level > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("industry_skill_time")
    if any(
        step.recipe.activity == ActivityKind.MANUFACTURING
        and step.production_modifiers.skills.advanced_industry_level > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("advanced_industry_skill_time")
    if any(
        step.recipe.activity == ActivityKind.REACTION
        and step.production_modifiers.skills.reactions_level > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("reactions_skill_time")
    if any(
        step.production_modifiers
        .facility_material_reduction_basis_points
        > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("facility_material_efficiency")
    if any(
        step.production_modifiers.facility_time_reduction_basis_points > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("facility_time_efficiency")
    if any(
        step.production_modifiers.rig_material_reduction_basis_points > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("rig_material_efficiency")
    if any(
        step.production_modifiers.rig_time_reduction_basis_points > 0
        for step in plan.build_steps
    ):
        applied_modifiers.append("rig_time_efficiency")

    return CalculationResponse(
        sde_build_number=plan.sde_build_number,
        calculation_basis="sde_base_quantities",
        applied_modifiers=tuple(applied_modifiers) + (
            ("specialist_skill_time",)
            if any(step.production_modifiers.specialist_skills for step in plan.build_steps)
            else ()
        ),
        consumed_inventory=tuple(
            ItemQuantityResponse(item=_item_reference(item.type_id, item_types), quantity=item.quantity)
            for item in plan.consumed_inventory
        ),
        excluded_modifiers=(
            "character_implants",
            "owned_materials",
            *(() if result.valuation is not None else ("market_prices",)),
        ),
        requested=tuple(
            ItemQuantityResponse(
                item=_item_reference(item.type_id, item_types),
                quantity=item.quantity,
            )
            for item in plan.requested
        ),
        build_steps=tuple(steps),
        purchases=tuple(
            PurchaseRequirementResponse(
                item=_item_reference(item.type_id, item_types),
                quantity=item.quantity,
                reason=item.reason,
            )
            for item in plan.purchases
        ),
        valuation=(
            valuation_response(result.valuation, item_types)
            if result.valuation is not None
            else None
        ),
    )
