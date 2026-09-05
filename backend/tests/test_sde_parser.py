import json
from pathlib import Path
from shutil import copytree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.sde.errors import SdeValidationError
from app.sde.parser import parse_sde
from app.sde.source import SdeSource


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"


def test_parser_normalizes_direct_industry_chain() -> None:
    dataset = parse_sde(SdeSource(FIXTURE_DIR))

    assert dataset.manifest.build_number == 9_000_001
    assert dataset.row_counts == {
        "categories": 2,
        "groups": 2,
        "types": 6,
        "solar_systems": 3,
        "activity_types": 2,
        "blueprints": 2,
        "activities": 2,
        "materials": 2,
        "products": 2,
        "skipped_unpublished_blueprints": 1,
        "skipped_blueprints_without_supported_activity": 0,
        "ignored_activities": 1,
    }
    assert dataset.activity_types == [
        {
            "activity_id": 1,
            "code": "manufacturing",
            "name": "Manufacturing",
            "description": "Manufacturing of things",
        },
        {
            "activity_id": 9,
            "code": "reaction",
            "name": "Reactions",
            "description": "Combining materials into advanced components",
        },
    ]
    assert dataset.solar_systems[0] == {
        "solar_system_id": 30000142,
        "name": "Jita",
    }
    assert dataset.materials[1] == {
        "blueprint_type_id": 2002,
        "activity_id": 1,
        "material_type_id": 1002,
        "quantity": 4,
    }
    assert dataset.products[0] == {
        "blueprint_type_id": 2001,
        "activity_id": 9,
        "product_type_id": 1002,
        "quantity": 2,
    }


def test_zip_and_directory_sources_parse_identically(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixture-sde.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for source_file in FIXTURE_DIR.iterdir():
            archive.write(source_file, source_file.name)

    directory_source = SdeSource(FIXTURE_DIR)
    zip_source = SdeSource(archive_path)

    assert zip_source.calculate_checksum() == directory_source.calculate_checksum()
    assert parse_sde(zip_source).row_counts == parse_sde(directory_source).row_counts


def test_parser_rejects_empty_core_dataset(tmp_path: Path) -> None:
    empty_source = tmp_path / "empty-sde"
    copytree(FIXTURE_DIR, empty_source)
    (empty_source / "categories.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(SdeValidationError, match="contains no categories"):
        parse_sde(SdeSource(empty_source))


def test_parser_rejects_source_without_supported_published_blueprints(
    tmp_path: Path,
) -> None:
    unsupported_source = tmp_path / "unsupported-sde"
    copytree(FIXTURE_DIR, unsupported_source)
    blueprint_path = unsupported_source / "blueprints.jsonl"
    records = [
        json.loads(line)
        for line in blueprint_path.read_text(encoding="utf-8").splitlines()
    ]
    unpublished_blueprint = next(record for record in records if record["_key"] == 2003)
    blueprint_path.write_text(
        json.dumps(unpublished_blueprint) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SdeValidationError,
        match="contains no published manufacturing or reaction blueprints",
    ):
        parse_sde(SdeSource(unsupported_source))


def test_parser_rejects_source_without_industry_materials(tmp_path: Path) -> None:
    material_free_source = tmp_path / "material-free-sde"
    copytree(FIXTURE_DIR, material_free_source)
    blueprint_path = material_free_source / "blueprints.jsonl"
    records = [
        json.loads(line)
        for line in blueprint_path.read_text(encoding="utf-8").splitlines()
    ]
    for record in records:
        if record["_key"] == 2001:
            record["activities"]["reaction"]["materials"] = []
        elif record["_key"] == 2002:
            record["activities"]["manufacturing"]["materials"] = []
    blueprint_path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records),
        encoding="utf-8",
    )

    with pytest.raises(
        SdeValidationError,
        match="contains no published manufacturing or reaction materials",
    ):
        parse_sde(SdeSource(material_free_source))


@pytest.mark.parametrize(
    ("old", "new", "error_match"),
    [
        ('"quantity": 3', '"quantity": 0', "quantity must be positive"),
        ('"typeID": 1001', '"typeID": 9999', "missing material type 9999"),
        (
            '[{"quantity": 3, "typeID": 1001}]',
            (
                '[{"quantity": 3, "typeID": 1001}, '
                '{"quantity": 1, "typeID": 1001}]'
            ),
            "repeats material type 1001",
        ),
    ],
)
def test_parser_rejects_invalid_relationships(
    tmp_path: Path,
    old: str,
    new: str,
    error_match: str,
) -> None:
    invalid_source = tmp_path / "invalid-sde"
    copytree(FIXTURE_DIR, invalid_source)
    blueprint_path = invalid_source / "blueprints.jsonl"
    blueprint_text = blueprint_path.read_text(encoding="utf-8")
    blueprint_path.write_text(blueprint_text.replace(old, new, 1), encoding="utf-8")

    with pytest.raises(SdeValidationError, match=error_match):
        parse_sde(SdeSource(invalid_source))
