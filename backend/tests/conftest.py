from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateSchema

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def migrated_connection() -> Iterator[Connection]:
    """Run migrations in an isolated transactional PostgreSQL schema."""
    from app.database.engine import engine

    schema_name = f"test_sde_{uuid4().hex}"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(CreateSchema(schema_name))
            connection.exec_driver_sql(
                f'SET LOCAL search_path TO "{schema_name}"'
            )

            alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")

            yield connection
        finally:
            transaction.rollback()
