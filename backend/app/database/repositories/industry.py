from collections import defaultdict
from collections.abc import Collection

from sqlalchemy import and_, case, exists, func, or_, select, text, tuple_
from sqlalchemy.orm import Session, aliased

from app.industry.errors import InvalidIndustryDataError
from app.industry.models import (
    ActivityKind,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    RecipeKey,
    SolarSystem,
)
from app.industry.specialist_skills import SpecialistSkillRequirement
from app.sde.constants import SDE_IMPORT_ADVISORY_LOCK_ID
from app.sde.models import (
    Blueprint,
    EveCategory,
    EveGroup,
    EveSolarSystem,
    EveType,
    IndustryActivity,
    IndustryActivityMaterial,
    IndustryActivityProduct,
    IndustryActivitySkill,
    IndustryActivityType,
    SdeImport,
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyIndustryRepository:
    """Read industry data without exposing SQLAlchemy models to the domain."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _lock_sde_snapshot(self) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock_shared(:lock_id)"),
            {"lock_id": SDE_IMPORT_ADVISORY_LOCK_ID},
        )

    @staticmethod
    def _to_industry_type(row) -> IndustryType:
        return IndustryType(
            type_id=row.type_id,
            name=row.type_name,
            published=row.published,
            group_id=row.group_id,
            group_name=row.group_name,
            category_id=row.category_id,
            category_name=row.category_name,
        )

    @staticmethod
    def _type_select():
        return (
            select(
                EveType.type_id.label("type_id"),
                EveType.name.label("type_name"),
                EveType.published.label("published"),
                EveGroup.group_id.label("group_id"),
                EveGroup.name.label("group_name"),
                EveCategory.category_id.label("category_id"),
                EveCategory.name.label("category_name"),
            )
            .select_from(EveType)
            .join(EveGroup, EveGroup.group_id == EveType.group_id)
            .join(EveCategory, EveCategory.category_id == EveGroup.category_id)
        )

    def latest_sde_build_number(self) -> int | None:
        self._lock_sde_snapshot()
        return self._session.scalar(
            select(SdeImport.build_number).order_by(SdeImport.id.desc()).limit(1)
        )

    def search_types(
        self,
        query: str,
        *,
        published_only: bool = True,
        producible_only: bool = False,
        limit: int = 20,
    ) -> tuple[IndustryType, ...]:
        query = query.strip()
        if not query:
            return ()
        if len(query) > 255:
            raise ValueError("query must not exceed 255 characters")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer from 1 through 100")

        self._lock_sde_snapshot()
        lowered_query = query.lower()
        escaped_query = _escape_like(lowered_query)
        lowered_name = func.lower(EveType.name)
        name_match = lowered_name.like(f"%{escaped_query}%", escape="\\")

        numeric_type_id = None
        if query.isascii() and query.isdigit() and len(query) <= 10:
            parsed_type_id = int(query)
            if 0 <= parsed_type_id <= 2_147_483_647:
                numeric_type_id = parsed_type_id
        match_condition = name_match
        ranking_conditions = []
        if numeric_type_id is not None:
            match_condition = or_(EveType.type_id == numeric_type_id, name_match)
            ranking_conditions.append((EveType.type_id == numeric_type_id, 0))
        ranking_conditions.extend(
            (
                (lowered_name == lowered_query, 1),
                (lowered_name.like(f"{escaped_query}%", escape="\\"), 2),
            )
        )

        statement = self._type_select().where(match_condition)
        if published_only:
            statement = statement.where(EveType.published.is_(True))
        if producible_only:
            statement = statement.where(
                exists(
                    select(1)
                    .select_from(IndustryActivityProduct)
                    .where(
                        IndustryActivityProduct.product_type_id == EveType.type_id
                    )
                )
            )

        statement = statement.order_by(
            case(*ranking_conditions, else_=3),
            lowered_name,
            EveType.type_id,
        ).limit(limit)
        return tuple(
            self._to_industry_type(row)
            for row in self._session.execute(statement)
        )

    def search_solar_systems(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[SolarSystem, ...]:
        query = query.strip()
        if not query:
            return ()
        if len(query) > 255:
            raise ValueError("query must not exceed 255 characters")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer from 1 through 100")

        self._lock_sde_snapshot()
        lowered_query = query.lower()
        escaped_query = _escape_like(lowered_query)
        lowered_name = func.lower(EveSolarSystem.name)
        name_match = lowered_name.like(f"%{escaped_query}%", escape="\\")

        numeric_system_id = None
        if query.isascii() and query.isdigit() and len(query) <= 10:
            parsed_system_id = int(query)
            if 0 < parsed_system_id <= 2_147_483_647:
                numeric_system_id = parsed_system_id
        match_condition = name_match
        ranking_conditions = []
        if numeric_system_id is not None:
            match_condition = or_(
                EveSolarSystem.solar_system_id == numeric_system_id,
                name_match,
            )
            ranking_conditions.append(
                (EveSolarSystem.solar_system_id == numeric_system_id, 0)
            )
        ranking_conditions.extend(
            (
                (lowered_name == lowered_query, 1),
                (lowered_name.like(f"{escaped_query}%", escape="\\"), 2),
            )
        )
        statement = (
            select(EveSolarSystem.solar_system_id, EveSolarSystem.name)
            .where(match_condition)
            .order_by(
                case(*ranking_conditions, else_=3),
                lowered_name,
                EveSolarSystem.solar_system_id,
            )
            .limit(limit)
        )
        return tuple(
            SolarSystem(
                solar_system_id=row.solar_system_id,
                name=row.name,
            )
            for row in self._session.execute(statement)
        )

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        requested_ids = sorted(set(type_ids))
        if not requested_ids:
            return {}

        self._lock_sde_snapshot()
        statement = self._type_select().where(EveType.type_id.in_(requested_ids))
        return {
            industry_type.type_id: industry_type
            for industry_type in (
                self._to_industry_type(row)
                for row in self._session.execute(statement)
            )
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        requested_ids = sorted(set(product_type_ids))
        result: dict[int, tuple[IndustryRecipe, ...]] = {
            type_id: () for type_id in requested_ids
        }
        if not requested_ids:
            return result

        self._lock_sde_snapshot()
        recipe_keys = tuple(
            self._session.execute(
                select(
                    IndustryActivityProduct.blueprint_type_id,
                    IndustryActivityProduct.activity_id,
                )
                .where(
                    IndustryActivityProduct.product_type_id.in_(requested_ids)
                )
                .distinct()
            ).tuples()
        )
        if not recipe_keys:
            return result

        recipe_key_filter = tuple_(
            IndustryActivity.blueprint_type_id,
            IndustryActivity.activity_id,
        ).in_(recipe_keys)
        blueprint_type = aliased(EveType)
        header_product_rows = self._session.execute(
            select(
                IndustryActivity.blueprint_type_id.label("blueprint_type_id"),
                IndustryActivity.activity_id.label("activity_id"),
                IndustryActivity.time_seconds.label("time_seconds"),
                IndustryActivityType.code.label("activity_code"),
                Blueprint.max_production_limit.label("max_production_limit"),
                blueprint_type.name.label("blueprint_name"),
                IndustryActivityProduct.product_type_id.label("product_type_id"),
                IndustryActivityProduct.quantity.label("product_quantity"),
            )
            .select_from(IndustryActivity)
            .join(
                IndustryActivityType,
                IndustryActivityType.activity_id == IndustryActivity.activity_id,
            )
            .join(
                Blueprint,
                Blueprint.blueprint_type_id == IndustryActivity.blueprint_type_id,
            )
            .join(
                blueprint_type,
                blueprint_type.type_id == Blueprint.blueprint_type_id,
            )
            .join(
                IndustryActivityProduct,
                and_(
                    IndustryActivityProduct.blueprint_type_id
                    == IndustryActivity.blueprint_type_id,
                    IndustryActivityProduct.activity_id
                    == IndustryActivity.activity_id,
                ),
            )
            .where(recipe_key_filter)
            .order_by(
                IndustryActivity.blueprint_type_id,
                IndustryActivity.activity_id,
                IndustryActivityProduct.product_type_id,
            )
        ).mappings()

        headers: dict[RecipeKey, dict] = {}
        products: dict[RecipeKey, list[ItemQuantity]] = defaultdict(list)
        for row in header_product_rows:
            recipe_key = RecipeKey(
                blueprint_type_id=row["blueprint_type_id"],
                activity_id=row["activity_id"],
            )
            headers.setdefault(
                recipe_key,
                {
                    "blueprint_name": row["blueprint_name"],
                    "activity_code": row["activity_code"],
                    "time_seconds": row["time_seconds"],
                    "max_production_limit": row["max_production_limit"],
                },
            )
            products[recipe_key].append(
                ItemQuantity(
                    type_id=row["product_type_id"],
                    quantity=row["product_quantity"],
                )
            )

        material_key_filter = tuple_(
            IndustryActivityMaterial.blueprint_type_id,
            IndustryActivityMaterial.activity_id,
        ).in_(recipe_keys)
        material_rows = self._session.execute(
            select(
                IndustryActivityMaterial.blueprint_type_id,
                IndustryActivityMaterial.activity_id,
                IndustryActivityMaterial.material_type_id,
                IndustryActivityMaterial.quantity,
            )
            .where(material_key_filter)
            .order_by(
                IndustryActivityMaterial.blueprint_type_id,
                IndustryActivityMaterial.activity_id,
                IndustryActivityMaterial.material_type_id,
            )
        )
        materials: dict[RecipeKey, list[ItemQuantity]] = defaultdict(list)
        for row in material_rows:
            recipe_key = RecipeKey(
                blueprint_type_id=row.blueprint_type_id,
                activity_id=row.activity_id,
            )
            materials[recipe_key].append(
                ItemQuantity(
                    type_id=row.material_type_id,
                    quantity=row.quantity,
                )
            )

        recipes: list[IndustryRecipe] = []
        for recipe_key in sorted(headers):
            header = headers[recipe_key]
            try:
                activity = ActivityKind(header["activity_code"])
            except ValueError as exc:
                raise InvalidIndustryDataError(
                    f"Unsupported activity code: {header['activity_code']}"
                ) from exc
            recipes.append(
                IndustryRecipe(
                    key=recipe_key,
                    blueprint_name=header["blueprint_name"],
                    activity=activity,
                    time_seconds=header["time_seconds"],
                    max_production_limit=header["max_production_limit"],
                    products=tuple(products[recipe_key]),
                    materials=tuple(materials[recipe_key]),
                )
            )

        grouped_recipes: dict[int, list[IndustryRecipe]] = {
            type_id: [] for type_id in requested_ids
        }
        requested_id_set = set(requested_ids)
        for recipe in recipes:
            for product in recipe.products:
                if product.type_id in requested_id_set:
                    grouped_recipes[product.type_id].append(recipe)

        return {
            type_id: tuple(sorted(candidates, key=lambda recipe: recipe.key))
            for type_id, candidates in grouped_recipes.items()
        }

    def load_recipe_skill_requirements(
        self,
        recipe_keys: Collection[RecipeKey],
    ) -> dict[RecipeKey, tuple[SpecialistSkillRequirement, ...]]:
        requested_keys = tuple(sorted(set(recipe_keys)))
        result = {key: () for key in requested_keys}
        if not requested_keys:
            return result

        self._lock_sde_snapshot()
        rows = self._session.execute(
            select(
                IndustryActivitySkill.blueprint_type_id,
                IndustryActivitySkill.activity_id,
                IndustryActivitySkill.skill_type_id,
                IndustryActivitySkill.required_level,
            )
            .where(
                tuple_(
                    IndustryActivitySkill.blueprint_type_id,
                    IndustryActivitySkill.activity_id,
                ).in_(
                    tuple(
                        (key.blueprint_type_id, key.activity_id)
                        for key in requested_keys
                    )
                )
            )
            .order_by(
                IndustryActivitySkill.blueprint_type_id,
                IndustryActivitySkill.activity_id,
                IndustryActivitySkill.skill_type_id,
            )
        )
        grouped: dict[RecipeKey, list[SpecialistSkillRequirement]] = defaultdict(list)
        for row in rows:
            key = RecipeKey(row.blueprint_type_id, row.activity_id)
            grouped[key].append(
                SpecialistSkillRequirement(
                    type_id=row.skill_type_id,
                    level=row.required_level,
                )
            )
        return {
            key: tuple(grouped.get(key, ()))
            for key in requested_keys
        }
