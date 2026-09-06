import json
from pathlib import Path
from shutil import copytree

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.database.repositories.industry import SqlAlchemyIndustryRepository
from app.industry.models import (
    ActivityKind,
    BuildChoice,
    BuildDecision,
    ItemQuantity,
    PurchaseReason,
)
from app.industry.service import IndustryPlanningService
from app.sde.importer import import_sde


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_repository_loads_types_and_recipes(
    migrated_connection: Connection,
) -> None:
    import_sde(FIXTURE_DIR, connection=migrated_connection, batch_size=2)

    with Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        repository = SqlAlchemyIndustryRepository(session)

        assert repository.latest_sde_build_number() == 9_000_001
        loaded_types = repository.load_types({1001, 1003, 9999})
        assert set(loaded_types) == {1001, 1003}
        assert loaded_types[1003].name == "Final Product"
        assert loaded_types[1003].group_name == "Test Materials"

        search_results = repository.search_types(
            "Final Product",
            producible_only=True,
        )
        assert search_results[0].type_id == 1003
        assert repository.search_types("1003")[0].type_id == 1003
        assert repository.search_types("%") == ()
        assert repository.search_types("_") == ()
        assert repository.search_types("\\") == ()
        with pytest.raises(ValueError, match="255"):
            repository.search_types("1" * 256)
        with pytest.raises(ValueError, match="limit"):
            repository.search_types("Final", limit=True)

        system_results = repository.search_solar_systems("Jita")
        assert system_results[0].solar_system_id == 30_000_142
        assert system_results[0].security_status == 0.945913
        assert system_results[0].security_space == "highsec"
        assert repository.search_solar_systems("31000005")[0].security_space == "wormhole"
        for activity in (ActivityKind.MANUFACTURING, ActivityKind.REACTION):
            groups = repository.rig_scope_groups(activity)
            assert [(group.group_id, group.category_id) for group in groups] == [(10, 1)]
        assert repository.search_solar_systems("30002665")[0].name == "New Caldari"
        assert repository.search_solar_systems("%") == ()

        recipes = repository.load_recipes_for_products({1001, 1002, 1003})
        assert recipes[1001] == ()
        assert recipes[1002][0].key.blueprint_type_id == 2001
        assert recipes[1002][0].products == (ItemQuantity(1002, 2),)
        assert recipes[1002][0].materials == (ItemQuantity(1001, 3),)
        assert recipes[1003][0].key.blueprint_type_id == 2002
        assert recipes[1003][0].materials == (ItemQuantity(1002, 4),)


@pytest.mark.integration
def test_planning_service_resolves_fixture_chain_and_buy_override(
    migrated_connection: Connection,
) -> None:
    import_sde(FIXTURE_DIR, connection=migrated_connection, batch_size=2)

    with Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        service = IndustryPlanningService(SqlAlchemyIndustryRepository(session))
        plan = service.create_plan((ItemQuantity(1003, 3),))

        assert plan.sde_build_number == 9_000_001
        assert [step.product_type_id for step in plan.build_steps] == [1002, 1003]
        reaction_step, manufacturing_step = plan.build_steps
        assert reaction_step.required_quantity == 12
        assert reaction_step.runs == 6
        assert manufacturing_step.runs == 3
        assert [(item.type_id, item.quantity) for item in plan.purchases] == [
            (1001, 18)
        ]

        buy_plan = service.create_plan(
            (ItemQuantity(1003, 3),),
            choices={1002: BuildChoice(BuildDecision.BUY)},
        )
        assert [step.product_type_id for step in buy_plan.build_steps] == [1003]
        assert buy_plan.purchases[0].type_id == 1002
        assert buy_plan.purchases[0].quantity == 12
        assert buy_plan.purchases[0].reason == PurchaseReason.BUY_OVERRIDE


@pytest.mark.integration
def test_repository_preserves_recipe_without_materials(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    source = tmp_path / "material-free-recipe-sde"
    copytree(FIXTURE_DIR, source)
    blueprint_path = source / "blueprints.jsonl"
    blueprints = _read_jsonl(blueprint_path)
    next(record for record in blueprints if record["_key"] == 2001)["activities"][
        "reaction"
    ]["materials"] = []
    _write_jsonl(blueprint_path, blueprints)
    import_sde(source, connection=migrated_connection, batch_size=2)

    with Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        repository = SqlAlchemyIndustryRepository(session)
        recipe = repository.load_recipes_for_products({1002})[1002][0]

    assert recipe.materials == ()
    assert recipe.products == (ItemQuantity(1002, 2),)


@pytest.mark.integration
def test_repository_preserves_multiple_recipes_and_all_products(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    source = tmp_path / "multi-recipe-sde"
    copytree(FIXTURE_DIR, source)

    types_path = source / "types.jsonl"
    types = _read_jsonl(types_path)
    next(record for record in types if record["_key"] == 2003)["published"] = True
    _write_jsonl(types_path, types)

    blueprints_path = source / "blueprints.jsonl"
    blueprints = _read_jsonl(blueprints_path)
    extra_blueprint = next(record for record in blueprints if record["_key"] == 2003)
    extra_blueprint["activities"] = {
        "manufacturing": {
            "materials": [{"quantity": 1, "typeID": 1001}],
            "products": [
                {"quantity": 1, "typeID": 1002},
                {"quantity": 2, "typeID": 1003},
            ],
            "time": 30,
        }
    }
    _write_jsonl(blueprints_path, blueprints)
    import_sde(source, connection=migrated_connection, batch_size=2)

    with Session(
        bind=migrated_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        repository = SqlAlchemyIndustryRepository(session)
        recipes = repository.load_recipes_for_products({1002, 1003})

    assert [recipe.key.blueprint_type_id for recipe in recipes[1002]] == [2001, 2003]
    assert [recipe.key.blueprint_type_id for recipe in recipes[1003]] == [2002, 2003]
    coproduct_recipe = next(
        recipe for recipe in recipes[1003] if recipe.key.blueprint_type_id == 2003
    )
    assert coproduct_recipe.products == (
        ItemQuantity(1002, 1),
        ItemQuantity(1003, 2),
    )
