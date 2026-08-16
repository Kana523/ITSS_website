"""add public market cache

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "esi_cache_states",
        sa.Column("resource_key", sa.String(length=128), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_compatibility_date", sa.Date(), nullable=False),
        sa.Column("matched_compatibility_date", sa.Date(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "row_count >= 0",
            name=op.f("ck_esi_cache_states_row_count_non_negative"),
        ),
        sa.PrimaryKeyConstraint(
            "resource_key",
            name=op.f("pk_esi_cache_states"),
        ),
    )
    op.create_table(
        "industry_system_cost_indices",
        sa.Column("solar_system_id", sa.Integer(), nullable=False),
        sa.Column("activity", sa.String(length=64), nullable=False),
        sa.Column("cost_index", sa.Numeric(precision=38, scale=20), nullable=False),
        sa.CheckConstraint(
            "solar_system_id > 0",
            name=op.f(
                "ck_industry_system_cost_indices_solar_system_id_positive"
            ),
        ),
        sa.CheckConstraint(
            "cost_index >= 0",
            name=op.f(
                "ck_industry_system_cost_indices_cost_index_non_negative"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "solar_system_id",
            "activity",
            name=op.f("pk_industry_system_cost_indices"),
        ),
    )
    op.create_table(
        "market_hub_prices",
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column("best_buy_price", sa.Numeric(precision=30, scale=2), nullable=True),
        sa.Column("best_buy_volume", sa.BigInteger(), nullable=True),
        sa.Column("best_sell_price", sa.Numeric(precision=30, scale=2), nullable=True),
        sa.Column("best_sell_volume", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "best_buy_price IS NULL OR best_buy_price > 0",
            name=op.f("ck_market_hub_prices_best_buy_price_positive"),
        ),
        sa.CheckConstraint(
            "best_buy_volume IS NULL OR best_buy_volume > 0",
            name=op.f("ck_market_hub_prices_best_buy_volume_positive"),
        ),
        sa.CheckConstraint(
            "best_sell_price IS NULL OR best_sell_price > 0",
            name=op.f("ck_market_hub_prices_best_sell_price_positive"),
        ),
        sa.CheckConstraint(
            "best_sell_volume IS NULL OR best_sell_volume > 0",
            name=op.f("ck_market_hub_prices_best_sell_volume_positive"),
        ),
        sa.CheckConstraint(
            "location_id > 0",
            name=op.f("ck_market_hub_prices_location_id_positive"),
        ),
        sa.CheckConstraint(
            "region_id > 0",
            name=op.f("ck_market_hub_prices_region_id_positive"),
        ),
        sa.CheckConstraint(
            "type_id > 0",
            name=op.f("ck_market_hub_prices_type_id_positive"),
        ),
        sa.PrimaryKeyConstraint(
            "region_id",
            "location_id",
            "type_id",
            name=op.f("pk_market_hub_prices"),
        ),
    )
    op.create_table(
        "market_order_page_cache",
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_compatibility_date", sa.Date(), nullable=False),
        sa.Column("matched_compatibility_date", sa.Date(), nullable=True),
        sa.Column(
            "page_quotes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "location_id > 0",
            name=op.f("ck_market_order_page_cache_location_id_positive"),
        ),
        sa.CheckConstraint(
            "page > 0",
            name=op.f("ck_market_order_page_cache_page_positive"),
        ),
        sa.CheckConstraint(
            "page_count > 0",
            name=op.f("ck_market_order_page_cache_page_count_positive"),
        ),
        sa.CheckConstraint(
            "region_id > 0",
            name=op.f("ck_market_order_page_cache_region_id_positive"),
        ),
        sa.PrimaryKeyConstraint(
            "region_id",
            "location_id",
            "page",
            name=op.f("pk_market_order_page_cache"),
        ),
    )
    op.create_table(
        "market_reference_prices",
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column(
            "adjusted_price",
            sa.Numeric(precision=38, scale=20),
            nullable=True,
        ),
        sa.Column(
            "average_price",
            sa.Numeric(precision=38, scale=20),
            nullable=True,
        ),
        sa.CheckConstraint(
            "adjusted_price IS NULL OR adjusted_price >= 0",
            name=op.f(
                "ck_market_reference_prices_adjusted_price_non_negative"
            ),
        ),
        sa.CheckConstraint(
            "average_price IS NULL OR average_price >= 0",
            name=op.f(
                "ck_market_reference_prices_average_price_non_negative"
            ),
        ),
        sa.CheckConstraint(
            "type_id > 0",
            name=op.f("ck_market_reference_prices_type_id_positive"),
        ),
        sa.PrimaryKeyConstraint(
            "type_id",
            name=op.f("pk_market_reference_prices"),
        ),
    )


def downgrade() -> None:
    op.drop_table("market_reference_prices")
    op.drop_table("market_order_page_cache")
    op.drop_table("market_hub_prices")
    op.drop_table("industry_system_cost_indices")
    op.drop_table("esi_cache_states")
