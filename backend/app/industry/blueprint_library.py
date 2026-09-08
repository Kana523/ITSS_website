"""Project-selected blueprint stock; planning never mutates physical ownership."""
from dataclasses import dataclass
from collections.abc import Iterable

from app.industry.errors import IndustryPlanningError, InvalidIndustryDataError
from app.industry.models import BlueprintEfficiency, MAX_SAFE_INTEGER, RecipeKey


@dataclass(frozen=True, slots=True)
class BlueprintSelection:
    recipe_key: RecipeKey
    kind: str
    quantity: int
    remaining_runs: int | None
    efficiency: BlueprintEfficiency
    lot_id: str | None = None

    def __post_init__(self):
        if self.lot_id is not None and (not isinstance(self.lot_id, str) or not 1 <= len(self.lot_id) <= 100):
            raise InvalidIndustryDataError("Invalid blueprint lot ID")
        if not isinstance(self.recipe_key, RecipeKey) or self.recipe_key.activity_id != 1:
            raise InvalidIndustryDataError("Blueprint stock supports manufacturing recipes only")
        if self.kind not in {"bpo", "bpc"}:
            raise InvalidIndustryDataError("Blueprint kind must be bpo or bpc")
        if type(self.quantity) is not int or not 1 <= self.quantity <= MAX_SAFE_INTEGER:
            raise InvalidIndustryDataError("Blueprint quantity must be a positive safe integer")
        if not isinstance(self.efficiency, BlueprintEfficiency):
            raise InvalidIndustryDataError("Invalid blueprint efficiency")
        if self.kind == "bpo" and self.remaining_runs is not None:
            raise InvalidIndustryDataError("Original blueprints have unlimited runs")
        if self.kind == "bpc" and (type(self.remaining_runs) is not int
                or not 0 <= self.remaining_runs <= MAX_SAFE_INTEGER
                or self.quantity * self.remaining_runs > MAX_SAFE_INTEGER):
            raise InvalidIndustryDataError("Copy runs must be non-negative safe integers with a safe total")

    @property
    def available_runs(self) -> int | None:
        return None if self.kind == "bpo" else self.quantity * self.remaining_runs


def normalize_selections(values: Iterable[BlueprintSelection] | None) -> dict[RecipeKey, BlueprintSelection]:
    result = {}
    for value in values or ():
        if not isinstance(value, BlueprintSelection):
            raise InvalidIndustryDataError("Invalid blueprint selection")
        if value.recipe_key in result:
            raise InvalidIndustryDataError("Select one blueprint lot per recipe")
        result[value.recipe_key] = value
        if len(result) > 500:
            raise InvalidIndustryDataError("Select at most 500 blueprint lots")
    return result


def group_selections(values: Iterable[BlueprintSelection] | None) -> dict[RecipeKey, tuple[BlueprintSelection, ...]]:
    groups = {}
    ids = set()
    count = 0
    for value in values or ():
        if not isinstance(value, BlueprintSelection):
            raise InvalidIndustryDataError("Invalid blueprint selection")
        count += 1
        if count > 500 or (value.lot_id is not None and value.lot_id in ids):
            raise InvalidIndustryDataError("Too many or duplicate blueprint lots")
        if value.lot_id is not None:
            ids.add(value.lot_id)
        groups.setdefault(value.recipe_key, []).append(value)
    return {key: tuple(lots) for key, lots in groups.items()}


class BlueprintStockError(IndustryPlanningError):
    def __init__(self, recipe_key: RecipeKey, required_runs: int, available_runs: int):
        self.recipe_key = recipe_key
        self.required_runs = required_runs
        self.available_runs = available_runs
        super().__init__(f"Blueprint {recipe_key.blueprint_type_id} requires {required_runs} runs; "
                         f"the selected library stock provides {available_runs}. Select more stock or reduce the build quantity.")
