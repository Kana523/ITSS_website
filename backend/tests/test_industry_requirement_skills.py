from collections.abc import Collection

import pytest

from app.industry.models import (
    ActivityKind,
    CharacterIndustrySkills,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    ProductionProfile,
    RecipeKey,
)
from app.industry.service import IndustryPlanningService
from app.industry.specialist_skills import (
    INDUSTRY_SKILL_TYPE_ID,
    REACTIONS_SKILL_TYPE_ID,
    MissingSpecialistSkillsError,
    SpecialistSkillRequirement,
    effective_required_skill_level,
)


def test_generic_profile_levels_are_reused_for_sde_skill_requirements() -> None:
    skills = CharacterIndustrySkills(
        industry_level=5,
        advanced_industry_level=5,
        reactions_level=4,
    )

    assert effective_required_skill_level(
        INDUSTRY_SKILL_TYPE_ID,
        {},
        skills,
    ) == 5
    assert effective_required_skill_level(
        REACTIONS_SKILL_TYPE_ID,
        {},
        skills,
    ) == 4
    assert effective_required_skill_level(30_001, {30_001: 3}, skills) == 3


class IndustryRequirementRepository:
    recipe = IndustryRecipe(
        key=RecipeKey(2001, 1),
        blueprint_name="Industry Requirement Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(1001, 1),),
        materials=(ItemQuantity(1002, 1),),
    )

    def latest_sde_build_number(self) -> int | None:
        return 9_000_001

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        return {
            type_id: IndustryType(
                type_id=type_id,
                name=f"Type {type_id}",
                published=True,
                group_id=10,
                group_name="Group",
                category_id=1,
                category_name="Category",
            )
            for type_id in type_ids
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        return {
            type_id: (self.recipe,) if type_id == 1001 else ()
            for type_id in product_type_ids
        }

    def load_recipe_skill_requirements(
        self,
        recipe_keys: Collection[RecipeKey],
    ) -> dict[RecipeKey, tuple[SpecialistSkillRequirement, ...]]:
        return {
            key: (
                (SpecialistSkillRequirement(INDUSTRY_SKILL_TYPE_ID, 1),)
                if key == self.recipe.key
                else ()
            )
            for key in recipe_keys
        }


def test_planner_does_not_require_industry_skill_twice() -> None:
    service = IndustryPlanningService(IndustryRequirementRepository())

    with pytest.raises(MissingSpecialistSkillsError):
        service.create_plan(
            (ItemQuantity(1001, 1),),
            specialist_skill_levels={},
        )

    plan = service.create_plan(
        (ItemQuantity(1001, 1),),
        production_profile=ProductionProfile(
            skills=CharacterIndustrySkills(industry_level=1)
        ),
        specialist_skill_levels={},
    )

    assert plan.build_steps[0].runs == 1
