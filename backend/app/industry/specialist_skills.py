from dataclasses import dataclass

from app.industry.errors import IndustryPlanningError, InvalidIndustryDataError
from app.industry.models import RecipeKey


MAX_SKILL_LEVEL = 5


@dataclass(frozen=True, slots=True, order=True)
class SpecialistSkillRequirement:
    type_id: int
    level: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.type_id, bool)
            or not isinstance(self.type_id, int)
            or self.type_id <= 0
        ):
            raise InvalidIndustryDataError(
                "specialist skill type_id must be a positive integer"
            )
        if (
            isinstance(self.level, bool)
            or not isinstance(self.level, int)
            or not 1 <= self.level <= MAX_SKILL_LEVEL
        ):
            raise InvalidIndustryDataError(
                "specialist skill requirement level must be from 1 to 5"
            )


class MissingSpecialistSkillsError(IndustryPlanningError):
    def __init__(
        self,
        missing: tuple[tuple[RecipeKey, SpecialistSkillRequirement, int], ...],
    ) -> None:
        self.missing = missing
        details = ", ".join(
            f"{recipe_key}: skill {requirement.type_id} "
            f"{current_level}/{requirement.level}"
            for recipe_key, requirement, current_level in missing
        )
        super().__init__(f"Blueprint specialist skill requirements are not met: {details}")


def normalize_specialist_skill_levels(
    levels: dict[int, int] | None,
) -> dict[int, int]:
    normalized: dict[int, int] = {}
    for type_id, level in (levels or {}).items():
        if (
            isinstance(type_id, bool)
            or not isinstance(type_id, int)
            or type_id <= 0
        ):
            raise InvalidIndustryDataError(
                "specialist skill type IDs must be positive integers"
            )
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or not 0 <= level <= MAX_SKILL_LEVEL
        ):
            raise InvalidIndustryDataError(
                f"specialist skill level for type {type_id} must be from 0 to 5"
            )
        normalized[type_id] = level
    return dict(sorted(normalized.items()))
