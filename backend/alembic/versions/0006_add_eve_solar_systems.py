"""add EVE solar system names

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eve_solar_systems",
        sa.Column("solar_system_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("last_seen_import_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "solar_system_id > 0",
            name="solar_system_id_positive",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_import_id"],
            ["sde_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("solar_system_id"),
    )
    op.create_index(
        "ix_eve_solar_systems_name",
        "eve_solar_systems",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eve_solar_systems_name",
        table_name="eve_solar_systems",
    )
    op.drop_table("eve_solar_systems")
