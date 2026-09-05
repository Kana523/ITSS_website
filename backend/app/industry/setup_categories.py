"""Product taxonomy used by category-specific manufacturing setup overrides.

The buckets mirror the manufacturing rig product classes exposed by the
calculator.  Explicit group matches take precedence over category matches.
That precedence is intentional for group 4902, which the application assigns
to the Tech I medium-ship bucket even though its broad SDE category also
participates in the Tech II medium-ship rule.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Final, Mapping


class IndustrySetupCategory(StrEnum):
    ADVANCED_COMPONENTS = "advanced_components"
    T1_SMALL_SHIPS = "t1_small_ships"
    T1_MEDIUM_SHIPS = "t1_medium_ships"
    T1_LARGE_SHIPS = "t1_large_ships"
    T2_SMALL_SHIPS = "t2_small_ships"
    T2_MEDIUM_SHIPS = "t2_medium_ships"
    T2_LARGE_SHIPS = "t2_large_ships"
    STRUCTURES = "structures"
    FIGHTERS_DRONES = "fighters_drones"
    EQUIPMENT = "equipment"
    AMMUNITION = "ammunition"
    CAPITAL_COMPONENTS = "capital_components"
    CAPITAL_SHIPS = "capital_ships"
    SUPERCAPITAL_SHIPS = "supercapital_ships"


INDUSTRY_SETUP_GROUP_IDS: Final[
    Mapping[IndustrySetupCategory, frozenset[int]]
] = MappingProxyType(
    {
        IndustrySetupCategory.ADVANCED_COMPONENTS: frozenset(
            {332, 334, 716, 913, 964}
        ),
        IndustrySetupCategory.T1_SMALL_SHIPS: frozenset({25, 31, 420}),
        IndustrySetupCategory.T1_MEDIUM_SHIPS: frozenset(
            {26, 28, 419, 463, 1201, 4902, 5087}
        ),
        IndustrySetupCategory.T1_LARGE_SHIPS: frozenset({27, 513, 941}),
        IndustrySetupCategory.T2_SMALL_SHIPS: frozenset(
            {324, 541, 830, 831, 834, 893, 1283, 1305, 1527, 1534}
        ),
        IndustrySetupCategory.T2_MEDIUM_SHIPS: frozenset(
            {358, 380, 540, 543, 832, 833, 894, 906, 963, 1202, 1972}
        ),
        IndustrySetupCategory.T2_LARGE_SHIPS: frozenset({898, 900, 902}),
        IndustrySetupCategory.STRUCTURES: frozenset({536, 1136, 4736}),
        IndustrySetupCategory.FIGHTERS_DRONES: frozenset(),
        IndustrySetupCategory.EQUIPMENT: frozenset({12, 340, 448, 649}),
        IndustrySetupCategory.AMMUNITION: frozenset(),
        IndustrySetupCategory.CAPITAL_COMPONENTS: frozenset({873}),
        IndustrySetupCategory.CAPITAL_SHIPS: frozenset(
            {485, 547, 883, 1538, 4594, 5120}
        ),
        IndustrySetupCategory.SUPERCAPITAL_SHIPS: frozenset({30, 659}),
    }
)


INDUSTRY_SETUP_CATEGORY_IDS: Final[
    Mapping[IndustrySetupCategory, frozenset[int]]
] = MappingProxyType(
    {
        IndustrySetupCategory.ADVANCED_COMPONENTS: frozenset(),
        IndustrySetupCategory.T1_SMALL_SHIPS: frozenset(),
        IndustrySetupCategory.T1_MEDIUM_SHIPS: frozenset(),
        IndustrySetupCategory.T1_LARGE_SHIPS: frozenset(),
        IndustrySetupCategory.T2_SMALL_SHIPS: frozenset(),
        IndustrySetupCategory.T2_MEDIUM_SHIPS: frozenset({32}),
        IndustrySetupCategory.T2_LARGE_SHIPS: frozenset(),
        IndustrySetupCategory.STRUCTURES: frozenset({23, 39, 40, 65, 66}),
        IndustrySetupCategory.FIGHTERS_DRONES: frozenset({18, 87}),
        IndustrySetupCategory.EQUIPMENT: frozenset({7, 20, 22}),
        IndustrySetupCategory.AMMUNITION: frozenset({8}),
        IndustrySetupCategory.CAPITAL_COMPONENTS: frozenset(),
        IndustrySetupCategory.CAPITAL_SHIPS: frozenset(),
        IndustrySetupCategory.SUPERCAPITAL_SHIPS: frozenset(),
    }
)


def _index_disjoint_ids(
    values_by_category: Mapping[IndustrySetupCategory, frozenset[int]],
    field_name: str,
) -> Mapping[int, IndustrySetupCategory]:
    indexed: dict[int, IndustrySetupCategory] = {}
    for setup_category, values in values_by_category.items():
        for value in values:
            previous = indexed.setdefault(value, setup_category)
            if previous != setup_category:
                raise RuntimeError(
                    f"Industry setup {field_name} {value} belongs to both "
                    f"{previous.value} and {setup_category.value}"
                )
    return MappingProxyType(indexed)


_CATEGORY_BY_GROUP_ID = _index_disjoint_ids(
    INDUSTRY_SETUP_GROUP_IDS,
    "group ID",
)
_CATEGORY_BY_CATEGORY_ID = _index_disjoint_ids(
    INDUSTRY_SETUP_CATEGORY_IDS,
    "category ID",
)


def industry_setup_category_for(
    *,
    category_id: int,
    group_id: int,
) -> IndustrySetupCategory | None:
    """Return the one setup bucket for a product, if the app recognizes it."""

    return _CATEGORY_BY_GROUP_ID.get(group_id) or _CATEGORY_BY_CATEGORY_ID.get(
        category_id
    )
