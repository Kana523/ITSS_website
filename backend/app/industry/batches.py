"""Bounded physical job allocation shared by material planning and scheduling."""
from fractions import Fraction

from app.industry.models import ActivityKind, ItemQuantity, ProductionBatch
from app.industry.errors import InvalidScheduleError
from app.industry.blueprint_library import BlueprintStockError

MAX_SCHEDULE_JOBS = 2000


def allocate_batches(recipe, runs, lots, efficiency, modifiers, implant_multiplier, max_runs_per_job, copy_limit=None):
    from app.industry.planner import _max_runs_within_job_time, _job_material_quantity

    batches = []
    remaining = runs
    if lots and not any(lot.kind == "bpo" for lot in lots):
        available = sum(lot.available_runs for lot in lots)
        if remaining > available:
            raise BlueprintStockError(recipe.key, remaining, available)
    # Untracked manufacturing assumes one original; reactions assume formulas available.
    sources = [(lot, index) for index, lot in enumerate(lots)] if lots else [(None, 0)]
    for lot, index in sources:
        if not remaining:
            break
        applied = lot.efficiency if lot else efficiency
        time_factor = Fraction(100 - applied.time_efficiency, 100) if applied else Fraction(1)
        material_factor = Fraction(100 - applied.material_efficiency, 100) if applied else Fraction(1)
        per_run = Fraction(recipe.time_seconds) * modifiers.time_multiplier * time_factor
        if recipe.activity == ActivityKind.MANUFACTURING:
            per_run *= implant_multiplier
        maximum = min(max_runs_per_job, _max_runs_within_job_time(per_run))
        copies = lot.quantity if lot else ((remaining + copy_limit - 1) // copy_limit if copy_limit else 1)
        runs_per_copy = lot.remaining_runs if lot and lot.kind == "bpc" else (copy_limit if not lot else None)
        if runs_per_copy == 0:
            continue
        if runs_per_copy is None and recipe.activity == ActivityKind.MANUFACTURING:
            used_copies = min(copies, remaining)
            maximum = min(maximum, (remaining + used_copies - 1) // used_copies)
        instance = 1
        while remaining and instance <= copies:
            instance_runs = min(remaining, runs_per_copy) if runs_per_copy is not None else remaining
            # Originals rotate batches across the owned instances; copies retain their remainders.
            while instance_runs:
                if len(batches) >= MAX_SCHEDULE_JOBS:
                    raise InvalidScheduleError("Schedule exceeds 2,000 jobs. Increase runs per job or reduce quantities.")
                batch_runs = min(instance_runs, maximum)
                inputs = tuple(ItemQuantity(material.type_id, _job_material_quantity(
                    material.quantity, batch_runs, modifiers.material_multiplier * material_factor,
                )) for material in recipe.materials)
                batches.append(ProductionBatch(batch_runs, applied, per_run * batch_runs, inputs,
                    lot.lot_id or f"selection-{index + 1}" if lot else None, instance))
                remaining -= batch_runs
                instance_runs -= batch_runs
                if runs_per_copy is None:
                    instance = instance % copies + 1
            if runs_per_copy is not None:
                instance += 1
            else:
                break
    return tuple(batches)
