from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from fractions import Fraction

import pytest

from app.api.schemas.scheduling import ScheduleRequest
from app.industry.models import ItemQuantity
from app.industry.planner import plan_production
from app.industry.scheduling import create_schedule
from app.industry.errors import InvalidIndustryDataError, InvalidScheduleError, QuantityTooLargeError
from test_blueprint_library import selection
from test_industry_api import api_client, MANUFACTURING_RECIPE  # noqa: F401


def options(**changes):
    return {"start_at": "2026-09-08T00:00:00Z", "max_runs_per_job": 2,
            "workers": [{"id": "pilot", "name": "Pilot", "manufacturing_slots": 2, "reaction_slots": 2}],
            "facilities": [{"id": "factory", "name": "Factory", "activity": "manufacturing", "solar_system_id": 30000142, "slots": 2},
                           {"id": "reactor", "name": "Reactor", "activity": "reaction", "solar_system_id": 30000142, "slots": 2}],
            "assignments": [], **changes}


def calculate(client, **changes):
    return client.post("/api/industry/calculate", json={"demands": [{"type_id": 1003, "quantity": 6}], "schedule": options(), **changes})


def manufacturing(body):
    return [job for job in body["schedule"]["jobs"] if job["activity"] == "manufacturing"]


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_serial(jobs):
    jobs = sorted(jobs, key=lambda job: instant(job["start_at"]))
    for left, right in zip(jobs, jobs[1:]):
        assert instant(left["end_at"]) <= instant(right["start_at"])


def test_dependencies_and_every_resource_exclude_overlap(api_client):
    response = calculate(api_client, blueprint_selections=[selection(lot_id="copies")])
    assert response.status_code == 200, response.text
    body = response.json()
    jobs = body["schedule"]["jobs"]
    predecessors = [job for job in jobs if job["activity"] == "reaction"]
    assert len(manufacturing(body)) == 4  # Each copy is split 2+1.
    resources = defaultdict(list)
    for job in jobs:
        resources["worker", job["worker_id"], job["activity"], job["worker_slot"]].append(job)
        resources["facility", job["facility_id"], job["facility_slot"]].append(job)
        if job["activity"] == "manufacturing":
            resources["blueprint", job["lot_id"], job["blueprint_instance"]].append(job)
            assert job["dependency_product_type_ids"] == [1002]
            assert instant(job["start_at"]) >= max(instant(row["end_at"]) for row in predecessors)
    for group in resources.values():
        assert_serial(group)
    # Two physical copies can run at the same time.
    first = {job["blueprint_instance"]: job for job in reversed(manufacturing(body))}
    assert first[1]["start_at"] == first[2]["start_at"]
    for step in body["build_steps"]:
        step_jobs = [job for job in jobs if job["product_type_id"] == step["product"]["type_id"]]
        assert sum(job["runs"] for job in step_jobs) == step["runs"]


def test_mixed_lot_rounding_and_time_drive_upstream_materials(api_client):
    lots = [selection(lot_id="researched", quantity=1, remaining_runs=3),
            selection(lot_id="plain", quantity=1, remaining_runs=3, material_efficiency=0, time_efficiency=0)]
    response = calculate(api_client, blueprint_selections=lots, schedule=options(max_runs_per_job=100))
    assert response.status_code == 200, response.text
    body = response.json()
    jobs = manufacturing(body)
    assert [(job["lot_id"], job["runs"], job["inputs"][0]["quantity"]) for job in jobs] == [("researched", 3, 11), ("plain", 3, 12)]
    assert [Fraction(int(job["duration_seconds"]["numerator"]), int(job["duration_seconds"]["denominator"])) for job in jobs] == [Fraction(744, 5), Fraction(186)]
    assert body["build_steps"][0]["runs"] == 12  # ceil(23 components / 2 output)
    assert body["build_steps"][1]["blueprint_efficiency"] is None
    assert "blueprint_material_efficiency" in body["applied_modifiers"]
    assert "blueprint_time_efficiency" in body["applied_modifiers"]
    # Smaller actual jobs round separately: 2+1 at ME10 uses 8+4, not 11.
    split = calculate(api_client, blueprint_selections=lots).json()
    assert sum(job["inputs"][0]["quantity"] for job in manufacturing(split)) == 24


def test_lot_priority_and_combined_copy_capacity(api_client):
    lots = [selection(lot_id="first", quantity=1, remaining_runs=3), selection(lot_id="second", quantity=1, remaining_runs=3)]
    assert calculate(api_client, blueprint_selections=lots).status_code == 200
    assert calculate(api_client, blueprint_selections=lots, demands=[{"type_id": 1003, "quantity": 7}]).status_code == 409
    lots[1] = selection(lot_id="original", kind="bpo", remaining_runs=None, quantity=1)
    jobs = manufacturing(calculate(api_client, blueprint_selections=lots).json())
    assert sum(job["runs"] for job in jobs if job["lot_id"] == "first") == 3
    assert sum(job["runs"] for job in jobs if job["lot_id"] == "original") == 3
    jobs = manufacturing(calculate(api_client, blueprint_selections=list(reversed(lots))).json())
    assert {job["lot_id"] for job in jobs} == {"original"}


@pytest.mark.parametrize("copies,expected_jobs", [(1, 1), (2, 2), (3, 3)])
def test_original_quantity_enables_parallel_batches(api_client, copies, expected_jobs):
    response = calculate(api_client, blueprint_selections=[selection(kind="bpo", remaining_runs=None, quantity=copies, lot_id="originals")], schedule=options(max_runs_per_job=100))
    assert response.status_code == 200, response.text
    jobs = manufacturing(response.json())
    assert len(jobs) == expected_jobs
    assert len({job["blueprint_instance"] for job in jobs}) == copies
    if copies > 1:
        assert jobs[0]["start_at"] == jobs[1]["start_at"]
    if copies == 3:
        assert instant(jobs[2]["start_at"]) >= instant(jobs[0]["end_at"])


@pytest.mark.parametrize("limit", ["worker", "facility", "blueprint"])
def test_individual_capacity_bottlenecks_are_respected(api_client, limit):
    schedule = options()
    if limit == "worker":
        schedule["workers"][0]["manufacturing_slots"] = 1
    if limit == "facility":
        schedule["facilities"][0]["slots"] = 1
    lots = [selection(kind="bpo", remaining_runs=None, quantity=1 if limit == "blueprint" else 2)]
    response = calculate(api_client, blueprint_selections=lots, schedule=schedule)
    assert response.status_code == 200, response.text
    assert_serial(manufacturing(response.json()))


def test_assignments_availability_timezone_and_missing_slots(api_client):
    schedule = options()
    schedule["workers"].append({"id": "later", "name": "Later", "manufacturing_slots": 1, "reaction_slots": 0, "available_from": "2026-09-09T02:00:00+02:00"})
    schedule["assignments"] = [{"recipe_key": {"blueprint_type_id": 2002, "activity_id": 1}, "worker_id": "later", "facility_id": "factory"}]
    response = calculate(api_client, schedule=schedule)
    assert response.status_code == 200, response.text
    jobs = manufacturing(response.json())
    assert {job["worker_id"] for job in jobs} == {"later"}
    assert instant(jobs[0]["start_at"]) == instant("2026-09-09T00:00:00Z")
    schedule["workers"][1]["manufacturing_slots"] = 0
    assert calculate(api_client, schedule=schedule).status_code == 422
    schedule["assignments"][0]["facility_id"] = "reactor"
    assert calculate(api_client, schedule=schedule).status_code == 422


@pytest.mark.parametrize("changes", [
    {"max_runs_per_job": 0}, {"max_runs_per_job": True}, {"workers": []}, {"facilities": []},
    {"start_at": "2026-09-08T00:00:00"},
    {"workers": [{"id": "pilot", "name": "Pilot", "manufacturing_slots": 12}]},
    {"assignments": [{"recipe_key": {"blueprint_type_id": 2002, "activity_id": 1}, "worker_id": "missing"}]},
])
def test_invalid_schedule_options_are_rejected(api_client, changes):
    assert calculate(api_client, schedule=options(**changes)).status_code == 422


def test_complete_inventory_needs_no_slots_or_blueprint_capacity(api_client):
    response = calculate(api_client, owned_materials=[{"type_id": 1003, "quantity": 6}], blueprint_selections=[selection(remaining_runs=0)], require_owned_blueprints=True)
    assert response.status_code == 200, response.text
    schedule = response.json()["schedule"]
    assert schedule["jobs"] == []
    assert schedule["start_at"] == schedule["end_at"]


def test_repeated_lot_id_across_different_recipes_is_a_request_error(api_client):
    lots = [selection(lot_id="duplicate"), selection(lot_id="duplicate", recipe_key={"blueprint_type_id": 2005, "activity_id": 1})]
    assert calculate(api_client, blueprint_selections=lots).status_code == 422


def test_copy_lot_cannot_exceed_sde_limit(api_client):
    response = calculate(api_client, blueprint_selections=[selection(remaining_runs=101)])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_schedule"


def test_physical_batches_obey_job_time_limit_and_copy_remainders():
    from app.industry.blueprint_library import BlueprintSelection
    from app.industry.models import BlueprintEfficiency
    recipe = replace(MANUFACTURING_RECIPE, time_seconds=5 * 24 * 60 * 60,
                     materials=(ItemQuantity(1002, 2),))
    efficiency = BlueprintEfficiency(10, 0)
    lot = BlueprintSelection(recipe.key, "bpc", 2, 10, efficiency, "copies")
    plan = plan_production([ItemQuantity(1003, 20)], [recipe], sde_build_number=1,
                           schedule_max_runs=100, scheduled_lots={recipe.key: (lot,)})
    batches = plan.build_steps[0].batches
    assert [batch.runs for batch in batches] == [6, 4, 6, 4]
    assert plan.build_steps[0].inputs[0].quantity == 38
    assert sum(batch.runs for batch in batches if batch.blueprint_instance == 1) == 10


def test_job_count_cap_and_calendar_overflow_are_structured_errors(api_client):
    response = calculate(api_client, demands=[{"type_id": 1003, "quantity": 2001}], schedule=options(max_runs_per_job=1))
    assert response.status_code == 422, response.text
    assert "2,000" in response.json()["error"]["message"]
    assert calculate(api_client, schedule=options(start_at="9999-12-31T23:59:59Z")).status_code == 422


def test_system_matching_and_microsecond_rounding():
    from types import SimpleNamespace
    recipe = replace(MANUFACTURING_RECIPE, time_seconds=1)
    plan = plan_production([ItemQuantity(1003, 1)], [recipe], sde_build_number=1,
                           schedule_max_runs=1, manufacturing_time_multiplier=Fraction(1, 3))
    settings = ScheduleRequest(**options()).model_dump()
    schedule = create_schedule(plan, settings, SimpleNamespace(solar_system_id=30000142))
    assert schedule["end_at"] - schedule["start_at"] == timedelta(microseconds=333334)
    with pytest.raises(InvalidScheduleError, match="matching facility"):
        create_schedule(plan, settings, SimpleNamespace(solar_system_id=30002665))


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5, 9007199254740992])
def test_direct_planner_rejects_invalid_schedule_batch_size(maximum):
    with pytest.raises((InvalidIndustryDataError, QuantityTooLargeError)):
        plan_production([ItemQuantity(1003, 1)], [MANUFACTURING_RECIPE], sde_build_number=1, schedule_max_runs=maximum)
