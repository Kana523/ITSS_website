import json
from collections.abc import Mapping
from typing import Any, TypedDict

from app.sde.errors import SdeValidationError
from app.sde.parser import KNOWN_ACTIVITY_CODES, SUPPORTED_ACTIVITY_IDS
from app.sde.source import DATASET_FILENAMES, SdeSource


class SkillRow(TypedDict):
    blueprint_type_id: int
    activity_id: int
    skill_type_id: int
    required_level: int


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


def parse_blueprint_skill_rows(
    source: SdeSource,
    *,
    known_type_ids: set[int],
) -> list[SkillRow]:
    """Read specialist skill requirements for supported industry activities."""
    rows: list[SkillRow] = []
    filename = DATASET_FILENAMES["blueprints"]
    with source.open_text("blueprints") as stream:
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
            context = f"blueprints line {line_number}"
            blueprint_type_id = _required_int(
                record,
                "_key",
                context,
                positive=True,
            )
            activities = record.get("activities")
            if not isinstance(activities, Mapping):
                raise SdeValidationError(f"{context}.activities must be an object")
            unknown_codes = set(activities) - KNOWN_ACTIVITY_CODES
            if unknown_codes:
                unknown = ", ".join(sorted(unknown_codes))
                raise SdeValidationError(
                    f"Blueprint {blueprint_type_id} has unknown activities: {unknown}"
                )

            for code, activity_id in SUPPORTED_ACTIVITY_IDS.items():
                activity = activities.get(code)
                if activity is None:
                    continue
                activity_context = f"blueprint {blueprint_type_id} activity {code}"
                if not isinstance(activity, Mapping):
                    raise SdeValidationError(f"{activity_context} must be an object")
                skills = activity.get("skills", [])
                if not isinstance(skills, list) or not all(
                    isinstance(skill, dict) for skill in skills
                ):
                    raise SdeValidationError(
                        f"{activity_context}.skills must be a list of objects"
                    )
                seen_skill_ids: set[int] = set()
                for index, skill in enumerate(skills):
                    skill_context = f"{activity_context}.skills[{index}]"
                    skill_type_id = _required_int(
                        skill,
                        "typeID",
                        skill_context,
                        positive=True,
                    )
                    if skill_type_id not in known_type_ids:
                        raise SdeValidationError(
                            f"{activity_context} references missing skill type "
                            f"{skill_type_id}"
                        )
                    if skill_type_id in seen_skill_ids:
                        raise SdeValidationError(
                            f"{activity_context} repeats skill type {skill_type_id}"
                        )
                    seen_skill_ids.add(skill_type_id)
                    level = _required_int(
                        skill,
                        "level",
                        skill_context,
                        positive=True,
                    )
                    if level > 5:
                        raise SdeValidationError(
                            f"{skill_context}.level must be from 1 to 5"
                        )
                    rows.append(
                        {
                            "blueprint_type_id": blueprint_type_id,
                            "activity_id": activity_id,
                            "skill_type_id": skill_type_id,
                            "required_level": level,
                        }
                    )
    return rows
