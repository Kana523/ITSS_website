from fractions import Fraction

import pytest

from app.industry.errors import (
    AmbiguousRecipeError,
    BlueprintEfficiencyNotApplicableError,
    ConflictingRigModifiersError,
    InvalidIndustryDataError,
    InvalidRecipeChoiceError,
    MissingRecipeError,
    QuantityTooLargeError,
    RecipeCycleError,
    UnusedBlueprintEfficienciesError,
    UnusedBuildChoicesError,
    UnsupportedCoProductsError,
)
from app.industry.models import (
    ActivityKind,
    BlueprintEfficiency,
    BuildChoice,
    BuildDecision,
    CharacterIndustrySkills,
    FacilityModifier,
    IndustryRecipe,
    IndustryType,
    ItemQuantity,
    MAX_SAFE_INTEGER,
    ProductionProfile,
    PurchaseReason,
    RecipeKey,
    RigModifier,
)
from app.industry.planner import plan_production


def _recipe(
    blueprint_type_id: int,
    product_type_id: int,
    output_quantity: int,
    materials: tuple[tuple[int, int], ...],
    *,
    activity_id: int = 1,
    activity: ActivityKind = ActivityKind.MANUFACTURING,
    time_seconds: int = 60,
) -> IndustryRecipe:
    return IndustryRecipe(
        key=RecipeKey(blueprint_type_id, activity_id),
        blueprint_name=f"Blueprint {blueprint_type_id}",
        activity=activity,
        time_seconds=time_seconds,
        max_production_limit=100,
        products=(ItemQuantity(product_type_id, output_quantity),),
        materials=tuple(
            ItemQuantity(type_id, quantity) for type_id, quantity in materials
        ),
    )


def _industry_type(
    type_id: int,
    *,
    group_id: int = 10,
    category_id: int = 6,
) -> IndustryType:
    return IndustryType(
        type_id=type_id,
        name=f"Type {type_id}",
        published=True,
        group_id=group_id,
        group_name=f"Group {group_id}",
        category_id=category_id,
        category_name=f"Category {category_id}",
    )


def test_planner_builds_manufacturing_reaction_chain() -> None:
    recipes = (
        _recipe(
            2001,
            1002,
            2,
            ((1001, 3),),
            activity_id=9,
            activity=ActivityKind.REACTION,
        ),
        _recipe(2002, 1003, 1, ((1002, 4),)),
    )

    plan = plan_production(
        (ItemQuantity(1003, 1),),
        recipes,
        sde_build_number=9_000_001,
    )

    assert [step.product_type_id for step in plan.build_steps] == [1002, 1003]
    assert plan.build_steps[0].runs == 2
    assert plan.build_steps[0].produced_quantity == 4
    assert plan.build_steps[1].runs == 1
    assert [
        (item.type_id, item.quantity, item.reason) for item in plan.purchases
    ] == [(1001, 6, PurchaseReason.NO_RECIPE)]


def test_planner_aggregates_shared_demand_before_rounding() -> None:
    recipes = (
        _recipe(2001, 101, 1, ((103, 2),)),
        _recipe(2002, 102, 1, ((103, 2),)),
        _recipe(2003, 103, 5, ((104, 7),)),
    )

    plan = plan_production(
        (ItemQuantity(101, 1), ItemQuantity(102, 1)),
        reversed(recipes),
        sde_build_number=1,
    )

    shared_step = next(
        step for step in plan.build_steps if step.product_type_id == 103
    )
    assert shared_step.required_quantity == 4
    assert shared_step.runs == 1
    assert shared_step.produced_quantity == 5
    assert shared_step.surplus_quantity == 1
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [(104, 7)]
    assert [step.product_type_id for step in plan.build_steps] == [103, 101, 102]


def test_blueprint_me_rounds_once_for_the_whole_job() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 19),))

    plan = plan_production(
        (ItemQuantity(1001, 2),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(10, 0)},
    )

    step = plan.build_steps[0]
    assert step.inputs == (ItemQuantity(3001, 35),)
    assert step.blueprint_efficiency == BlueprintEfficiency(10, 0)
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [
        (3001, 35)
    ]


def test_blueprint_me_keeps_one_indivisible_material_per_run() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 1),))

    plan = plan_production(
        (ItemQuantity(1001, 10),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(10, 0)},
    )

    assert plan.build_steps[0].inputs == (ItemQuantity(3001, 10),)


def test_blueprint_me_uses_blueprint_runs_not_requested_output_units() -> None:
    recipe = _recipe(2001, 1001, 10, ((3001, 5),))

    plan = plan_production(
        (ItemQuantity(1001, 11),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(10, 0)},
    )

    step = plan.build_steps[0]
    assert step.runs == 2
    assert step.inputs == (ItemQuantity(3001, 9),)


def test_adjusted_parent_inputs_drive_recursive_demand() -> None:
    component = _recipe(2001, 1002, 6, ((3001, 2),))
    final_product = _recipe(2002, 1003, 1, ((1002, 19),))

    plan = plan_production(
        (ItemQuantity(1003, 2),),
        (component, final_product),
        sde_build_number=1,
        blueprint_efficiencies={
            final_product.key: BlueprintEfficiency(10, 0)
        },
    )

    component_step = next(
        step for step in plan.build_steps if step.product_type_id == 1002
    )
    assert component_step.required_quantity == 35
    assert component_step.runs == 6


def test_me_rounds_separate_parent_jobs_before_shared_demand_is_aggregated() -> None:
    recipes = (
        _recipe(2001, 1001, 1, ((1003, 19),)),
        _recipe(2002, 1002, 1, ((1003, 19),)),
        _recipe(2003, 1003, 10, ((1004, 1),)),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1), ItemQuantity(1002, 1)),
        recipes,
        sde_build_number=1,
        blueprint_efficiencies={
            recipes[0].key: BlueprintEfficiency(10, 0),
            recipes[1].key: BlueprintEfficiency(10, 0),
        },
    )

    shared_step = next(
        step for step in plan.build_steps if step.product_type_id == 1003
    )
    assert shared_step.required_quantity == 36
    assert shared_step.runs == 4


def test_blueprint_te_preserves_fractional_seconds_exactly() -> None:
    recipe = _recipe(2001, 1001, 1, (), time_seconds=62)

    plan = plan_production(
        (ItemQuantity(1001, 3),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(0, 20)},
    )

    step = plan.build_steps[0]
    assert step.base_total_job_time_seconds == 186
    assert step.total_job_time_centiseconds == 14_880
    assert step.display_job_time_seconds == 148


def test_exact_centiseconds_may_exceed_javascript_safe_integer() -> None:
    recipe = _recipe(
        2001,
        1001,
        1,
        (),
        time_seconds=MAX_SAFE_INTEGER,
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(0, 20)},
    )

    step = plan.build_steps[0]
    assert step.base_total_job_time_seconds == MAX_SAFE_INTEGER
    assert step.total_job_time_centiseconds == MAX_SAFE_INTEGER * 80


def test_production_profile_applies_all_factors_before_rounding() -> None:
    recipe = _recipe(
        2001,
        1001,
        1,
        ((3001, 7),),
        time_seconds=100,
    )
    profile = ProductionProfile(
        skills=CharacterIndustrySkills(
            industry_level=5,
            advanced_industry_level=5,
            reactions_level=5,
        ),
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=100,
                time_reduction_basis_points=1_500,
            ),
        ),
        rig_modifiers=(
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=504,
                time_reduction_basis_points=5_040,
                category_ids=(6,),
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
        blueprint_efficiencies={recipe.key: BlueprintEfficiency(10, 20)},
        production_profile=profile,
        product_types={1001: _industry_type(1001, category_id=6)},
    )

    step = plan.build_steps[0]
    # 7 * .90 * .99 * .9496 = 5.9226552, then one final ceiling.
    assert step.inputs == (ItemQuantity(3001, 6),)
    assert step.production_modifiers.character_time_multiplier == Fraction(
        17,
        25,
    )
    assert step.production_modifiers.facility_material_multiplier == Fraction(
        99,
        100,
    )
    assert step.production_modifiers.rig_material_multiplier == Fraction(
        1187,
        1250,
    )
    assert step.production_modifiers.material_multiplier == Fraction(
        117_513,
        125_000,
    )
    assert step.production_modifiers.facility_time_multiplier == Fraction(
        17,
        20,
    )
    assert step.production_modifiers.rig_time_multiplier == Fraction(
        62,
        125,
    )
    assert step.exact_job_time_seconds == (
        Fraction(100)
        * Fraction(80, 100)
        * Fraction(80, 100)
        * Fraction(85, 100)
        * Fraction(85, 100)
        * Fraction(4_960, 10_000)
    )
    assert step.display_job_time_seconds == 22
    assert step.total_job_time_centiseconds is None


def test_reaction_profile_uses_reactions_skill_not_industry_skills() -> None:
    reaction = _recipe(
        2001,
        1001,
        1,
        ((3001, 100),),
        activity_id=9,
        activity=ActivityKind.REACTION,
        time_seconds=100,
    )
    profile = ProductionProfile(
        skills=CharacterIndustrySkills(
            industry_level=5,
            advanced_industry_level=5,
            reactions_level=5,
        ),
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=9_000,
                time_reduction_basis_points=9_000,
            ),
            FacilityModifier(
                ActivityKind.REACTION,
                time_reduction_basis_points=2_500,
            ),
        ),
        rig_modifiers=(
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=9_000,
                time_reduction_basis_points=9_000,
                group_ids=(20,),
            ),
            RigModifier(
                ActivityKind.REACTION,
                material_reduction_basis_points=264,
                time_reduction_basis_points=2_640,
                group_ids=(20,),
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (reaction,),
        sde_build_number=1,
        production_profile=profile,
        product_types={1001: _industry_type(1001, group_id=20)},
    )

    step = plan.build_steps[0]
    assert step.blueprint_efficiency is None
    assert step.inputs == (ItemQuantity(3001, 98),)
    assert step.production_modifiers.character_time_multiplier == Fraction(4, 5)
    assert step.exact_job_time_seconds == Fraction(1_104, 25)
    assert step.total_job_time_centiseconds == 4_416


def test_rig_scopes_match_category_or_group_per_product() -> None:
    category_recipe = _recipe(2001, 1001, 1, ((3001, 100),))
    group_recipe = _recipe(2002, 1002, 1, ((3002, 100),))
    profile = ProductionProfile(
        rig_modifiers=(
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=1_000,
                category_ids=(6,),
            ),
            RigModifier(
                ActivityKind.MANUFACTURING,
                time_reduction_basis_points=2_000,
                group_ids=(20,),
            ),
        )
    )

    plan = plan_production(
        (ItemQuantity(1001, 1), ItemQuantity(1002, 1)),
        (category_recipe, group_recipe),
        sde_build_number=1,
        production_profile=profile,
        product_types={
            1001: _industry_type(1001, group_id=10, category_id=6),
            1002: _industry_type(1002, group_id=20, category_id=7),
        },
    )

    category_step = next(
        step for step in plan.build_steps if step.product_type_id == 1001
    )
    group_step = next(
        step for step in plan.build_steps if step.product_type_id == 1002
    )
    assert category_step.inputs == (ItemQuantity(3001, 90),)
    assert category_step.exact_job_time_seconds == 60
    assert group_step.inputs == (ItemQuantity(3002, 100),)
    assert group_step.exact_job_time_seconds == 48


def test_planner_rejects_overlapping_rig_modifiers_per_dimension() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 100),))
    profile = ProductionProfile(
        rig_modifiers=(
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=200,
                category_ids=(6,),
            ),
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=240,
                group_ids=(10,),
            ),
        )
    )

    with pytest.raises(ConflictingRigModifiersError) as error:
        plan_production(
            (ItemQuantity(1001, 1),),
            (recipe,),
            sde_build_number=1,
            production_profile=profile,
            product_types={1001: _industry_type(1001)},
        )

    assert error.value.recipe_key == recipe.key
    assert error.value.dimension == "material requirements"


def test_scoped_rig_modifier_requires_product_metadata() -> None:
    recipe = _recipe(2001, 1001, 1, ())

    with pytest.raises(InvalidIndustryDataError, match="Product metadata"):
        plan_production(
            (ItemQuantity(1001, 1),),
            (recipe,),
            sde_build_number=1,
            production_profile=ProductionProfile(
                rig_modifiers=(
                    RigModifier(
                        ActivityKind.MANUFACTURING,
                        time_reduction_basis_points=2_000,
                        category_ids=(6,),
                    ),
                )
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("industry_level", -1),
        ("industry_level", 6),
        ("industry_level", True),
        ("advanced_industry_level", -1),
        ("advanced_industry_level", 6),
        ("reactions_level", -1),
        ("reactions_level", 6),
    ],
)
def test_character_skill_levels_are_strictly_validated(
    field_name: str,
    invalid_value: object,
) -> None:
    values = {
        "industry_level": 0,
        "advanced_industry_level": 0,
        "reactions_level": 0,
    }
    values[field_name] = invalid_value

    with pytest.raises(InvalidIndustryDataError, match="integer from 0 to 5"):
        CharacterIndustrySkills(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_value", [-1, 10_000, True])
def test_modifier_basis_points_are_strictly_validated(
    invalid_value: object,
) -> None:
    with pytest.raises(InvalidIndustryDataError, match="basis points"):
        FacilityModifier(
            ActivityKind.MANUFACTURING,
            material_reduction_basis_points=invalid_value,  # type: ignore[arg-type]
            time_reduction_basis_points=1,
        )
    with pytest.raises(InvalidIndustryDataError, match="basis points"):
        RigModifier(
            ActivityKind.MANUFACTURING,
            material_reduction_basis_points=invalid_value,  # type: ignore[arg-type]
            time_reduction_basis_points=1,
        )


def test_modifiers_require_a_nonzero_effect() -> None:
    with pytest.raises(InvalidIndustryDataError, match="must reduce"):
        FacilityModifier(ActivityKind.MANUFACTURING)
    with pytest.raises(InvalidIndustryDataError, match="must reduce"):
        RigModifier(ActivityKind.MANUFACTURING)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("category_ids", (6, 6)),
        ("category_ids", (0,)),
        ("category_ids", [6]),
        ("group_ids", (10, 10)),
        ("group_ids", (0,)),
        ("group_ids", [10]),
    ],
)
def test_rig_scope_ids_are_strictly_validated(
    field_name: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "activity": ActivityKind.MANUFACTURING,
        "time_reduction_basis_points": 1,
        field_name: invalid_value,
    }
    with pytest.raises(InvalidIndustryDataError):
        RigModifier(**values)  # type: ignore[arg-type]


def test_production_profile_rejects_duplicate_facility_activity() -> None:
    with pytest.raises(InvalidIndustryDataError, match="one facility modifier"):
        ProductionProfile(
            facility_modifiers=(
                FacilityModifier(
                    ActivityKind.MANUFACTURING,
                    time_reduction_basis_points=100,
                ),
                FacilityModifier(
                    ActivityKind.MANUFACTURING,
                    material_reduction_basis_points=100,
                ),
            )
        )


def test_reactions_reject_blueprint_efficiency_settings() -> None:
    reaction = _recipe(
        2001,
        1001,
        1,
        ((3001, 2),),
        activity_id=9,
        activity=ActivityKind.REACTION,
    )

    with pytest.raises(BlueprintEfficiencyNotApplicableError):
        plan_production(
            (ItemQuantity(1001, 1),),
            (reaction,),
            sde_build_number=1,
            blueprint_efficiencies={
                reaction.key: BlueprintEfficiency(10, 20)
            },
        )

    plan = plan_production(
        (ItemQuantity(1001, 2),),
        (reaction,),
        sde_build_number=1,
    )
    assert plan.build_steps[0].blueprint_efficiency is None
    assert plan.build_steps[0].inputs == (ItemQuantity(3001, 4),)


def test_planner_rejects_efficiency_outside_selected_graph() -> None:
    with pytest.raises(UnusedBlueprintEfficienciesError) as error:
        plan_production(
            (ItemQuantity(1001, 1),),
            (),
            sde_build_number=1,
            blueprint_efficiencies={
                RecipeKey(9999, 1): BlueprintEfficiency(10, 20)
            },
        )

    assert error.value.recipe_keys == (RecipeKey(9999, 1),)


def test_planner_honors_global_buy_override() -> None:
    recipes = (
        _recipe(2001, 1002, 2, ((1001, 3),)),
        _recipe(2002, 1003, 1, ((1002, 4),)),
    )

    plan = plan_production(
        (ItemQuantity(1003, 1),),
        recipes,
        sde_build_number=1,
        choices={1002: BuildChoice(BuildDecision.BUY)},
    )

    assert [step.product_type_id for step in plan.build_steps] == [1003]
    assert plan.purchases[0].type_id == 1002
    assert plan.purchases[0].quantity == 4
    assert plan.purchases[0].reason == PurchaseReason.BUY_OVERRIDE


def test_planner_requires_explicit_choice_for_ambiguous_recipe() -> None:
    first = _recipe(2001, 1001, 1, ((3001, 2),))
    second = _recipe(2002, 1001, 1, ((3002, 3),))

    with pytest.raises(AmbiguousRecipeError) as error:
        plan_production(
            (ItemQuantity(1001, 1),),
            (second, first),
            sde_build_number=1,
        )
    assert error.value.candidates == (first.key, second.key)

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (second, first),
        sde_build_number=1,
        choices={
            1001: BuildChoice(
                BuildDecision.BUILD,
                recipe_key=second.key,
            )
        },
    )
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [(3002, 3)]


def test_planner_reports_cycles_and_buy_choice_can_break_them() -> None:
    recipes = (
        _recipe(2001, 1001, 1, ((1002, 1),)),
        _recipe(2002, 1002, 1, ((1001, 1),)),
    )

    with pytest.raises(RecipeCycleError) as error:
        plan_production(
            (ItemQuantity(1001, 1),),
            recipes,
            sde_build_number=1,
        )
    assert error.value.type_path == (1001, 1002, 1001)

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        recipes,
        sde_build_number=1,
        choices={1002: BuildChoice(BuildDecision.BUY)},
    )
    assert [step.product_type_id for step in plan.build_steps] == [1001]
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [(1002, 1)]


def test_planner_rejects_forced_build_without_recipe() -> None:
    with pytest.raises(MissingRecipeError):
        plan_production(
            (ItemQuantity(1001, 1),),
            (),
            sde_build_number=1,
            choices={1001: BuildChoice(BuildDecision.BUILD)},
        )


def test_planner_supports_zero_material_recipe() -> None:
    plan = plan_production(
        (ItemQuantity(1001, 2),),
        (_recipe(2001, 1001, 1, ()),),
        sde_build_number=1,
    )

    assert plan.build_steps[0].runs == 2
    assert plan.purchases == ()


def test_planner_rejects_multi_product_recipe_until_coproducts_are_supported() -> None:
    recipe = IndustryRecipe(
        key=RecipeKey(2001, 1),
        blueprint_name="Co-product Blueprint",
        activity=ActivityKind.MANUFACTURING,
        time_seconds=60,
        max_production_limit=100,
        products=(ItemQuantity(1001, 1), ItemQuantity(1002, 1)),
        materials=(ItemQuantity(3001, 1),),
    )

    with pytest.raises(UnsupportedCoProductsError):
        plan_production(
            (ItemQuantity(1001, 1),),
            (recipe,),
            sde_build_number=1,
        )


def test_planner_aggregates_duplicate_root_demands() -> None:
    plan = plan_production(
        (ItemQuantity(1001, 2), ItemQuantity(1001, 3)),
        (),
        sde_build_number=1,
    )

    assert plan.requested == (ItemQuantity(1001, 5),)
    assert [(item.type_id, item.quantity) for item in plan.purchases] == [(1001, 5)]


def test_planner_rejects_calculated_values_javascript_cannot_represent() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 2),))

    with pytest.raises(QuantityTooLargeError) as error:
        plan_production(
            (ItemQuantity(1001, MAX_SAFE_INTEGER),),
            (recipe,),
            sde_build_number=1,
        )

    assert error.value.maximum == MAX_SAFE_INTEGER
    assert error.value.field_name == "Total job time for type 1001"


def test_planner_rejects_choices_outside_the_selected_graph() -> None:
    with pytest.raises(UnusedBuildChoicesError) as error:
        plan_production(
            (ItemQuantity(1001, 1),),
            (),
            sde_build_number=1,
            choices={9999: BuildChoice(BuildDecision.BUY)},
        )

    assert error.value.type_ids == (9999,)


def test_planner_rejects_invalid_explicit_recipe_choice() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 1),))

    with pytest.raises(InvalidRecipeChoiceError):
        plan_production(
            (ItemQuantity(1001, 1),),
            (recipe,),
            sde_build_number=1,
            choices={
                1001: BuildChoice(
                    BuildDecision.BUILD,
                    recipe_key=RecipeKey(9999, 1),
                )
            },
        )


def test_domain_rejects_invalid_choice_and_activity_values() -> None:
    with pytest.raises(InvalidIndustryDataError, match="BuildDecision"):
        BuildChoice("typo")  # type: ignore[arg-type]

    with pytest.raises(InvalidIndustryDataError, match="ActivityKind"):
        IndustryRecipe(
            key=RecipeKey(2001, 1),
            blueprint_name="Invalid Blueprint",
            activity="manufacturing",  # type: ignore[arg-type]
            time_seconds=60,
            max_production_limit=1,
            products=(ItemQuantity(1001, 1),),
            materials=(),
        )

    with pytest.raises(InvalidIndustryDataError, match="positive integers"):
        plan_production(
            (ItemQuantity(1001, 1),),
            (),
            sde_build_number=1,
            choices={True: BuildChoice()},
        )
    with pytest.raises(InvalidIndustryDataError, match="must be a BuildChoice"):
        plan_production(
            (ItemQuantity(1001, 1),),
            (),
            sde_build_number=1,
            choices={1001: "buy"},  # type: ignore[dict-item]
        )

    for material_efficiency, time_efficiency in (
        (-1, 0),
        (11, 0),
        (0, -2),
        (0, 3),
        (0, 22),
    ):
        with pytest.raises(InvalidIndustryDataError):
            BlueprintEfficiency(material_efficiency, time_efficiency)


def test_catalog_metadata_accepts_official_zero_ids() -> None:
    system_type = IndustryType(
        type_id=0,
        name="#System",
        published=False,
        group_id=0,
        group_name="System",
        category_id=0,
        category_name="System",
    )

    assert system_type.type_id == 0
    with pytest.raises(InvalidIndustryDataError, match="positive integer"):
        ItemQuantity(0, 1)
