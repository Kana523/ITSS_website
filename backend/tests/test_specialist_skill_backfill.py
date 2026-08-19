import json
from pathlib import Path
from shutil import copytree

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Connection

from app.sde.importer import import_sde
from app.sde.models import IndustryActivitySkill, SdeImport


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"
SKILL_TYPE_ID = 3001
REQUIRED_LEVEL = 4


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )


def _source_with_specialist_skill(tmp_path: Path) -> Path:
    source = tmp_path / "legacy-specialist-sde"
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
    return source


@pytest.mark.integration
def test_same_build_refresh_backfills_skills_for_pre_skill_import(
    migrated_connection: Connection,
    tmp_path: Path,
) -> None:
    source = _source_with_specialist_skill(tmp_path)
    first = import_sde(
        source,
        connection=migrated_connection,
        batch_size=2,
    )
    assert first.row_counts["skills"] == 1

    legacy_counts = dict(first.row_counts)
    legacy_counts.pop("skills")
    migrated_connection.execute(delete(IndustryActivitySkill))
    migrated_connection.execute(
        update(SdeImport)
        .where(SdeImport.id == first.import_id)
        .values(row_counts=legacy_counts)
    )

    assert migrated_connection.scalar(
        select(IndustryActivitySkill.skill_type_id)
    ) is None

    refreshed = import_sde(
        source,
        connection=migrated_connection,
        batch_size=2,
    )

    assert refreshed.already_imported is True
    assert refreshed.import_id == first.import_id
    assert refreshed.row_counts["skills"] == 1
    restored = migrated_connection.execute(
        select(
            IndustryActivitySkill.blueprint_type_id,
            IndustryActivitySkill.activity_id,
            IndustryActivitySkill.skill_type_id,
            IndustryActivitySkill.required_level,
        )
    ).one()
    assert restored == (2002, 1, SKILL_TYPE_ID, REQUIRED_LEVEL)
