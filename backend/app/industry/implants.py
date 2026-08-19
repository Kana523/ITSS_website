from dataclasses import replace
from enum import IntEnum
from fractions import Fraction

from app.industry.models import ActivityKind
from app.industry.views import DescribedProductionPlan


class ManufacturingTimeImplant(IntEnum):
    """Supported slot-8 hardwirings that reduce manufacturing job duration."""

    BX_801 = 27170
    BX_802 = 27167
    BX_804 = 27171

    @property
    def time_reduction_basis_points(self) -> int:
        return {
            ManufacturingTimeImplant.BX_801: 100,
            ManufacturingTimeImplant.BX_802: 200,
            ManufacturingTimeImplant.BX_804: 400,
        }[self]

    @property
    def time_multiplier(self) -> Fraction:
        return Fraction(10_000 - self.time_reduction_basis_points, 10_000)


def apply_manufacturing_time_implant(
    result: DescribedProductionPlan,
    implant: ManufacturingTimeImplant | None,
) -> DescribedProductionPlan:
    """Apply a selected BX hardwiring to manufacturing steps only.

    The core planner remains unchanged for callers that do not provide an implant.
    Material quantities, reactions, and valuation inputs are deliberately untouched.
    """
    if implant is None:
        return result

    multiplier = implant.time_multiplier
    build_steps = tuple(
        replace(
            step,
            exact_job_time_seconds=step.exact_job_time_seconds * multiplier,
        )
        if step.recipe.activity == ActivityKind.MANUFACTURING
        else step
        for step in result.plan.build_steps
    )
    if build_steps == result.plan.build_steps:
        return result

    return replace(
        result,
        plan=replace(result.plan, build_steps=build_steps),
    )
