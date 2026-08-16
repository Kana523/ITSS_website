from collections.abc import Collection, Mapping
from typing import Protocol

from app.industry.models import IndustryRecipe, IndustryType, RecipeKey
from app.industry.specialist_skills import SpecialistSkillRequirement


class IndustryCatalogRepository(Protocol):
    """Read-only item discovery for a future API boundary."""

    def search_types(
        self,
        query: str,
        *,
        published_only: bool = True,
        producible_only: bool = False,
        limit: int = 20,
    ) -> tuple[IndustryType, ...]: ...


class IndustryRepository(Protocol):
    """Read-only industry data required by the planning service."""

    def latest_sde_build_number(self) -> int | None: ...

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> Mapping[int, IndustryType]: ...

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> Mapping[int, tuple[IndustryRecipe, ...]]: ...

    def load_recipe_skill_requirements(
        self,
        recipe_keys: Collection[RecipeKey],
    ) -> Mapping[RecipeKey, tuple[SpecialistSkillRequirement, ...]]: ...


class IndustryDataRepository(
    IndustryRepository,
    IndustryCatalogRepository,
    Protocol,
):
    """Complete read boundary used by the industry application facade."""
