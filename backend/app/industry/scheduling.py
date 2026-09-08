"""Deterministic scheduling of the same physical batches used for material totals."""
from datetime import timedelta
from math import ceil

from app.industry.errors import InvalidScheduleError


def create_schedule(plan, options, pricing=None):
    start = options["start_at"]
    workers = options["workers"]
    facilities = options["facilities"]
    assignments = {(row["recipe_key"]["blueprint_type_id"], row["recipe_key"]["activity_id"]): row
                   for row in options["assignments"]}
    worker_free = {}
    facility_free = {}
    for worker in workers:
        available = max(start, worker.get("available_from") or start)
        for activity in ("manufacturing", "reaction"):
            worker_free[worker["id"], activity] = [available] * worker[f"{activity}_slots"]
    for facility in facilities:
        facility_free[facility["id"]] = [start] * facility["slots"]
    blueprint_free = {}
    finished = {}
    product_ids = {step.product_type_id for step in plan.build_steps}
    jobs = []
    # All predecessor batches finish before the next production step begins.
    # This deliberately gives a conservative plan, not an optimal makespan.
    for step in plan.build_steps:
        activity = step.recipe.activity.value
        dependencies = sorted({item.type_id for item in step.inputs if item.type_id in product_ids})
        ready = max([start] + [finished[type_id] for type_id in dependencies])
        key = (step.recipe.key.blueprint_type_id, step.recipe.key.activity_id)
        assignment = assignments.get(key, {})
        system_id = None
        if step.industry_setup_override is not None:
            system_id = step.industry_setup_override.solar_system_id
        elif pricing is not None:
            system_id = pricing.solar_system_id if activity == "manufacturing" else pricing.reaction_solar_system_id
        eligible_workers = [worker for worker in workers if worker[f"{activity}_slots"]
                            and (not assignment.get("worker_id") or worker["id"] == assignment["worker_id"])]
        eligible_facilities = [facility for facility in facilities if facility["activity"] == activity
                               and (system_id is None or facility["solar_system_id"] == system_id)
                               and (not assignment.get("facility_id") or facility["id"] == assignment["facility_id"])]
        if not eligible_workers or not eligible_facilities:
            raise InvalidScheduleError(f"No available character slots or matching facility for {activity} blueprint {key[0]} in system {system_id or 'unspecified'}.")
        end = ready
        # Give every physical blueprint its first job before queuing its next.
        # Otherwise later jobs on one copy can reserve slots needed by idle copies.
        occurrences = {}
        queued = []
        for index, batch in enumerate(step.batches):
            source = (batch.lot_id, batch.blueprint_instance)
            wave = occurrences.get(source, 0) if activity == "manufacturing" else 0
            occurrences[source] = wave + 1
            queued.append((wave, index, batch))
        for _, _, batch in sorted(queued, key=lambda row: row[:2]):
            blueprint_key = (key, batch.lot_id, batch.blueprint_instance) if activity == "manufacturing" else None
            available = max(ready, blueprint_free.get(blueprint_key, start))
            best = None
            for worker in eligible_workers:
                slots = worker_free[worker["id"], activity]
                worker_slot = min(range(len(slots)), key=lambda index: (slots[index], index))
                for facility in eligible_facilities:
                    fslots = facility_free[facility["id"]]
                    facility_slot = min(range(len(fslots)), key=lambda index: (fslots[index], index))
                    candidate = (max(available, slots[worker_slot], fslots[facility_slot]), worker["id"], facility["id"], worker_slot, facility_slot)
                    if best is None or candidate < best:
                        best = candidate
            began, worker_id, facility_id, worker_slot, facility_slot = best
            try:
                ended = began + timedelta(microseconds=ceil(batch.exact_time_seconds * 1_000_000))
            except OverflowError as error:
                raise InvalidScheduleError("Schedule dates exceed the supported calendar range") from error
            worker_free[worker_id, activity][worker_slot] = ended
            facility_free[facility_id][facility_slot] = ended
            if blueprint_key is not None:
                blueprint_free[blueprint_key] = ended
            job_id = len(jobs) + 1
            jobs.append({"job_id": job_id, "product_type_id": step.product_type_id,
                "recipe_key": {"blueprint_type_id": key[0], "activity_id": key[1]}, "activity": activity,
                "runs": batch.runs, "output_quantity": batch.runs * step.output_per_run,
                "lot_id": batch.lot_id, "blueprint_instance": batch.blueprint_instance,
                "material_efficiency": batch.blueprint_efficiency.material_efficiency if batch.blueprint_efficiency else 0,
                "time_efficiency": batch.blueprint_efficiency.time_efficiency if batch.blueprint_efficiency else 0,
                "worker_id": worker_id, "worker_slot": worker_slot + 1, "facility_id": facility_id,
                "facility_slot": facility_slot + 1, "start_at": began, "end_at": ended,
                "duration_seconds": {"numerator": str(batch.exact_time_seconds.numerator), "denominator": str(batch.exact_time_seconds.denominator)},
                "inputs": [{"type_id": item.type_id, "quantity": item.quantity} for item in batch.inputs],
                "dependency_product_type_ids": dependencies})
            end = max(end, ended)
        finished[step.product_type_id] = end
    return {"start_at": start, "end_at": max([start] + list(finished.values())), "jobs": jobs,
            "assumptions": ["Purchased materials and owned inventory are available at the start.",
                            "All batches of each predecessor finish before dependent jobs begin; hauling time is excluded.",
                            "Characters use this project's skill profile. Facilities use its configured activity/category bonuses and fees.",
                            "Stock and slots are planned locally, not reserved in EVE or other projects."]}
