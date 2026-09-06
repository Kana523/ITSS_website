from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Connection

from app.sde.importer import import_sde
from app.sde.models import EveSolarSystem, SdeImport
from app.sde.source import DATASET_FILENAMES, SdeSource


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sde"


@pytest.mark.integration
def test_same_build_refresh_backfills_solar_systems_for_legacy_import(
    migrated_connection: Connection,
) -> None:
    first = import_sde(
        FIXTURE_DIR,
        connection=migrated_connection,
        batch_size=2,
    )
    legacy_counts = dict(first.row_counts)
    legacy_counts.pop("solar_systems")
    legacy_checksum = SdeSource(FIXTURE_DIR).calculate_checksum(
        tuple(
            dataset
            for dataset in DATASET_FILENAMES
            if dataset != "solar_systems"
        )
    )
    migrated_connection.execute(delete(EveSolarSystem))
    migrated_connection.execute(
        update(SdeImport)
        .where(SdeImport.id == first.import_id)
        .values(
            row_counts=legacy_counts,
            source_checksum=legacy_checksum,
        )
    )

    refreshed = import_sde(
        FIXTURE_DIR,
        connection=migrated_connection,
        batch_size=2,
    )

    assert refreshed.already_imported is True
    assert refreshed.row_counts["solar_systems"] == 3
    assert refreshed.source_checksum == first.source_checksum
    assert migrated_connection.scalar(
        select(func.count()).select_from(EveSolarSystem)
    ) == 3


@pytest.mark.integration
def test_same_build_backfills_security_after_schema_upgrade(migrated_connection: Connection) -> None:
    first = import_sde(FIXTURE_DIR, connection=migrated_connection)
    migrated_connection.execute(update(EveSolarSystem).values(security_status=None))
    refreshed = import_sde(FIXTURE_DIR, connection=migrated_connection)
    assert refreshed.already_imported is True
    assert refreshed.import_id == first.import_id
    assert migrated_connection.scalar(select(EveSolarSystem.security_status).where(
        EveSolarSystem.solar_system_id == 30000142,
    )) == 0.945913
