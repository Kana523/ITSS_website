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
    IndustrySetupOverride,
    IndustryType,
    ItemQuantity,
    MAX_SAFE_INTEGER,
    ProductionProfile,
    PurchaseReason,
    RecipeKey,
    RigModifier,
)
from app.industry.planner import plan_production
from app.industry.setup_categories import (
    INDUSTRY_SETUP_CATEGORY_IDS,
    INDUSTRY_SETUP_GROUP_IDS,
    IndustrySetupCategory,
    industry_setup_category_for,
)


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


def test_industry_setup_category_mapping_is_exact_and_disjoint() -> None:
    assert set(IndustrySetupCategory) == set(INDUSTRY_SETUP_GROUP_IDS)
    assert set(IndustrySetupCategory) == set(INDUSTRY_SETUP_CATEGORY_IDS)
    assert dict(INDUSTRY_SETUP_GROUP_IDS) == {
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
    assert dict(INDUSTRY_SETUP_CATEGORY_IDS) == {
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

    group_ids = [
        group_id
        for group_ids in INDUSTRY_SETUP_GROUP_IDS.values()
        for group_id in group_ids
    ]
    category_ids = [
        category_id
        for category_ids in INDUSTRY_SETUP_CATEGORY_IDS.values()
        for category_id in category_ids
    ]
    assert len(group_ids) == len(set(group_ids))
    assert len(category_ids) == len(set(category_ids))


@pytest.mark.parametrize(
    ("category_id", "group_id", "expected"),
    [
        (6, 334, IndustrySetupCategory.ADVANCED_COMPONENTS),
        (6, 25, IndustrySetupCategory.T1_SMALL_SHIPS),
        (32, 4902, IndustrySetupCategory.T1_MEDIUM_SHIPS),
        (6, 513, IndustrySetupCategory.T1_LARGE_SHIPS),
        (6, 324, IndustrySetupCategory.T2_SMALL_SHIPS),
        (32, 999_001, IndustrySetupCategory.T2_MEDIUM_SHIPS),
        (6, 902, IndustrySetupCategory.T2_LARGE_SHIPS),
        (23, 999_002, IndustrySetupCategory.STRUCTURES),
        (18, 999_003, IndustrySetupCategory.FIGHTERS_DRONES),
        (7, 999_004, IndustrySetupCategory.EQUIPMENT),
        (8, 999_005, IndustrySetupCategory.AMMUNITION),
        (6, 873, IndustrySetupCategory.CAPITAL_COMPONENTS),
        (6, 485, IndustrySetupCategory.CAPITAL_SHIPS),
        (6, 30, IndustrySetupCategory.SUPERCAPITAL_SHIPS),
        (1, 999_006, None),
    ],
)
def test_industry_setup_category_representatives(
    category_id: int,
    group_id: int,
    expected: IndustrySetupCategory | None,
) -> None:
    assert industry_setup_category_for(
        category_id=category_id,
        group_id=group_id,
    ) == expected


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


def test_matching_setup_override_replaces_all_legacy_facility_and_rig_rules(
) -> None:
    recipe = _recipe(
        2001,
        1001,
        1,
        ((3001, 100),),
        time_seconds=100,
    )
    profile = ProductionProfile(
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
                material_reduction_basis_points=200,
                time_reduction_basis_points=2_000,
            ),
            RigModifier(
                ActivityKind.MANUFACTURING,
                material_reduction_basis_points=300,
                time_reduction_basis_points=3_000,
                group_ids=(25,),
            ),
        ),
        setup_overrides=(
            IndustrySetupOverride(
                category=IndustrySetupCategory.T1_SMALL_SHIPS,
                solar_system_id=30_002_665,
                facility_material_reduction_basis_points=1_000,
                facility_time_reduction_basis_points=3_000,
                rig_material_reduction_basis_points=500,
                rig_time_reduction_basis_points=1_000,
                job_cost_reduction_basis_points=400,
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
        production_profile=profile,
        product_types={1001: _industry_type(1001, group_id=25)},
    )

    step = plan.build_steps[0]
    assert step.inputs == (ItemQuantity(3001, 86),)
    assert step.exact_job_time_seconds == 63
    assert step.production_modifiers.facility_material_reduction_basis_points == 1_000
    assert step.production_modifiers.facility_time_reduction_basis_points == 3_000
    assert step.production_modifiers.rig_material_reduction_basis_points == 500
    assert step.production_modifiers.rig_time_reduction_basis_points == 1_000
    assert step.industry_setup_override is not None
    assert (
        step.industry_setup_override.category
        == IndustrySetupCategory.T1_SMALL_SHIPS
    )
    assert step.industry_setup_override.solar_system_id == 30_002_665
    assert step.industry_setup_override.job_cost_reduction_basis_points == 400


def test_unmatched_setup_override_uses_legacy_facility_and_scoped_rig() -> None:
    recipe = _recipe(2001, 1001, 1, ((3001, 100),), time_seconds=100)
    profile = ProductionProfile(
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
                material_reduction_basis_points=200,
                time_reduction_basis_points=2_000,
                group_ids=(12,),
            ),
        ),
        setup_overrides=(
            IndustrySetupOverride(
                category=IndustrySetupCategory.T1_SMALL_SHIPS,
                solar_system_id=30_002_665,
                facility_material_reduction_basis_points=1_000,
                facility_time_reduction_basis_points=3_000,
                rig_material_reduction_basis_points=500,
                rig_time_reduction_basis_points=1_000,
                job_cost_reduction_basis_points=400,
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
        production_profile=profile,
        product_types={1001: _industry_type(1001, group_id=12)},
    )

    step = plan.build_steps[0]
    assert step.inputs == (ItemQuantity(3001, 98),)
    assert step.exact_job_time_seconds == 68
    assert step.production_modifiers.facility_material_reduction_basis_points == 100
    assert step.production_modifiers.facility_time_reduction_basis_points == 1_500
    assert step.production_modifiers.rig_material_reduction_basis_points == 200
    assert step.production_modifiers.rig_time_reduction_basis_points == 2_000
    assert step.industry_setup_override is None


def test_reactions_ignore_matching_manufacturing_setup_override() -> None:
    recipe = _recipe(
        2001,
        1001,
        1,
        ((3001, 100),),
        activity_id=9,
        activity=ActivityKind.REACTION,
        time_seconds=100,
    )
    profile = ProductionProfile(
        facility_modifiers=(
            FacilityModifier(
                ActivityKind.REACTION,
                material_reduction_basis_points=100,
                time_reduction_basis_points=2_500,
            ),
        ),
        rig_modifiers=(
            RigModifier(
                ActivityKind.REACTION,
                material_reduction_basis_points=200,
                time_reduction_basis_points=2_000,
            ),
        ),
        setup_overrides=(
            IndustrySetupOverride(
                category=IndustrySetupCategory.T1_SMALL_SHIPS,
                solar_system_id=30_002_665,
                facility_material_reduction_basis_points=1_000,
                facility_time_reduction_basis_points=3_000,
                rig_material_reduction_basis_points=500,
                rig_time_reduction_basis_points=1_000,
                job_cost_reduction_basis_points=400,
            ),
        ),
    )

    plan = plan_production(
        (ItemQuantity(1001, 1),),
        (recipe,),
        sde_build_number=1,
        production_profile=profile,
    )

    step = plan.build_steps[0]
    assert step.inputs == (ItemQuantity(3001, 98),)
    assert step.exact_job_time_seconds == 60
    assert step.industry_setup_override is None


def test_setup_override_requires_manufacturing_product_metadata() -> None:
    recipe = _recipe(2001, 1001, 1, ())
    profile = ProductionProfile(
        setup_overrides=(
            IndustrySetupOverride(
                category=IndustrySetupCategory.T1_SMALL_SHIPS,
                solar_system_id=30_002_665,
            ),
        )
    )

    with pytest.raises(
        InvalidIndustryDataError,
        match="Product metadata is required to resolve industry setup overrides",
    ):
        plan_production(
            (ItemQuantity(1001, 1),),
            (recipe,),
            sde_build_number=1,
            production_profile=profile,
        )


def test_production_profile_sorts_and_rejects_duplicate_setup_categories() -> None:
    t2_large = IndustrySetupOverride(
        IndustrySetupCategory.T2_LARGE_SHIPS,
        30_000_142,
    )
    advanced_components = IndustrySetupOverride(
        IndustrySetupCategory.ADVANCED_COMPONENTS,
        30_002_665,
    )
    profile = ProductionProfile(
        setup_overrides=(t2_large, advanced_components)
    )

    assert profile.setup_overrides == (advanced_components, t2_large)
    assert profile.override_for(
        _industry_type(1001, group_id=902)
    ) == t2_large

    with pytest.raises(InvalidIndustryDataError, match="one setup override"):
        ProductionProfile(setup_overrides=(t2_large, t2_large))


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
