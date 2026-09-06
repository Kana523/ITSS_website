"""Store system security for facility bonuses.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unknown until the existing SDE archive is re-imported; never assume highsec.
    op.add_column("eve_solar_systems", sa.Column("security_status", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("eve_solar_systems", "security_status")
