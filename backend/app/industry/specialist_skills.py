from dataclasses import dataclass
from collections.abc import Mapping

from app.industry.errors import IndustryPlanningError, InvalidIndustryDataError
from app.industry.models import AppliedSpecialistSkill, CharacterIndustrySkills, RecipeKey


MAX_SKILL_LEVEL = 5
INDUSTRY_SKILL_TYPE_ID = 3380
REACTIONS_SKILL_TYPE_ID = 45746

# Verified against CCP's public ESI type descriptions on 2026-09-05:
# https://esi.evetech.net/latest/universe/types/{type_id}/?language=en
# Only skills explicitly granting manufacturing time bonuses belong here.
# Required skills such as Capital Ship Construction and Science grant none.
MANUFACTURING_TIME_BONUSES = {
    3395: 100,  # Advanced Small Ship Construction
    3396: 100,  # Advanced Industrial Ship Construction
    3397: 100,  # Advanced Medium Ship Construction
    3398: 100,  # Advanced Large Ship Construction
    3400: 100,  # Outpost Construction
    77725: 100,  # Advanced Capital Ship Construction
    11433: 100,  # High Energy Physics
    11441: 100,  # Plasma Physics
    11442: 100,  # Nanite Engineering
    11443: 100,  # Hydromagnetic Physics
    11444: 100,  # Amarr Starship Engineering
    11445: 100,  # Minmatar Starship Engineering
    11446: 100,  # Graviton Physics
    11447: 100,  # Laser Physics
    11448: 100,  # Electromagnetic Physics
    11449: 100,  # Rocket Science
    11450: 100,  # Gallente Starship Engineering
    11451: 100,  # Nuclear Physics
    11452: 100,  # Mechanical Engineering
    11453: 100,  # Electronic Engineering
    11454: 100,  # Caldari Starship Engineering
    11455: 100,  # Quantum Physics
    11529: 100,  # Molecular Engineering
    52307: 100,  # Triglavian Quantum Engineering
    81050: 100,  # Upwell Starship Engineering
    81896: 200,  # Mutagenic Stabilization
}


def manufacturing_skill_bonuses(
    requirements: tuple["SpecialistSkillRequirement", ...],
    levels: Mapping[int, int],
) -> tuple[AppliedSpecialistSkill, ...]:
    return tuple(
        AppliedSpecialistSkill(type_id, levels[type_id], MANUFACTURING_TIME_BONUSES[type_id])
        for type_id in sorted({requirement.type_id for requirement in requirements})
        if type_id in MANUFACTURING_TIME_BONUSES and levels.get(type_id, 0) > 0
    )


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
        super().__init__(
            f"Blueprint specialist skill requirements are not met: {details}"
        )


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


def effective_required_skill_level(
    type_id: int,
    specialist_skill_levels: Mapping[int, int],
    generic_skills: CharacterIndustrySkills,
) -> int:
    """Resolve one SDE activity requirement from the request's skill inputs.

    Industry and Reactions already have dedicated fields in ProductionProfile.
    Accepting the maximum also preserves compatibility if an older client sends
    either of those type IDs through the additive specialist skill list.
    """
    level = specialist_skill_levels.get(type_id, 0)
    if type_id == INDUSTRY_SKILL_TYPE_ID:
        return max(level, generic_skills.industry_level)
    if type_id == REACTIONS_SKILL_TYPE_ID:
        return max(level, generic_skills.reactions_level)
    return level
