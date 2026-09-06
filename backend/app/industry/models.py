from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from math import isfinite

from app.industry.errors import InvalidIndustryDataError
from app.industry.setup_categories import (
    IndustrySetupCategory,
    industry_setup_category_for,
)


MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_MATERIAL_EFFICIENCY = 10
MAX_TIME_EFFICIENCY = 20
MAX_SKILL_LEVEL = 5
BASIS_POINTS_PER_UNIT = 10_000
MAX_REDUCTION_BASIS_POINTS = BASIS_POINTS_PER_UNIT - 1


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidIndustryDataError(f"{field_name} must be a positive integer")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidIndustryDataError(
            f"{field_name} must be a non-negative integer"
        )


def _require_skill_level(value: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_SKILL_LEVEL
    ):
        raise InvalidIndustryDataError(
            f"{field_name} must be an integer from 0 to 5"
        )


def _require_reduction_basis_points(value: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_REDUCTION_BASIS_POINTS
    ):
        raise InvalidIndustryDataError(
            f"{field_name} must be an integer from 0 to 9999 basis points"
        )


def _require_rate_basis_points(value: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= BASIS_POINTS_PER_UNIT
    ):
        raise InvalidIndustryDataError(
            f"{field_name} must be an integer from 0 to 10000 basis points"
        )


def _reduction_factor(reduction_basis_points: int) -> Fraction:
    return Fraction(
        BASIS_POINTS_PER_UNIT - reduction_basis_points,
        BASIS_POINTS_PER_UNIT,
    )


class ActivityKind(StrEnum):
    MANUFACTURING = "manufacturing"
    REACTION = "reaction"


class BuildDecision(StrEnum):
    AUTO = "auto"
    BUY = "buy"
    BUILD = "build"


class PurchaseReason(StrEnum):
    NO_RECIPE = "no_recipe"
    BUY_OVERRIDE = "buy_override"


@dataclass(frozen=True, slots=True, order=True)
class RecipeKey:
    blueprint_type_id: int
    activity_id: int

    def __post_init__(self) -> None:
        _require_positive_int(self.blueprint_type_id, "blueprint_type_id")
        _require_positive_int(self.activity_id, "activity_id")

    def __str__(self) -> str:
        return f"{self.blueprint_type_id}:{self.activity_id}"


@dataclass(frozen=True, slots=True, order=True)
class ItemQuantity:
    type_id: int
    quantity: int

    def __post_init__(self) -> None:
        _require_positive_int(self.type_id, "type_id")
        _require_positive_int(self.quantity, "quantity")


@dataclass(frozen=True, slots=True)
class IndustryType:
    type_id: int
    name: str
    published: bool
    group_id: int
    group_name: str
    category_id: int
    category_name: str

    def __post_init__(self) -> None:
        _require_non_negative_int(self.type_id, "type_id")
        _require_non_negative_int(self.group_id, "group_id")
        _require_non_negative_int(self.category_id, "category_id")
        if not isinstance(self.published, bool):
            raise InvalidIndustryDataError("published must be a boolean")
        for field_name, value in (
            ("name", self.name),
            ("group_name", self.group_name),
            ("category_name", self.category_name),
        ):
            if not value:
                raise InvalidIndustryDataError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class RigScopeGroup:
    group_id: int
    group_name: str
    category_id: int
    category_name: str


@dataclass(frozen=True, slots=True)
class SolarSystem:
    solar_system_id: int
    name: str
    security_status: float | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.solar_system_id, "solar_system_id")
        if not self.name:
            raise InvalidIndustryDataError("solar system name must not be empty")
        if self.security_status is not None and (
            isinstance(self.security_status, bool)
            or not isinstance(self.security_status, (float, int))
            or not isfinite(self.security_status)
            or not -1 <= self.security_status <= 1
        ):
            raise InvalidIndustryDataError("security_status must be between -1 and 1")

    @property
    def security_space(self) -> str | None:
        # CCP's system-security and ID-range guides: use true security, not
        # Python's rounded display value (0.45 is already highsec).
        if self.security_status is None:
            return None
        if 31_000_000 <= self.solar_system_id <= 31_999_999:
            return "wormhole"
        if not 30_000_000 <= self.solar_system_id <= 30_999_999:
            return None
        if self.security_status >= 0.45:
            return "highsec"
        return "lowsec" if self.security_status > 0 else "nullsec"


@dataclass(frozen=True, slots=True)
class IndustryRecipe:
    key: RecipeKey
    blueprint_name: str
    activity: ActivityKind
    time_seconds: int
    max_production_limit: int | None
    products: tuple[ItemQuantity, ...]
    materials: tuple[ItemQuantity, ...]

    def __post_init__(self) -> None:
        if not self.blueprint_name:
            raise InvalidIndustryDataError("blueprint_name must not be empty")
        if not isinstance(self.activity, ActivityKind):
            raise InvalidIndustryDataError("activity must be an ActivityKind")
        _require_positive_int(self.time_seconds, "time_seconds")
        if self.max_production_limit is not None:
            _require_positive_int(
                self.max_production_limit,
                "max_production_limit",
            )
        if not self.products:
            raise InvalidIndustryDataError("A recipe must have at least one product")

        product_ids = [product.type_id for product in self.products]
        material_ids = [material.type_id for material in self.materials]
        if len(product_ids) != len(set(product_ids)):
            raise InvalidIndustryDataError("A recipe repeats a product type")
        if len(material_ids) != len(set(material_ids)):
            raise InvalidIndustryDataError("A recipe repeats a material type")

        object.__setattr__(
            self,
            "products",
            tuple(sorted(self.products, key=lambda item: item.type_id)),
        )
        object.__setattr__(
            self,
            "materials",
            tuple(sorted(self.materials, key=lambda item: item.type_id)),
        )

    def output_quantity_for(self, type_id: int) -> int | None:
        return next(
            (
                product.quantity
                for product in self.products
                if product.type_id == type_id
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class BuildChoice:
    decision: BuildDecision = BuildDecision.AUTO
    recipe_key: RecipeKey | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, BuildDecision):
            raise InvalidIndustryDataError("decision must be a BuildDecision")
        if self.decision != BuildDecision.BUILD and self.recipe_key is not None:
            raise InvalidIndustryDataError(
                "Only an explicit build choice may select a recipe"
            )


@dataclass(frozen=True, slots=True)
class BlueprintEfficiency:
    material_efficiency: int = 0
    time_efficiency: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.material_efficiency, bool)
            or not isinstance(self.material_efficiency, int)
            or not 0
            <= self.material_efficiency
            <= MAX_MATERIAL_EFFICIENCY
        ):
            raise InvalidIndustryDataError(
                "material_efficiency must be an integer from 0 to 10"
            )
        if (
            isinstance(self.time_efficiency, bool)
            or not isinstance(self.time_efficiency, int)
            or not 0 <= self.time_efficiency <= MAX_TIME_EFFICIENCY
            or self.time_efficiency % 2 != 0
        ):
            raise InvalidIndustryDataError(
                "time_efficiency must be an even integer from 0 to 20"
            )

    @property
    def is_unresearched(self) -> bool:
        return self.material_efficiency == 0 and self.time_efficiency == 0


@dataclass(frozen=True, slots=True)
class CharacterIndustrySkills:
    """Skill levels whose documented effects apply to supported activities."""

    industry_level: int = 0
    advanced_industry_level: int = 0
    reactions_level: int = 0

    def __post_init__(self) -> None:
        _require_skill_level(self.industry_level, "industry_level")
        _require_skill_level(
            self.advanced_industry_level,
            "advanced_industry_level",
        )
        _require_skill_level(self.reactions_level, "reactions_level")


@dataclass(frozen=True, slots=True)
class FacilityModifier:
    """Exact final facility reductions for one activity, in basis points."""

    activity: ActivityKind
    material_reduction_basis_points: int = 0
    time_reduction_basis_points: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.activity, ActivityKind):
            raise InvalidIndustryDataError(
                "facility modifier activity must be an ActivityKind"
            )
        _require_reduction_basis_points(
            self.material_reduction_basis_points,
            "facility material_reduction_basis_points",
        )
        _require_reduction_basis_points(
            self.time_reduction_basis_points,
            "facility time_reduction_basis_points",
        )
        if (
            self.material_reduction_basis_points == 0
            and self.time_reduction_basis_points == 0
        ):
            raise InvalidIndustryDataError(
                "facility modifier must reduce material requirements or job time"
            )


@dataclass(frozen=True, slots=True)
class RigModifier:
    """Exact final rig reductions, optionally scoped to product taxonomy.

    Category and group scopes form a union. An empty scope applies to every
    product made by the selected activity. Values are final reductions, so a
    caller must apply any security-space scaling before constructing the rule.
    """

    activity: ActivityKind
    material_reduction_basis_points: int = 0
    time_reduction_basis_points: int = 0
    category_ids: tuple[int, ...] = ()
    group_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.activity, ActivityKind):
            raise InvalidIndustryDataError(
                "rig modifier activity must be an ActivityKind"
            )
        _require_reduction_basis_points(
            self.material_reduction_basis_points,
            "rig material_reduction_basis_points",
        )
        _require_reduction_basis_points(
            self.time_reduction_basis_points,
            "rig time_reduction_basis_points",
        )
        if (
            self.material_reduction_basis_points == 0
            and self.time_reduction_basis_points == 0
        ):
            raise InvalidIndustryDataError(
                "rig modifier must reduce material requirements or job time"
            )
        for field_name, values in (
            ("category_ids", self.category_ids),
            ("group_ids", self.group_ids),
        ):
            if not isinstance(values, tuple):
                raise InvalidIndustryDataError(
                    f"rig modifier {field_name} must be a tuple"
                )
            for value in values:
                _require_positive_int(value, f"rig modifier {field_name}")
            if len(values) != len(set(values)):
                raise InvalidIndustryDataError(
                    f"rig modifier {field_name} must not contain duplicates"
                )
            object.__setattr__(self, field_name, tuple(sorted(values)))

    def applies_to(self, item_type: IndustryType) -> bool:
        if not self.category_ids and not self.group_ids:
            return True
        return (
            item_type.category_id in self.category_ids
            or item_type.group_id in self.group_ids
        )


@dataclass(frozen=True, slots=True)
class IndustrySetupOverride:
    """A complete manufacturing setup for one recognized product bucket."""

    category: IndustrySetupCategory
    solar_system_id: int
    facility_material_reduction_basis_points: int = 0
    facility_time_reduction_basis_points: int = 0
    rig_material_reduction_basis_points: int = 0
    rig_time_reduction_basis_points: int = 0
    job_cost_reduction_basis_points: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.category, IndustrySetupCategory):
            raise InvalidIndustryDataError(
                "industry setup override category must be an "
                "IndustrySetupCategory"
            )
        _require_positive_int(self.solar_system_id, "solar_system_id")
        for field_name in (
            "facility_material_reduction_basis_points",
            "facility_time_reduction_basis_points",
            "rig_material_reduction_basis_points",
            "rig_time_reduction_basis_points",
        ):
            _require_reduction_basis_points(
                getattr(self, field_name),
                f"industry setup override {field_name}",
            )
        _require_rate_basis_points(
            self.job_cost_reduction_basis_points,
            "industry setup override job_cost_reduction_basis_points",
        )


@dataclass(frozen=True, slots=True)
class ProductionProfile:
    """Immutable request-scoped production settings used by the pure planner."""

    skills: CharacterIndustrySkills = field(
        default_factory=CharacterIndustrySkills
    )
    facility_modifiers: tuple[FacilityModifier, ...] = ()
    rig_modifiers: tuple[RigModifier, ...] = ()
    setup_overrides: tuple[IndustrySetupOverride, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.skills, CharacterIndustrySkills):
            raise InvalidIndustryDataError(
                "production profile skills must be CharacterIndustrySkills"
            )
        if not isinstance(self.facility_modifiers, tuple):
            raise InvalidIndustryDataError(
                "facility_modifiers must be a tuple"
            )
        if not isinstance(self.rig_modifiers, tuple):
            raise InvalidIndustryDataError("rig_modifiers must be a tuple")
        if not isinstance(self.setup_overrides, tuple):
            raise InvalidIndustryDataError("setup_overrides must be a tuple")
        if not all(
            isinstance(modifier, FacilityModifier)
            for modifier in self.facility_modifiers
        ):
            raise InvalidIndustryDataError(
                "facility_modifiers must contain FacilityModifier values"
            )
        if not all(
            isinstance(modifier, RigModifier)
            for modifier in self.rig_modifiers
        ):
            raise InvalidIndustryDataError(
                "rig_modifiers must contain RigModifier values"
            )
        if not all(
            isinstance(override, IndustrySetupOverride)
            for override in self.setup_overrides
        ):
            raise InvalidIndustryDataError(
                "setup_overrides must contain IndustrySetupOverride values"
            )

        facility_activities = [
            modifier.activity for modifier in self.facility_modifiers
        ]
        if len(facility_activities) != len(set(facility_activities)):
            raise InvalidIndustryDataError(
                "production profile may contain only one facility modifier "
                "per activity"
            )
        setup_categories = [
            override.category for override in self.setup_overrides
        ]
        if len(setup_categories) != len(set(setup_categories)):
            raise InvalidIndustryDataError(
                "production profile may contain only one setup override "
                "per category"
            )
        object.__setattr__(
            self,
            "facility_modifiers",
            tuple(
                sorted(
                    self.facility_modifiers,
                    key=lambda modifier: modifier.activity.value,
                )
            ),
        )
        object.__setattr__(
            self,
            "rig_modifiers",
            tuple(
                sorted(
                    self.rig_modifiers,
                    key=lambda modifier: (
                        modifier.activity.value,
                        modifier.category_ids,
                        modifier.group_ids,
                        modifier.material_reduction_basis_points,
                        modifier.time_reduction_basis_points,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "setup_overrides",
            tuple(
                sorted(
                    self.setup_overrides,
                    key=lambda override: override.category.value,
                )
            ),
        )

    def facility_for(self, activity: ActivityKind) -> FacilityModifier | None:
        return next(
            (
                modifier
                for modifier in self.facility_modifiers
                if modifier.activity == activity
            ),
            None,
        )

    def override_for(
        self,
        item_type: IndustryType,
    ) -> IndustrySetupOverride | None:
        if not isinstance(item_type, IndustryType):
            raise InvalidIndustryDataError(
                "setup override product metadata must be an IndustryType"
            )
        category = industry_setup_category_for(
            category_id=item_type.category_id,
            group_id=item_type.group_id,
        )
        if category is None:
            return None
        return next(
            (
                override
                for override in self.setup_overrides
                if override.category == category
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class AppliedIndustrySetupOverride:
    """Pricing identity retained after a setup override is resolved."""

    category: IndustrySetupCategory
    solar_system_id: int
    job_cost_reduction_basis_points: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.category, IndustrySetupCategory):
            raise InvalidIndustryDataError(
                "applied industry setup category must be an "
                "IndustrySetupCategory"
            )
        _require_positive_int(self.solar_system_id, "solar_system_id")
        _require_rate_basis_points(
            self.job_cost_reduction_basis_points,
            "applied industry setup job_cost_reduction_basis_points",
        )


@dataclass(frozen=True, slots=True)
class AppliedSpecialistSkill:
    type_id: int
    level: int
    time_reduction_per_level_basis_points: int

    def __post_init__(self) -> None:
        _require_positive_int(self.type_id, "specialist skill type_id")
        _require_skill_level(self.level, "specialist skill level")
        _require_reduction_basis_points(
            self.time_reduction_per_level_basis_points,
            "specialist time reduction per level",
        )
        _require_reduction_basis_points(
            self.level * self.time_reduction_per_level_basis_points,
            "specialist time reduction",
        )

    @property
    def time_multiplier(self) -> Fraction:
        return _reduction_factor(
            self.level * self.time_reduction_per_level_basis_points
        )


@dataclass(frozen=True, slots=True)
class AppliedProductionModifiers:
    """Resolved exact modifier factors for one production step."""

    activity: ActivityKind
    skills: CharacterIndustrySkills
    facility_material_reduction_basis_points: int = 0
    facility_time_reduction_basis_points: int = 0
    rig_material_reduction_basis_points: int = 0
    rig_time_reduction_basis_points: int = 0
    specialist_skills: tuple[AppliedSpecialistSkill, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.activity, ActivityKind):
            raise InvalidIndustryDataError(
                "applied modifier activity must be an ActivityKind"
            )
        if not isinstance(self.skills, CharacterIndustrySkills):
            raise InvalidIndustryDataError(
                "applied modifier skills must be CharacterIndustrySkills"
            )
        for field_name in (
            "facility_material_reduction_basis_points",
            "facility_time_reduction_basis_points",
            "rig_material_reduction_basis_points",
            "rig_time_reduction_basis_points",
        ):
            _require_reduction_basis_points(
                getattr(self, field_name),
                field_name,
            )

    @property
    def character_time_multiplier(self) -> Fraction:
        if self.activity == ActivityKind.MANUFACTURING:
            return Fraction(100 - 4 * self.skills.industry_level, 100) * Fraction(
                100 - 3 * self.skills.advanced_industry_level,
                100,
            )
        return Fraction(100 - 4 * self.skills.reactions_level, 100)

    @property
    def facility_material_multiplier(self) -> Fraction:
        return _reduction_factor(
            self.facility_material_reduction_basis_points
        )

    @property
    def facility_time_multiplier(self) -> Fraction:
        return _reduction_factor(self.facility_time_reduction_basis_points)

    @property
    def rig_material_multiplier(self) -> Fraction:
        return _reduction_factor(self.rig_material_reduction_basis_points)

    @property
    def rig_time_multiplier(self) -> Fraction:
        return _reduction_factor(self.rig_time_reduction_basis_points)

    @property
    def material_multiplier(self) -> Fraction:
        return self.facility_material_multiplier * self.rig_material_multiplier

    @property
    def specialist_time_multiplier(self) -> Fraction:
        multiplier = Fraction(1)
        if self.activity == ActivityKind.MANUFACTURING:
            for skill in self.specialist_skills:
                multiplier *= skill.time_multiplier
        return multiplier

    @property
    def time_multiplier(self) -> Fraction:
        return (
            self.character_time_multiplier
            * self.specialist_time_multiplier
            * self.facility_time_multiplier
            * self.rig_time_multiplier
        )


@dataclass(frozen=True, slots=True)
class ProductionStep:
    product_type_id: int
    recipe: IndustryRecipe
    required_quantity: int
    output_per_run: int
    runs: int
    produced_quantity: int
    surplus_quantity: int
    blueprint_efficiency: BlueprintEfficiency | None
    production_modifiers: AppliedProductionModifiers
    base_total_job_time_seconds: int
    exact_job_time_seconds: Fraction
    inputs: tuple[ItemQuantity, ...]
    industry_setup_override: AppliedIndustrySetupOverride | None = None

    @property
    def total_job_time_centiseconds(self) -> int | None:
        """Return centiseconds only when that unit is exactly representable."""
        centiseconds = self.exact_job_time_seconds * 100
        if centiseconds.denominator != 1:
            return None
        return centiseconds.numerator

    @property
    def display_job_time_seconds(self) -> int:
        """Return truncated whole seconds for human-readable display only.

        ``exact_job_time_seconds`` is the authoritative duration; this
        convenience value deliberately discards any fractional second.
        """
        return (
            self.exact_job_time_seconds.numerator
            // self.exact_job_time_seconds.denominator
        )


@dataclass(frozen=True, slots=True, order=True)
class PurchaseRequirement:
    type_id: int
    quantity: int
    reason: PurchaseReason


@dataclass(frozen=True, slots=True)
class ProductionPlan:
    sde_build_number: int
    requested: tuple[ItemQuantity, ...]
    build_steps: tuple[ProductionStep, ...]
    purchases: tuple[PurchaseRequirement, ...]
    consumed_inventory: tuple[ItemQuantity, ...] = ()
