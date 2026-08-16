from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Connection

from app.database.engine import engine
from app.sde.constants import SDE_IMPORT_ADVISORY_LOCK_ID
from app.sde.errors import SdeImportConflictError, SdeSourceError
from app.sde.models import (
    Blueprint,
    EveCategory,
    EveGroup,
    EveType,
    IndustryActivity,
    IndustryActivityMaterial,
    IndustryActivityProduct,
    IndustryActivitySkill,
    IndustryActivityType,
    SdeImport,
)
from app.sde.parser import ParsedSde, parse_sde
from app.sde.skill_parser import SkillRow, parse_blueprint_skill_rows
from app.sde.source import SdeSource


MAX_AUTOMATIC_ROW_DROP_PERCENT = 5
PROTECTED_DATASETS = (
    ("categories", EveCategory, ("category_id",)),
    ("groups", EveGroup, ("group_id",)),
    ("types", EveType, ("type_id",)),
    ("activity_types", IndustryActivityType, ("activity_id",)),
    ("blueprints", Blueprint, ("blueprint_type_id",)),
    ("activities", IndustryActivity, ("blueprint_type_id", "activity_id")),
    (
        "materials",
        IndustryActivityMaterial,
        ("blueprint_type_id", "activity_id", "material_type_id"),
    ),
    (
        "products",
        IndustryActivityProduct,
        ("blueprint_type_id", "activity_id", "product_type_id"),
    ),
)


@dataclass(frozen=True, slots=True)
class SdeImportResult:
    import_id: int
    build_number: int
    source_checksum: str
    row_counts: dict[str, int]
    already_imported: bool


def _batches(
    rows: Iterable[Mapping[str, Any]],
    batch_size: int,
    import_id: int,
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append({**row, "last_seen_import_id": import_id})
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _upsert_rows(
    connection: Connection,
    model,
    rows: Iterable[Mapping[str, Any]],
    *,
    conflict_columns: tuple[str, ...],
    update_columns: tuple[str, ...],
    batch_size: int,
    import_id: int,
) -> None:
    table = model.__table__
    insert_statement = postgresql_insert(table)
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[table.c[column] for column in conflict_columns],
        set_={
            column: getattr(insert_statement.excluded, column)
            for column in update_columns
        },
    )
    for batch in _batches(rows, batch_size, import_id):
        connection.execute(upsert_statement, batch)


def _find_large_deletions(
    connection: Connection,
    dataset: ParsedSde,
) -> list[str]:
    large_deletions: list[str] = []
    for dataset_name, model, key_columns in PROTECTED_DATASETS:
        table = model.__table__
        existing_keys = {
            tuple(row)
            for row in connection.execute(
                select(*(table.c[column] for column in key_columns))
            ).tuples()
        }
        if not existing_keys:
            continue

        incoming_rows = getattr(dataset, dataset_name)
        incoming_keys = {
            tuple(row[column] for column in key_columns) for row in incoming_rows
        }
        deleted_count = len(existing_keys - incoming_keys)
        if (
            deleted_count * 100
            > len(existing_keys) * MAX_AUTOMATIC_ROW_DROP_PERCENT
        ):
            deletion_percent = deleted_count * 100 / len(existing_keys)
            large_deletions.append(
                f"{dataset_name}: {deleted_count} of {len(existing_keys)} current "
                f"rows ({deletion_percent:.1f}%)"
            )

    return large_deletions


def _synchronize_sde(
    connection: Connection,
    dataset: ParsedSde,
    skill_rows: list[SkillRow],
    source_checksum: str,
    batch_size: int,
    allow_large_deletions: bool,
) -> SdeImportResult:
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": SDE_IMPORT_ADVISORY_LOCK_ID},
    )
    row_counts = {**dataset.row_counts, "skills": len(skill_rows)}

    latest_import = connection.execute(
        select(
            SdeImport.id,
            SdeImport.build_number,
            SdeImport.source_checksum,
            SdeImport.row_counts,
        )
        .order_by(SdeImport.id.desc())
        .limit(1)
    ).mappings().one_or_none()

    existing_import = connection.execute(
        select(
            SdeImport.id,
            SdeImport.build_number,
            SdeImport.source_checksum,
            SdeImport.row_counts,
        ).where(SdeImport.build_number == dataset.manifest.build_number)
    ).mappings().one_or_none()

    if existing_import is not None:
        if existing_import["source_checksum"] != source_checksum:
            raise SdeImportConflictError(
                f"SDE build {dataset.manifest.build_number} was already imported "
                "from different source content"
            )
        if latest_import is None or existing_import["id"] != latest_import["id"]:
            raise SdeImportConflictError(
                f"SDE build {dataset.manifest.build_number} is historical and "
                "cannot replace the current build"
            )
        return SdeImportResult(
            import_id=existing_import["id"],
            build_number=existing_import["build_number"],
            source_checksum=existing_import["source_checksum"],
            row_counts=dict(existing_import["row_counts"]),
            already_imported=True,
        )

    if (
        latest_import is not None
        and dataset.manifest.build_number < latest_import["build_number"]
    ):
        raise SdeImportConflictError(
            f"SDE build {dataset.manifest.build_number} is older than current "
            f"build {latest_import['build_number']}"
        )

    if latest_import is not None and not allow_large_deletions:
        large_deletions = _find_large_deletions(connection, dataset)
        if large_deletions:
            raise SdeImportConflictError(
                "SDE update would remove an unusually large amount of data: "
                + ", ".join(large_deletions)
                + ". Verify the source, then rerun with --allow-large-deletions."
            )

    import_id = connection.execute(
        insert(SdeImport)
        .values(
            build_number=dataset.manifest.build_number,
            release_date=dataset.manifest.release_date,
            source_checksum=source_checksum,
            row_counts=row_counts,
        )
        .returning(SdeImport.id)
    ).scalar_one()

    _upsert_rows(
        connection,
        EveCategory,
        dataset.categories,
        conflict_columns=("category_id",),
        update_columns=("name", "published", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        EveGroup,
        dataset.groups,
        conflict_columns=("group_id",),
        update_columns=(
            "category_id",
            "name",
            "published",
            "last_seen_import_id",
        ),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        EveType,
        dataset.types,
        conflict_columns=("type_id",),
        update_columns=("group_id", "name", "published", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        IndustryActivityType,
        dataset.activity_types,
        conflict_columns=("activity_id",),
        update_columns=(
            "code",
            "name",
            "description",
            "last_seen_import_id",
        ),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        Blueprint,
        dataset.blueprints,
        conflict_columns=("blueprint_type_id",),
        update_columns=("max_production_limit", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        IndustryActivity,
        dataset.activities,
        conflict_columns=("blueprint_type_id", "activity_id"),
        update_columns=("time_seconds", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        IndustryActivityMaterial,
        dataset.materials,
        conflict_columns=(
            "blueprint_type_id",
            "activity_id",
            "material_type_id",
        ),
        update_columns=("quantity", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        IndustryActivityProduct,
        dataset.products,
        conflict_columns=(
            "blueprint_type_id",
            "activity_id",
            "product_type_id",
        ),
        update_columns=("quantity", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )
    _upsert_rows(
        connection,
        IndustryActivitySkill,
        skill_rows,
        conflict_columns=(
            "blueprint_type_id",
            "activity_id",
            "skill_type_id",
        ),
        update_columns=("required_level", "last_seen_import_id"),
        batch_size=batch_size,
        import_id=import_id,
    )

    for model in (
        IndustryActivitySkill,
        IndustryActivityProduct,
        IndustryActivityMaterial,
        IndustryActivity,
        Blueprint,
        IndustryActivityType,
        EveType,
        EveGroup,
        EveCategory,
    ):
        connection.execute(
            delete(model).where(model.last_seen_import_id != import_id)
        )

    return SdeImportResult(
        import_id=import_id,
        build_number=dataset.manifest.build_number,
        source_checksum=source_checksum,
        row_counts=row_counts,
        already_imported=False,
    )


def import_sde(
    source_path: Path | str,
    *,
    batch_size: int = 2_000,
    allow_large_deletions: bool = False,
    connection: Connection | None = None,
) -> SdeImportResult:
    """Parse, validate, and atomically synchronize an SDE snapshot."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    source = SdeSource(source_path)
    source_checksum = source.calculate_checksum()
    dataset = parse_sde(source)
    skill_rows = parse_blueprint_skill_rows(
        source,
        known_type_ids={row["type_id"] for row in dataset.types},
    )
    if source.calculate_checksum() != source_checksum:
        raise SdeSourceError("SDE source changed while it was being read")

    if connection is not None:
        if not connection.in_transaction():
            raise RuntimeError("A supplied connection must have an active transaction")
        return _synchronize_sde(
            connection,
            dataset,
            skill_rows,
            source_checksum,
            batch_size,
            allow_large_deletions,
        )

    with engine.begin() as managed_connection:
        return _synchronize_sde(
            managed_connection,
            dataset,
            skill_rows,
            source_checksum,
            batch_size,
            allow_large_deletions,
        )
