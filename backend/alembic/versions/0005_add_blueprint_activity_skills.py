"""add blueprint activity skill requirements

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "industry_activity_skills",
        sa.Column("blueprint_type_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("skill_type_id", sa.Integer(), nullable=False),
        sa.Column("required_level", sa.Integer(), nullable=False),
        sa.Column("last_seen_import_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "required_level >= 1 AND required_level <= 5",
            name="required_level_valid",
        ),
        sa.ForeignKeyConstraint(
            ["blueprint_type_id", "activity_id"],
            [
                "industry_activities.blueprint_type_id",
                "industry_activities.activity_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_type_id"],
            ["eve_types.type_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_import_id"],
            ["sde_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "blueprint_type_id",
            "activity_id",
            "skill_type_id",
        ),
    )
    op.create_index(
        "ix_industry_activity_skills_skill_type_id",
        "industry_activity_skills",
        ["skill_type_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_industry_activity_skills_skill_type_id",
        table_name="industry_activity_skills",
    )
    op.drop_table("industry_activity_skills")
