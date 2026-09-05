from dataclasses import dataclass

from app.industry.models import (
    IndustryRecipe,
    IndustryType,
    ProductionPlan,
    SolarSystem,
)
from app.industry.economics_service import ValuedProductionPlan


@dataclass(frozen=True, slots=True)
class TypeSearchResult:
    sde_build_number: int
    items: tuple[IndustryType, ...]


@dataclass(frozen=True, slots=True)
class SolarSystemSearchResult:
    sde_build_number: int
    systems: tuple[SolarSystem, ...]


@dataclass(frozen=True, slots=True)
class ProductRecipesResult:
    sde_build_number: int
    product: IndustryType
    recipes: tuple[IndustryRecipe, ...]
    item_types: tuple[IndustryType, ...]


@dataclass(frozen=True, slots=True)
class DescribedProductionPlan:
    plan: ProductionPlan
    item_types: tuple[IndustryType, ...]
    valuation: ValuedProductionPlan | None = None
