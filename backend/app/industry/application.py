from collections.abc import Iterable, Mapping

from app.industry.errors import (
    IndustryPlanningError,
    InvalidIndustryDataError,
    SdeNotImportedError,
    UnknownTypeError,
)
from app.industry.economics_service import (
    IndustryEconomicsService,
    IndustryPricingOptions,
)
from app.industry.models import (
    BlueprintEfficiency,
    BuildChoice,
    IndustryType,
    ItemQuantity,
    ProductionProfile,
    RecipeKey,
)
from app.industry.repository import IndustryDataRepository
from app.industry.service import IndustryPlanningService
from app.industry.views import (
    DescribedProductionPlan,
    ProductRecipesResult,
    TypeSearchResult,
)


class IndustryApplicationService:
    """Application facade consumed by HTTP and future CLI boundaries."""

    def __init__(
        self,
        repository: IndustryDataRepository,
        economics_service: IndustryEconomicsService | None = None,
    ) -> None:
        self._repository = repository
        self._planning = IndustryPlanningService(repository)
        self._economics = economics_service

    def _require_build_number(self) -> int:
        build_number = self._repository.latest_sde_build_number()
        if build_number is None:
            raise SdeNotImportedError(
                "An EVE SDE snapshot must be imported before using industry data"
            )
        return build_number

    def search_types(
        self,
        query: str,
        *,
        producible_only: bool = False,
        limit: int = 20,
    ) -> TypeSearchResult:
        build_number = self._require_build_number()
        return TypeSearchResult(
            sde_build_number=build_number,
            items=self._repository.search_types(
                query,
                published_only=True,
                producible_only=producible_only,
                limit=limit,
            ),
        )

    def get_product_recipes(self, product_type_id: int) -> ProductRecipesResult:
        build_number = self._require_build_number()
        loaded_product = self._repository.load_types({product_type_id})
        if product_type_id not in loaded_product:
            raise UnknownTypeError(
                (product_type_id,),
                sde_build_number=build_number,
            )
        if not loaded_product[product_type_id].published:
            raise UnknownTypeError(
                (product_type_id,),
                sde_build_number=build_number,
            )

        recipes = self._repository.load_recipes_for_products(
            {product_type_id}
        )[product_type_id]
        related_type_ids = {product_type_id}
        for recipe in recipes:
            related_type_ids.add(recipe.key.blueprint_type_id)
            related_type_ids.update(item.type_id for item in recipe.products)
            related_type_ids.update(item.type_id for item in recipe.materials)

        item_types = self._load_complete_type_set(related_type_ids)
        return ProductRecipesResult(
            sde_build_number=build_number,
            product=loaded_product[product_type_id],
            recipes=recipes,
            item_types=item_types,
        )

    def create_plan(
        self,
        demands: Iterable[ItemQuantity],
        *,
        choices: Mapping[int, BuildChoice] | None = None,
        blueprint_efficiencies: Mapping[RecipeKey, BlueprintEfficiency] | None = None,
        production_profile: ProductionProfile | None = None,
        owned_materials: Mapping[int, int] | None = None,
        blueprint_copy_run_limits: Mapping[RecipeKey, int] | None = None,
        pricing_options: IndustryPricingOptions | None = None,
        expected_sde_build_number: int | None = None,
    ) -> DescribedProductionPlan:
        plan = self._planning.create_plan(
            demands,
            choices=choices,
            blueprint_efficiencies=blueprint_efficiencies,
            production_profile=production_profile,
            owned_materials=owned_materials,
            blueprint_copy_run_limits=blueprint_copy_run_limits,
            expected_sde_build_number=expected_sde_build_number,
        )
        related_type_ids = {item.type_id for item in plan.requested}
        related_type_ids.update(item.type_id for item in plan.purchases)
        for step in plan.build_steps:
            related_type_ids.add(step.product_type_id)
            related_type_ids.add(step.recipe.key.blueprint_type_id)
            related_type_ids.update(item.type_id for item in step.recipe.products)
            related_type_ids.update(item.type_id for item in step.inputs)

        valuation = None
        if pricing_options is not None:
            if self._economics is None:
                raise InvalidIndustryDataError(
                    "Market pricing is not configured for this application"
                )
            try:
                valuation = self._economics.value_plan(plan, pricing_options)
            except IndustryPlanningError as exc:
                exc.attach_sde_build_number(plan.sde_build_number)
                raise

        return DescribedProductionPlan(
            plan=plan,
            item_types=self._load_complete_type_set(related_type_ids),
            valuation=valuation,
        )

    def _load_complete_type_set(
        self,
        type_ids: set[int],
    ) -> tuple[IndustryType, ...]:
        loaded_types = self._repository.load_types(type_ids)
        missing_type_ids = tuple(sorted(type_ids - loaded_types.keys()))
        if missing_type_ids:
            raise InvalidIndustryDataError(
                "Industry data references missing EVE type ID(s): "
                + ", ".join(str(type_id) for type_id in missing_type_ids)
            )
        return tuple(loaded_types[type_id] for type_id in sorted(loaded_types))
