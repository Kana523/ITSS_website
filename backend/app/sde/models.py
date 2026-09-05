from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SdeImport(Base):
    __tablename__ = "sde_imports"
    __table_args__ = (
        CheckConstraint("build_number > 0", name="build_number_positive"),
        CheckConstraint(
            "char_length(source_checksum) = 64",
            name="source_checksum_sha256_length",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    build_number: Mapped[int] = mapped_column(BigInteger, unique=True)
    release_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_checksum: Mapped[str] = mapped_column(String(64))
    row_counts: Mapped[dict[str, int]] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class EveCategory(Base):
    __tablename__ = "eve_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    published: Mapped[bool] = mapped_column(Boolean)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class EveGroup(Base):
    __tablename__ = "eve_groups"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("eve_categories.category_id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    published: Mapped[bool] = mapped_column(Boolean)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class EveType(Base):
    __tablename__ = "eve_types"

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("eve_groups.group_id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    published: Mapped[bool] = mapped_column(Boolean)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class EveSolarSystem(Base):
    __tablename__ = "eve_solar_systems"
    __table_args__ = (
        CheckConstraint(
            "solar_system_id > 0",
            name="solar_system_id_positive",
        ),
    )

    solar_system_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class IndustryActivityType(Base):
    __tablename__ = "industry_activity_types"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class Blueprint(Base):
    __tablename__ = "blueprints"
    __table_args__ = (
        CheckConstraint(
            "max_production_limit IS NULL OR max_production_limit > 0",
            name="max_production_limit_positive",
        ),
    )

    blueprint_type_id: Mapped[int] = mapped_column(
        ForeignKey("eve_types.type_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    max_production_limit: Mapped[int | None] = mapped_column(Integer)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class IndustryActivity(Base):
    __tablename__ = "industry_activities"
    __table_args__ = (
        CheckConstraint("time_seconds > 0", name="time_seconds_positive"),
    )

    blueprint_type_id: Mapped[int] = mapped_column(
        ForeignKey("blueprints.blueprint_type_id", ondelete="CASCADE"),
        primary_key=True,
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("industry_activity_types.activity_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    time_seconds: Mapped[int] = mapped_column(Integer)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class IndustryActivityMaterial(Base):
    __tablename__ = "industry_activity_materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["blueprint_type_id", "activity_id"],
            [
                "industry_activities.blueprint_type_id",
                "industry_activities.activity_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index(
            "ix_industry_activity_materials_material_type_id",
            "material_type_id",
        ),
    )

    blueprint_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_type_id: Mapped[int] = mapped_column(
        ForeignKey("eve_types.type_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quantity: Mapped[int] = mapped_column(BigInteger)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class IndustryActivityProduct(Base):
    __tablename__ = "industry_activity_products"
    __table_args__ = (
        ForeignKeyConstraint(
            ["blueprint_type_id", "activity_id"],
            [
                "industry_activities.blueprint_type_id",
                "industry_activities.activity_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index(
            "ix_industry_activity_products_product_type_id",
            "product_type_id",
        ),
    )

    blueprint_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_type_id: Mapped[int] = mapped_column(
        ForeignKey("eve_types.type_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quantity: Mapped[int] = mapped_column(BigInteger)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )


class IndustryActivitySkill(Base):
    __tablename__ = "industry_activity_skills"
    __table_args__ = (
        ForeignKeyConstraint(
            ["blueprint_type_id", "activity_id"],
            [
                "industry_activities.blueprint_type_id",
                "industry_activities.activity_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "required_level >= 1 AND required_level <= 5",
            name="required_level_valid",
        ),
        Index(
            "ix_industry_activity_skills_skill_type_id",
            "skill_type_id",
        ),
    )

    blueprint_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_type_id: Mapped[int] = mapped_column(
        ForeignKey("eve_types.type_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    required_level: Mapped[int] = mapped_column(Integer)
    last_seen_import_id: Mapped[int] = mapped_column(
        ForeignKey("sde_imports.id", ondelete="RESTRICT")
    )
