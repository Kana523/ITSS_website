import json
from collections.abc import Collection, Iterator
from pathlib import Path
from shutil import copytree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.api.dependencies import get_industry_application_service
from app.database.repositories.industry import SqlAlchemyIndustryRepository
from app.industry.application import IndustryApplicationService
from app.industry.models import (
    ActivityKind,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    RecipeKey,
)
from app.industry.service import IndustryPlanningService
from app.industry.specialist_skills import (
    MissingSpecialistSkillsError,
    SpecialistSkillRequirement,
)
from app.main import create_app
from app.sde.importer import import_sde


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"
RECIPE_KEY = RecipeKey(2001, 1)
SKILL_TYPE_ID = 3001
REQUIRED_LEVEL = 4


def _type(type_id: int, name: str) -> IndustryType:
    return IndustryType(
        type_id=type_id,
        name=name,
        published=True,
        group_id=10,
        group_name="Test Group",
        category_id=1,
        category_name="Test Category",
    )


TEST_RECIPE = IndustryRecipe(
    key=RECIPE_KEY,
    blueprint_name="Specialist Test Blueprint",
    activity=ActivityKind.MANUFACTURING,
    time_seconds=60,
    max_production_limit=100,
    products=(ItemQuantity(1001, 1),),
    materials=(ItemQuantity(1002, 2),),
)


class SpecialistSkillRepository:
    def __init__(self) -> None:
        self.types = {
            1001: _type(1001, "Specialist Test Product"),
            1002: _type(1002, "Raw Material"),
            2001: _type(2001, "Specialist Test Blueprint"),
        }
        self.skill_loads: list[tuple[RecipeKey, ...]] = []

    def latest_sde_build_number(self) -> int | None:
        return 9_000_001

    def search_types(
        self,
        query: str,
        *,
        published_only: bool = True,
        producible_only: bool = False,
        limit: int = 20,
    ) -> tuple[IndustryType, ...]:
        del published_only, producible_only
        return tuple(
            item
            for item in self.types.values()
            if query.casefold() in item.name.casefold()
        )[:limit]

    def load_types(
        self,
        type_ids: Collection[int],
    ) -> dict[int, IndustryType]:
        return {
            type_id: self.types[type_id]
            for type_id in type_ids
            if type_id in self.types
        }

    def load_recipes_for_products(
        self,
        product_type_ids: Collection[int],
    ) -> dict[int, tuple[IndustryRecipe, ...]]:
        return {
            type_id: (TEST_RECIPE,) if type_id == 1001 else ()
            for type_id in product_type_ids
        }

    def load_recipe_skill_requirements(
        self,
        recipe_keys: Collection[RecipeKey],
    ) -> dict[RecipeKey, tuple[SpecialistSkillRequirement, ...]]:
        keys = tuple(sorted(recipe_keys))
        self.skill_loads.append(keys)
        return {
            key: (
                (SpecialistSkillRequirement(SKILL_TYPE_ID, REQUIRED_LEVEL),)
                if key == RECIPE_KEY
                else ()
            )
            for key in keys
        }


def test_specialist_skill_validation_is_opt_in_and_exact() -> None:
    repository = SpecialistSkillRepository()
    service = IndustryPlanningService(repository)

    legacy_plan = service.create_plan((ItemQuantity(1001, 1),))
    assert legacy_plan.build_steps[0].product_type_id == 1001
    assert repository.skill_loads == []

    with pytest.raises(MissingSpecialistSkillsError) as error:
        service.create_plan(
            (ItemQuantity(1001, 1),),
            specialist_skill_levels={},
        )

    assert error.value.sde_build_number == 9_000_001
    assert error.value.missing == (
        (
            RECIPE_KEY,
            SpecialistSkillRequirement(SKILL_TYPE_ID, REQUIRED_LEVEL),
            0,
        ),
    )

    with pytest.raises(MissingSpecialistSkillsError) as low_level_error:
        service.create_plan(
            (ItemQuantity(1001, 1),),
            specialist_skill_levels={SKILL_TYPE_ID: REQUIRED_LEVEL - 1},
        )
    assert low_level_error.value.missing[0][2] == REQUIRED_LEVEL - 1

    qualified_plan = service.create_plan(
        (ItemQuantity(1001, 1),),
        specialist_skill_levels={SKILL_TYPE_ID: REQUIRED_LEVEL},
    )
    assert qualified_plan.build_steps[0].runs == 1


def _api_client() -> Iterator[TestClient]:
    application = create_app()
    service = IndustryApplicationService(SpecialistSkillRepository())
    application.dependency_overrides[get_industry_application_service] = (
        lambda: service
    )
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


def test_calculate_returns_structured_missing_specialist_skills_error() -> None:
    client_iterator = _api_client()
    client = next(client_iterator)
    try:
        legacy = client.post(
            "/api/industry/calculate",
            json={"demands": [{"type_id": 1001, "quantity": 1}]},
        )
        assert legacy.status_code == 200

        response = client.post(
            "/api/industry/calculate",
            json={
                "demands": [{"type_id": 1001, "quantity": 1}],
                "specialist_skills": [
                    {"type_id": SKILL_TYPE_ID, "level": 2}
                ],
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "missing_specialist_skills",
                "message": (
                    "Blueprint specialist skill requirements are not met: "
                    "2001:1: skill 3001 2/4"
                ),
                "details": {
                    "missing_skills": [
                        {
                            "recipe_key": {
                                "blueprint_type_id": 2001,
                                "activity_id": 1,
                            },
                            "skill_type_id": 3001,
                            "current_level": 2,
                            "required_level": 4,
                        }
                    ]
                },
            },
            "sde_build_number": 9_000_001,
        }

        qualified = client.post(
            "/api/industry/calculate",
            json={
                "demands": [{"type_id": 1001, "quantity": 1}],
                "specialist_skills": [
                    {"type_id": SKILL_TYPE_ID, "level": REQUIRED_LEVEL}
                ],
            },
        )
        assert qualified.status_code == 200
    finally:
        try:
            next(client_iterator)
        except StopIteration:
            pass


def test_specialist_skill_request_rejects_duplicates_and_invalid_levels() -> None:
    client_iterator = _api_client()
    client = next(client_iterator)
    try:
        duplicate = client.post(
            "/api/industry/calculate",
            json={
                "demands": [{"type_id": 1001, "quantity": 1}],
                "specialist_skills": [
                    {"type_id": SKILL_TYPE_ID, "level": 4},
                    {"type_id": SKILL_TYPE_ID, "level": 5},
                ],
            },
        )
        invalid = client.post(
            "/api/industry/calculate",
            json={
                "demands": [{"type_id": 1001, "quantity": 1}],
                "specialist_skills": [
                    {"type_id": SKILL_TYPE_ID, "level": 6}
                ],
            },
        )

        assert duplicate.status_code == 422
        assert duplicate.json()["error"]["code"] == "validation_error"
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"
    finally:
        try:
            next(client_iterator)
        except StopIteration:
            pass


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_sde_skill_requirement_survives_import_repository_and_planner(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    source = tmp_path / "specialist-skills-sde"
    copytree(FIXTURE_DIR, source)

    types_path = source / "types.jsonl"
    types = _read_jsonl(types_path)
    types.append(
        {
            "_key": SKILL_TYPE_ID,
            "groupID": 10,
            "name": {"en": "Advanced Test Construction"},
            "published": True,
        }
    )
    _write_jsonl(types_path, types)

    blueprints_path = source / "blueprints.jsonl"
    blueprints = _read_jsonl(blueprints_path)
    manufacturing = next(
        record for record in blueprints if record["_key"] == 2002
    )["activities"]["manufacturing"]
    manufacturing["skills"] = [
        {"typeID": SKILL_TYPE_ID, "level": REQUIRED_LEVEL}
    ]
    _write_jsonl(blueprints_path, blueprints)

    result = import_sde(
        source,
        connection=migrated_connection,
        batch_size=2,
    )
    assert result.row_counts["skills"] == 1

    with Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        repository = SqlAlchemyIndustryRepository(session)
        requirements = repository.load_recipe_skill_requirements(
            {RecipeKey(2001, 9), RecipeKey(2002, 1)}
        )
        assert requirements[RecipeKey(2001, 9)] == ()
        assert requirements[RecipeKey(2002, 1)] == (
            SpecialistSkillRequirement(SKILL_TYPE_ID, REQUIRED_LEVEL),
        )

        service = IndustryPlanningService(repository)
        with pytest.raises(MissingSpecialistSkillsError):
            service.create_plan(
                (ItemQuantity(1003, 1),),
                specialist_skill_levels={},
            )

        plan = service.create_plan(
            (ItemQuantity(1003, 1),),
            specialist_skill_levels={SKILL_TYPE_ID: REQUIRED_LEVEL},
        )
        assert [step.product_type_id for step in plan.build_steps] == [1002, 1003]
