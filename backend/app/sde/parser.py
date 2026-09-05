import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from app.sde.errors import SdeValidationError
from app.sde.source import DATASET_FILENAMES, SdeSource


KNOWN_ACTIVITY_CODES = frozenset(
    {
        "copying",
        "invention",
        "manufacturing",
        "reaction",
        "research_material",
        "research_time",
    }
)
SUPPORTED_ACTIVITY_IDS = {
    "manufacturing": 1,
    "reaction": 9,
}


class CategoryRow(TypedDict):
    category_id: int
    name: str
    published: bool


class GroupRow(TypedDict):
    group_id: int
    category_id: int
    name: str
    published: bool


class TypeRow(TypedDict):
    type_id: int
    group_id: int
    name: str
    published: bool


class SolarSystemRow(TypedDict):
    solar_system_id: int
    name: str


class ActivityTypeRow(TypedDict):
    activity_id: int
    code: str
    name: str
    description: str | None


class BlueprintRow(TypedDict):
    blueprint_type_id: int
    max_production_limit: int | None


class ActivityRow(TypedDict):
    blueprint_type_id: int
    activity_id: int
    time_seconds: int


class MaterialRow(TypedDict):
    blueprint_type_id: int
    activity_id: int
    material_type_id: int
    quantity: int


class ProductRow(TypedDict):
    blueprint_type_id: int
    activity_id: int
    product_type_id: int
    quantity: int


@dataclass(frozen=True, slots=True)
class SdeManifest:
    build_number: int
    release_date: datetime


@dataclass(frozen=True, slots=True)
class ParsedSde:
    manifest: SdeManifest
    categories: list[CategoryRow]
    groups: list[GroupRow]
    types: list[TypeRow]
    solar_systems: list[SolarSystemRow]
    activity_types: list[ActivityTypeRow]
    blueprints: list[BlueprintRow]
    activities: list[ActivityRow]
    materials: list[MaterialRow]
    products: list[ProductRow]
    skipped_unpublished_blueprints: int
    skipped_blueprints_without_supported_activity: int
    ignored_activities: int

    @property
    def row_counts(self) -> dict[str, int]:
        return {
            "categories": len(self.categories),
            "groups": len(self.groups),
            "types": len(self.types),
            "solar_systems": len(self.solar_systems),
            "activity_types": len(self.activity_types),
            "blueprints": len(self.blueprints),
            "activities": len(self.activities),
            "materials": len(self.materials),
            "products": len(self.products),
            "skipped_unpublished_blueprints": (
                self.skipped_unpublished_blueprints
            ),
            "skipped_blueprints_without_supported_activity": (
                self.skipped_blueprints_without_supported_activity
            ),
            "ignored_activities": self.ignored_activities,
        }


def _iter_records(source: SdeSource, dataset: str) -> Iterator[tuple[int, dict]]:
    filename = DATASET_FILENAMES[dataset]
    with source.open_text(dataset) as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SdeValidationError(
                    f"{filename} line {line_number} is invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(record, dict):
                raise SdeValidationError(
                    f"{filename} line {line_number} must be an object"
                )
            yield line_number, record


def _required_int(
    record: Mapping[str, Any],
    field: str,
    context: str,
    *,
    positive: bool = False,
) -> int:
    value = record.get(field)
    if type(value) is not int:
        raise SdeValidationError(f"{context}.{field} must be an integer")
    if positive and value <= 0:
        raise SdeValidationError(f"{context}.{field} must be positive")
    return value


def _required_bool(record: Mapping[str, Any], field: str, context: str) -> bool:
    value = record.get(field)
    if type(value) is not bool:
        raise SdeValidationError(f"{context}.{field} must be a boolean")
    return value


def _english_name(record: Mapping[str, Any], context: str) -> str:
    names = record.get("name")
    if not isinstance(names, Mapping):
        raise SdeValidationError(f"{context}.name must be a localized object")
    name = names.get("en")
    if not isinstance(name, str) or not name.strip():
        raise SdeValidationError(f"{context}.name.en must be a non-empty string")
    if len(name) > 255:
        raise SdeValidationError(f"{context}.name.en exceeds 255 characters")
    return name


def _optional_positive_int(
    record: Mapping[str, Any], field: str, context: str
) -> int | None:
    value = record.get(field)
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise SdeValidationError(f"{context}.{field} must be positive or null")
    return value


def _parse_manifest(source: SdeSource) -> SdeManifest:
    records = list(_iter_records(source, "manifest"))
    if len(records) != 1:
        raise SdeValidationError("_sde.jsonl must contain exactly one record")

    line_number, record = records[0]
    context = f"manifest line {line_number}"
    if record.get("_key") != "sde":
        raise SdeValidationError(f"{context}._key must be 'sde'")
    build_number = _required_int(record, "buildNumber", context, positive=True)
    release_date_value = record.get("releaseDate")
    if not isinstance(release_date_value, str):
        raise SdeValidationError(f"{context}.releaseDate must be a string")
    try:
        release_date = datetime.fromisoformat(
            release_date_value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise SdeValidationError(
            f"{context}.releaseDate must be an ISO-8601 timestamp"
        ) from exc
    if release_date.tzinfo is None:
        raise SdeValidationError(f"{context}.releaseDate must include a timezone")
    return SdeManifest(build_number=build_number, release_date=release_date)


def _parse_categories(source: SdeSource) -> list[CategoryRow]:
    rows: list[CategoryRow] = []
    seen: set[int] = set()
    for line_number, record in _iter_records(source, "categories"):
        context = f"categories line {line_number}"
        category_id = _required_int(record, "_key", context)
        if category_id in seen:
            raise SdeValidationError(f"Duplicate category ID {category_id}")
        seen.add(category_id)
        rows.append(
            {
                "category_id": category_id,
                "name": _english_name(record, context),
                "published": _required_bool(record, "published", context),
            }
        )
    return rows


def _parse_groups(
    source: SdeSource, category_ids: set[int]
) -> list[GroupRow]:
    rows: list[GroupRow] = []
    seen: set[int] = set()
    for line_number, record in _iter_records(source, "groups"):
        context = f"groups line {line_number}"
        group_id = _required_int(record, "_key", context)
        if group_id in seen:
            raise SdeValidationError(f"Duplicate group ID {group_id}")
        seen.add(group_id)
        category_id = _required_int(record, "categoryID", context)
        if category_id not in category_ids:
            raise SdeValidationError(
                f"Group {group_id} references missing category {category_id}"
            )
        rows.append(
            {
                "group_id": group_id,
                "category_id": category_id,
                "name": _english_name(record, context),
                "published": _required_bool(record, "published", context),
            }
        )
    return rows


def _parse_types(source: SdeSource, group_ids: set[int]) -> list[TypeRow]:
    rows: list[TypeRow] = []
    seen: set[int] = set()
    for line_number, record in _iter_records(source, "types"):
        context = f"types line {line_number}"
        type_id = _required_int(record, "_key", context)
        if type_id in seen:
            raise SdeValidationError(f"Duplicate type ID {type_id}")
        seen.add(type_id)
        group_id = _required_int(record, "groupID", context)
        if group_id not in group_ids:
            raise SdeValidationError(
                f"Type {type_id} references missing group {group_id}"
            )
        rows.append(
            {
                "type_id": type_id,
                "group_id": group_id,
                "name": _english_name(record, context),
                "published": _required_bool(record, "published", context),
            }
        )
    return rows


def _parse_solar_systems(source: SdeSource) -> list[SolarSystemRow]:
    rows: list[SolarSystemRow] = []
    seen: set[int] = set()
    for line_number, record in _iter_records(source, "solar_systems"):
        context = f"mapSolarSystems line {line_number}"
        solar_system_id = _required_int(record, "_key", context, positive=True)
        if solar_system_id in seen:
            raise SdeValidationError(
                f"Duplicate solar system ID {solar_system_id}"
            )
        seen.add(solar_system_id)
        rows.append(
            {
                "solar_system_id": solar_system_id,
                "name": _english_name(record, context),
            }
        )
    return rows


def _parse_activity_types(
    source: SdeSource,
) -> tuple[list[ActivityTypeRow], dict[str, int]]:
    by_id: dict[int, tuple[str, str | None]] = {}
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for line_number, record in _iter_records(source, "activity_types"):
        context = f"industryActivities line {line_number}"
        activity_id = _required_int(record, "_key", context, positive=True)
        if activity_id in seen_ids:
            raise SdeValidationError(f"Duplicate industry activity ID {activity_id}")
        seen_ids.add(activity_id)
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SdeValidationError(f"{context}.name must be a non-empty string")
        if name in seen_names:
            raise SdeValidationError(f"Duplicate industry activity name {name!r}")
        seen_names.add(name)
        description = record.get("description")
        if description is not None and not isinstance(description, str):
            raise SdeValidationError(f"{context}.description must be a string")
        by_id[activity_id] = (name, description)

    rows: list[ActivityTypeRow] = []
    activity_ids: dict[str, int] = {}
    for code, activity_id in SUPPORTED_ACTIVITY_IDS.items():
        try:
            source_name, description = by_id[activity_id]
        except KeyError as exc:
            raise SdeValidationError(
                f"industryActivities is missing activity ID {activity_id} ({code})"
            ) from exc
        activity_ids[code] = activity_id
        rows.append(
            {
                "activity_id": activity_id,
                "code": code,
                "name": source_name,
                "description": description,
            }
        )
    return rows, activity_ids


def _relation_list(
    activity: Mapping[str, Any], field: str, context: str
) -> list[dict]:
    relations = activity.get(field, [])
    if not isinstance(relations, list) or not all(
        isinstance(relation, dict) for relation in relations
    ):
        raise SdeValidationError(f"{context}.{field} must be a list of objects")
    return relations


def _validate_deterministic_product(
    product: Mapping[str, Any], context: str
) -> None:
    probability = product.get("probability")
    if probability is None:
        return
    if isinstance(probability, bool):
        raise SdeValidationError(f"{context}.probability must equal 1")
    try:
        parsed_probability = Decimal(str(probability))
    except (InvalidOperation, ValueError) as exc:
        raise SdeValidationError(f"{context}.probability must be numeric") from exc
    if parsed_probability != Decimal(1):
        raise SdeValidationError(
            f"{context}.probability is unsupported for deterministic activities"
        )


def _parse_blueprints(
    source: SdeSource,
    types: list[TypeRow],
    activity_ids: dict[str, int],
) -> tuple[
    list[BlueprintRow],
    list[ActivityRow],
    list[MaterialRow],
    list[ProductRow],
    int,
    int,
    int,
]:
    type_publication = {row["type_id"]: row["published"] for row in types}
    type_ids = set(type_publication)
    blueprint_rows: list[BlueprintRow] = []
    activity_rows: list[ActivityRow] = []
    material_rows: list[MaterialRow] = []
    product_rows: list[ProductRow] = []
    seen_blueprints: set[int] = set()
    skipped_unpublished = 0
    skipped_without_supported = 0
    ignored_activities = 0

    for line_number, record in _iter_records(source, "blueprints"):
        context = f"blueprints line {line_number}"
        blueprint_type_id = _required_int(record, "_key", context, positive=True)
        if blueprint_type_id in seen_blueprints:
            raise SdeValidationError(
                f"Duplicate blueprint type ID {blueprint_type_id}"
            )
        seen_blueprints.add(blueprint_type_id)
        declared_blueprint_type_id = _required_int(
            record, "blueprintTypeID", context, positive=True
        )
        if declared_blueprint_type_id != blueprint_type_id:
            raise SdeValidationError(
                f"Blueprint key {blueprint_type_id} does not match "
                f"blueprintTypeID {declared_blueprint_type_id}"
            )
        if blueprint_type_id not in type_ids:
            raise SdeValidationError(
                f"Blueprint {blueprint_type_id} has no matching EVE type"
            )
        if not type_publication[blueprint_type_id]:
            skipped_unpublished += 1
            continue

        activities = record.get("activities")
        if not isinstance(activities, Mapping):
            raise SdeValidationError(f"{context}.activities must be an object")
        unknown_codes = set(activities) - KNOWN_ACTIVITY_CODES
        if unknown_codes:
            unknown = ", ".join(sorted(unknown_codes))
            raise SdeValidationError(
                f"Blueprint {blueprint_type_id} has unknown activities: {unknown}"
            )
        ignored_activities += len(set(activities) - set(activity_ids))
        supported_codes = [code for code in activity_ids if code in activities]
        if not supported_codes:
            skipped_without_supported += 1
            continue

        max_production_limit = _optional_positive_int(
            record, "maxProductionLimit", context
        )
        blueprint_rows.append(
            {
                "blueprint_type_id": blueprint_type_id,
                "max_production_limit": max_production_limit,
            }
        )

        for code in supported_codes:
            activity = activities[code]
            activity_context = f"blueprint {blueprint_type_id} activity {code}"
            if not isinstance(activity, Mapping):
                raise SdeValidationError(f"{activity_context} must be an object")
            activity_id = activity_ids[code]
            time_seconds = _required_int(
                activity, "time", activity_context, positive=True
            )
            activity_rows.append(
                {
                    "blueprint_type_id": blueprint_type_id,
                    "activity_id": activity_id,
                    "time_seconds": time_seconds,
                }
            )

            seen_materials: set[int] = set()
            for index, material in enumerate(
                _relation_list(activity, "materials", activity_context)
            ):
                relation_context = f"{activity_context}.materials[{index}]"
                material_type_id = _required_int(
                    material, "typeID", relation_context, positive=True
                )
                if material_type_id not in type_ids:
                    raise SdeValidationError(
                        f"{activity_context} references missing material type "
                        f"{material_type_id}"
                    )
                if material_type_id in seen_materials:
                    raise SdeValidationError(
                        f"{activity_context} repeats material type {material_type_id}"
                    )
                seen_materials.add(material_type_id)
                material_rows.append(
                    {
                        "blueprint_type_id": blueprint_type_id,
                        "activity_id": activity_id,
                        "material_type_id": material_type_id,
                        "quantity": _required_int(
                            material, "quantity", relation_context, positive=True
                        ),
                    }
                )

            products = _relation_list(activity, "products", activity_context)
            if not products:
                raise SdeValidationError(
                    f"{activity_context} must contain at least one product"
                )
            seen_products: set[int] = set()
            for index, product in enumerate(products):
                relation_context = f"{activity_context}.products[{index}]"
                product_type_id = _required_int(
                    product, "typeID", relation_context, positive=True
                )
                if product_type_id not in type_ids:
                    raise SdeValidationError(
                        f"{activity_context} references missing product type "
                        f"{product_type_id}"
                    )
                if product_type_id in seen_products:
                    raise SdeValidationError(
                        f"{activity_context} repeats product type {product_type_id}"
                    )
                seen_products.add(product_type_id)
                _validate_deterministic_product(product, relation_context)
                product_rows.append(
                    {
                        "blueprint_type_id": blueprint_type_id,
                        "activity_id": activity_id,
                        "product_type_id": product_type_id,
                        "quantity": _required_int(
                            product, "quantity", relation_context, positive=True
                        ),
                    }
                )

    return (
        blueprint_rows,
        activity_rows,
        material_rows,
        product_rows,
        skipped_unpublished,
        skipped_without_supported,
        ignored_activities,
    )


def parse_sde(source: SdeSource | Path | str) -> ParsedSde:
    source = source if isinstance(source, SdeSource) else SdeSource(source)
    manifest = _parse_manifest(source)
    categories = _parse_categories(source)
    if not categories:
        raise SdeValidationError("SDE contains no categories")
    category_ids = {row["category_id"] for row in categories}
    groups = _parse_groups(source, category_ids)
    if not groups:
        raise SdeValidationError("SDE contains no groups")
    group_ids = {row["group_id"] for row in groups}
    types = _parse_types(source, group_ids)
    if not types:
        raise SdeValidationError("SDE contains no types")
    solar_systems = _parse_solar_systems(source)
    if not solar_systems:
        raise SdeValidationError("SDE contains no solar systems")
    activity_types, activity_ids = _parse_activity_types(source)
    (
        blueprints,
        activities,
        materials,
        products,
        skipped_unpublished,
        skipped_without_supported,
        ignored_activities,
    ) = _parse_blueprints(source, types, activity_ids)
    if not blueprints or not activities or not products:
        raise SdeValidationError(
            "SDE contains no published manufacturing or reaction blueprints"
        )
    if not materials:
        raise SdeValidationError(
            "SDE contains no published manufacturing or reaction materials"
        )

    return ParsedSde(
        manifest=manifest,
        categories=categories,
        groups=groups,
        types=types,
        solar_systems=solar_systems,
        activity_types=activity_types,
        blueprints=blueprints,
        activities=activities,
        materials=materials,
        products=products,
        skipped_unpublished_blueprints=skipped_unpublished,
        skipped_blueprints_without_supported_activity=skipped_without_supported,
        ignored_activities=ignored_activities,
    )
