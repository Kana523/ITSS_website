import json
from pathlib import Path
from shutil import copytree

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.sde.errors import SdeImportConflictError, SdeSourceError
from app.sde.importer import import_sde
from app.sde.models import (
    Blueprint,
    EveCategory,
    EveGroup,
    EveType,
    IndustryActivity,
    IndustryActivityMaterial,
    IndustryActivityProduct,
    SdeImport,
)
from app.sde.source import SdeSource


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )


def test_importer_rejects_source_that_changes_while_being_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checksums = iter(("a" * 64, "b" * 64))
    monkeypatch.setattr(
        SdeSource,
        "calculate_checksum",
        lambda self: next(checksums),
    )

    with pytest.raises(SdeSourceError, match="changed while it was being read"):
        import_sde(FIXTURE_DIR)


@pytest.mark.integration
def test_importer_loads_direct_chain_and_is_idempotent(
    migrated_connection: Connection,
) -> None:
    first_result = import_sde(
        FIXTURE_DIR,
        connection=migrated_connection,
        batch_size=2,
    )

    assert first_result.already_imported is False
    assert first_result.row_counts["blueprints"] == 2

    final_material = migrated_connection.execute(
        select(EveType.name, IndustryActivityMaterial.quantity)
        .join(
            IndustryActivityMaterial,
            EveType.type_id == IndustryActivityMaterial.material_type_id,
        )
        .where(IndustryActivityMaterial.blueprint_type_id == 2002)
    ).one()
    assert final_material == ("Reacted Component", 4)

    component_product = migrated_connection.execute(
        select(
            IndustryActivityProduct.blueprint_type_id,
            IndustryActivityProduct.quantity,
        ).where(IndustryActivityProduct.product_type_id == 1002)
    ).one()
    assert component_product == (2001, 2)

    second_result = import_sde(
        FIXTURE_DIR,
        connection=migrated_connection,
        batch_size=2,
    )
    assert second_result.already_imported is True
    assert second_result.import_id == first_result.import_id
    assert migrated_connection.scalar(select(func.count()).select_from(SdeImport)) == 1


@pytest.mark.integration
def test_conflicting_repeat_keeps_existing_snapshot(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    import_sde(FIXTURE_DIR, connection=migrated_connection, batch_size=2)
    conflicting_source = tmp_path / "conflicting-sde"
    copytree(FIXTURE_DIR, conflicting_source)
    categories_path = conflicting_source / "categories.jsonl"
    categories_path.write_text(
        categories_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SdeImportConflictError, match="different source content"):
        import_sde(
            conflicting_source,
            connection=migrated_connection,
            batch_size=2,
        )

    assert migrated_connection.scalar(select(func.count()).select_from(SdeImport)) == 1
    assert migrated_connection.scalar(select(func.count()).select_from(EveType)) == 6


@pytest.mark.integration
def test_large_deletion_guard_detects_equal_size_key_replacement(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    import_sde(FIXTURE_DIR, connection=migrated_connection, batch_size=2)
    replacement_source = tmp_path / "replacement-sde"
    copytree(FIXTURE_DIR, replacement_source)

    manifest_path = replacement_source / "_sde.jsonl"
    manifest = _read_jsonl(manifest_path)[0]
    manifest["buildNumber"] = 9_000_002
    _write_jsonl(manifest_path, [manifest])

    types_path = replacement_source / "types.jsonl"
    types = _read_jsonl(types_path)
    next(record for record in types if record["_key"] == 1001)["_key"] = 1010
    _write_jsonl(types_path, types)

    blueprints_path = replacement_source / "blueprints.jsonl"
    blueprints = _read_jsonl(blueprints_path)
    next(record for record in blueprints if record["_key"] == 2001)["activities"][
        "reaction"
    ]["materials"][0]["typeID"] = 1010
    _write_jsonl(blueprints_path, blueprints)

    with pytest.raises(SdeImportConflictError, match="unusually large amount"):
        import_sde(replacement_source, connection=migrated_connection, batch_size=2)

    assert migrated_connection.scalar(select(func.count()).select_from(SdeImport)) == 1
    assert migrated_connection.scalar(
        select(EveType.type_id).where(EveType.type_id == 1001)
    ) == 1001


@pytest.mark.integration
def test_new_build_requires_confirmation_for_large_deletions_and_syncs_atomically(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    initial_source = tmp_path / "initial-sde"
    copytree(FIXTURE_DIR, initial_source)

    categories_path = initial_source / "categories.jsonl"
    groups_path = initial_source / "groups.jsonl"
    types_path = initial_source / "types.jsonl"
    _write_jsonl(
        categories_path,
        _read_jsonl(categories_path)
        + [{"_key": 3, "name": {"en": "Retired"}, "published": False}],
    )
    _write_jsonl(
        groups_path,
        _read_jsonl(groups_path)
        + [
            {
                "_key": 30,
                "categoryID": 3,
                "name": {"en": "Retired"},
                "published": False,
            }
        ],
    )
    _write_jsonl(
        types_path,
        _read_jsonl(types_path)
        + [
            {
                "_key": 3001,
                "groupID": 30,
                "name": {"en": "Retired Type"},
                "published": False,
            }
        ],
    )
    import_sde(initial_source, connection=migrated_connection, batch_size=2)

    updated_source = tmp_path / "updated-sde"
    copytree(initial_source, updated_source)

    manifest_path = updated_source / "_sde.jsonl"
    manifest = _read_jsonl(manifest_path)[0]
    manifest["buildNumber"] = 9_000_002
    _write_jsonl(manifest_path, [manifest])

    categories_path = updated_source / "categories.jsonl"
    _write_jsonl(
        categories_path,
        [record for record in _read_jsonl(categories_path) if record["_key"] != 3],
    )
    groups_path = updated_source / "groups.jsonl"
    _write_jsonl(
        groups_path,
        [record for record in _read_jsonl(groups_path) if record["_key"] != 30],
    )
    types_path = updated_source / "types.jsonl"
    types = [
        record
        for record in _read_jsonl(types_path)
        if record["_key"] not in {2001, 3001}
    ]
    next(record for record in types if record["_key"] == 1002)["name"]["en"] = (
        "Updated Component"
    )
    _write_jsonl(types_path, types)

    blueprints_path = updated_source / "blueprints.jsonl"
    blueprints = [
        record
        for record in _read_jsonl(blueprints_path)
        if record["_key"] != 2001
    ]
    next(record for record in blueprints if record["_key"] == 2002)["activities"][
        "manufacturing"
    ]["materials"][0]["quantity"] = 5
    _write_jsonl(blueprints_path, blueprints)

    with pytest.raises(SdeImportConflictError, match="unusually large amount"):
        import_sde(updated_source, connection=migrated_connection, batch_size=2)

    assert migrated_connection.scalar(select(func.count()).select_from(SdeImport)) == 1
    assert migrated_connection.scalar(
        select(Blueprint.blueprint_type_id).where(Blueprint.blueprint_type_id == 2001)
    ) == 2001

    result = import_sde(
        updated_source,
        connection=migrated_connection,
        batch_size=2,
        allow_large_deletions=True,
    )
    assert result.build_number == 9_000_002
    assert result.already_imported is False
    assert migrated_connection.scalar(select(func.count()).select_from(SdeImport)) == 2
    assert migrated_connection.scalar(select(func.count()).select_from(EveCategory)) == 2
    assert migrated_connection.scalar(select(func.count()).select_from(EveGroup)) == 2
    assert migrated_connection.scalar(select(func.count()).select_from(EveType)) == 5
    assert migrated_connection.scalar(select(func.count()).select_from(Blueprint)) == 1
    assert migrated_connection.scalar(
        select(func.count()).select_from(IndustryActivity)
    ) == 1
    assert migrated_connection.scalar(
        select(func.count()).select_from(IndustryActivityMaterial)
    ) == 1
    assert migrated_connection.scalar(
        select(func.count()).select_from(IndustryActivityProduct)
    ) == 1
    assert migrated_connection.scalar(
        select(Blueprint.blueprint_type_id).where(Blueprint.blueprint_type_id == 2001)
    ) is None
    assert migrated_connection.scalar(
        select(EveType.type_id).where(EveType.type_id == 2001)
    ) is None
    assert migrated_connection.scalar(
        select(EveType.type_id).where(EveType.type_id == 3001)
    ) is None
    assert migrated_connection.scalar(
        select(EveType.name).where(EveType.type_id == 1002)
    ) == "Updated Component"
    assert migrated_connection.scalar(
        select(IndustryActivityMaterial.quantity).where(
            IndustryActivityMaterial.blueprint_type_id == 2002
        )
    ) == 5

    with pytest.raises(SdeImportConflictError, match="historical"):
        import_sde(initial_source, connection=migrated_connection, batch_size=2)
