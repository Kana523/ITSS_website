"""add market depth cache columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    empty_depth = sa.text("'[]'::jsonb")
    op.add_column(
        "market_hub_prices",
        sa.Column(
            "buy_levels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=empty_depth,
        ),
    )
    op.add_column(
        "market_hub_prices",
        sa.Column(
            "sell_levels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=empty_depth,
        ),
    )


def downgrade() -> None:
    op.drop_column("market_hub_prices", "sell_levels")
    op.drop_column("market_hub_prices", "buy_levels")
