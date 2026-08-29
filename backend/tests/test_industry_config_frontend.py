from pathlib import Path
import re


def _frontend_sources() -> tuple[str, str, str]:
    root = Path(__file__).resolve().parents[2]
    return (
        (root / "industry" / "index.html").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry.js").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry-configs.js").read_text(
            encoding="utf-8"
        ),
    )


def _workspace_sources() -> tuple[str, str, str, str]:
    root = Path(__file__).resolve().parents[2]
    return (
        (root / "industry" / "index.html").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry.js").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry-tabs.js").read_text(
            encoding="utf-8"
        ),
        (root / "assets" / "js" / "industry-core.js").read_text(
            encoding="utf-8"
        ),
    )


def test_industry_frontend_loads_saved_configs_after_implants() -> None:
    html, loader, configs = _frontend_sources()

    assert 'skills.src = new URL("industry-skills.js", baseUrl).href' in loader
    assert 'skills.addEventListener("load", loadCore' in loader
    assert loader.index("industry-core.js") < loader.index("industry-implants.js")
    assert loader.index("industry-implants.js") < loader.index("industry-tabs.js")
    assert loader.index("industry-tabs.js") < loader.index(
        "industry-configs.js"
    )
    assert loader.index("industry-configs.js") < loader.index("industry-market.js")
    assert "data-config-name" in html
    assert "data-config-select" in html
    assert "data-config-save" in html
    assert "data-config-load" not in html
    assert "data-config-delete" in html
    assert 'data-config-status role="status" aria-live="polite"' in html
    assert 'const STORAGE_KEY = "itss_industry_configurations_v1"' in configs
    assert 'const DRAFT_KEY = "itss_industry_configuration_draft_v1"' in configs
    assert "schema_version: SCHEMA_VERSION" in configs
    assert "window.localStorage.getItem" in configs
    assert "window.localStorage.setItem" in configs


def test_workspace_has_three_persistent_tabs_with_build_as_default() -> None:
    html, loader, tabs, _ = _workspace_sources()

    assert html.count("data-industry-tab=") == 3
    assert html.count("data-industry-panel=") == 3
    assert 'data-industry-tab="config"' in html
    assert 'data-industry-tab="build"' in html
    assert 'data-industry-tab="shopping"' in html
    assert (
        'data-industry-tab="build" type="button" role="tab" '
        'aria-selected="true"'
    ) in html
    assert (
        'data-industry-panel="build" role="tabpanel" '
        'aria-labelledby="industry-tab-build" tabindex="0">'
    ) in html
    assert (
        'data-industry-panel="config" role="tabpanel" '
        'aria-labelledby="industry-tab-config" tabindex="0" hidden'
    ) in html
    assert (
        'data-industry-panel="shopping" role="tabpanel" '
        'aria-labelledby="industry-tab-shopping" tabindex="0" hidden'
    ) in html

    assert "industry-tabs.js" in loader
    assert 'const STORAGE_KEY = "itss_industry_active_tab_v1"' in tabs
    assert 'const DEFAULT_TAB = "build"' in tabs
    assert "window.localStorage.getItem(STORAGE_KEY)" in tabs
    assert "window.localStorage.setItem(STORAGE_KEY, name)" in tabs
    assert "activate(storedTab(), { persist: false })" in tabs


def test_calculator_status_lives_only_in_build_tab() -> None:
    html, _, _, _ = _workspace_sources()

    build_panel_start = html.index('data-industry-panel="build"')
    shopping_panel_start = html.index('data-industry-panel="shopping"')
    build_panel = html[build_panel_start:shopping_panel_start]

    assert "industry-hero" not in html
    assert "Industry calculator" not in html
    assert html.count("data-api-state") == 1
    assert "data-api-state" in build_panel


def test_profile_selection_loads_immediately_and_default_is_unbonused() -> None:
    html, _, configs = _frontend_sources()

    assert '<option value="">Default</option>' in html
    assert 'new Option("Default", "")' in configs
    assert 'elements.select?.addEventListener("change", () => {' in configs
    assert "activateProfile(elements.select.value);" in configs
    assert "selected?.configuration || defaultConfiguration" in configs
    assert 'const name = configuration?.name || "Default"' in configs
    assert 'activateProfile("", { announce: false })' in configs

    assert 'data-active-profile-name>Default</strong>' in html
    assert html.count("data-active-profile-name") == 1
    assert 'value="unbonused">No structure bonus</option>' in html
    assert "data-industry-skill-groups" in html
    assert "data-trade-skill-groups" in html


def test_published_skill_catalog_is_categorized_and_sso_ready() -> None:
    root = Path(__file__).resolve().parents[2]
    skills = (root / "assets" / "js" / "industry-skills.js").read_text(
        encoding="utf-8"
    )
    type_ids = [int(value) for value in re.findall(r"skill\((\d+),", skills)]

    assert 'group(268, "production", "Production"' in skills
    assert 'group(270, "science", "Science"' in skills
    assert 'group(1218, "processing", "Processing"' in skills
    assert 'group(274, "trade", "Trade skills"' in skills
    assert len(type_ids) == 94
    assert len(set(type_ids)) == 94
    assert '3380: "industry_level"' in skills
    assert '3388: "advanced_industry_level"' in skills
    assert '45746: "reactions_level"' in skills
    assert 'scope: "esi-skills.read_skills.v1"' in skills
    assert 'endpoint: "/characters/{character_id}/skills"' in skills
    assert 'idField: "skill_id"' in skills
    assert 'defaultLevelField: "active_skill_level"' in skills
    assert "function applyEsiSkills" in skills


def test_skill_catalog_contains_requested_trade_skills() -> None:
    root = Path(__file__).resolve().parents[2]
    skills = (root / "assets" / "js" / "industry-skills.js").read_text(
        encoding="utf-8"
    )

    assert 'skill(16622, "Accounting")' in skills
    assert 'skill(3446, "Broker Relations")' in skills
    assert 'skill(16597, "Advanced Broker Relations")' in skills


def test_expanded_skills_are_persisted_by_type_id_without_breaking_v1_profiles() -> None:
    _, _, configs = _frontend_sources()

    assert "input.dataset.skillTypeId || input.dataset.profileSkill" in configs
    assert "raw.skills[key] ?? (legacyKey ? raw.skills[legacyKey] : undefined) ?? 0" in configs
    assert "raw.pricing.integers[key] ?? input.defaultValue" in configs
    assert "raw.pricing.percents[key] ?? input.defaultValue" in configs


def test_profiles_capture_settings_only() -> None:
    _, _, configs = _frontend_sources()

    assert "manufacturing_time_implant" in configs
    assert "activities" in configs
    assert "pricing:" in configs
    assert "latestPlan" not in configs
    assert "ownedMaterials" not in configs
    assert "demands" not in configs


def test_structure_controls_replace_raw_modifier_inputs() -> None:
    html, _, configs = _frontend_sources()

    assert html.count("data-structure-select") == 2
    assert html.count("data-security-select") == 2
    assert html.count("data-rig-tier-select") == 2
    assert 'value="raitaru"' in html
    assert 'value="azbel"' in html
    assert 'value="sotiyo"' in html
    assert 'value="athanor"' in html
    assert 'value="tatara"' in html
    assert 'data-derived-job-cost="manufacturing"' in html
    assert 'data-derived-job-cost="reaction"' in html
    assert 'type="number" value="0" min="0" max="99.99"' not in html

    assert "raitaru: Object.freeze({ material: 100, time: 1500, cost: 300 })" in configs
    assert "azbel: Object.freeze({ material: 100, time: 2000, cost: 400 })" in configs
    assert "sotiyo: Object.freeze({ material: 100, time: 3000, cost: 500 })" in configs
    assert "tatara: Object.freeze({ material: 0, time: 2500, cost: 0 })" in configs


def test_manufacturing_and_reaction_rigs_use_distinct_security_tables() -> None:
    _, _, configs = _frontend_sources()

    assert "lowsec: Object.freeze({ material: 380, time: 3800 })" in configs
    assert "nullsec: Object.freeze({ material: 504, time: 5040 })" in configs
    assert "lowsec: Object.freeze({ material: 200, time: 2000 })" in configs
    assert "nullsec: Object.freeze({ material: 264, time: 2640 })" in configs
    assert "wormhole: Object.freeze({ material: 264, time: 2640 })" in configs
    assert "formatCombinedReduction(structure.material, rig.material)" in configs
    assert "formatCombinedReduction(structure.time, rig.time)" in configs


def test_saved_configuration_captures_source_settings_not_derived_values() -> None:
    _, _, configs = _frontend_sources()

    assert "manufacturing_time_implant" in configs
    assert "activities" in configs
    assert "structure:" in configs
    assert "security:" in configs
    assert "rig:" in configs
    assert "pricing:" in configs
    assert '[data-pricing-percent]:not([data-derived-job-cost])' in configs
    assert "normalizeConfiguration" in configs
    assert "latestPlan" not in configs


def test_market_costs_are_grouped_with_general_scc_and_future_settings() -> None:
    html, _, _, core = _workspace_sources()

    assert "SCC surcharges" in html
    assert "Industry &amp; reactions" in html
    assert html.count('data-pricing-percent="scc_surcharge_basis_points"') == 1
    assert 'data-pricing-percent="reaction_scc_surcharge_basis_points"' not in html
    assert 'data-config-percent="science_scc_surcharge_basis_points"' in html
    assert "pricing.reaction_scc_surcharge_basis_points = pricing.scc_surcharge_basis_points" in core
    assert '<p class="pricing-subheading">Industry</p>' in html
    assert '<p class="pricing-subheading">Reactions</p>' in html
    assert '<p class="pricing-subheading">Science</p>' in html
    assert '<p class="pricing-subheading">Taxes</p>' in html
    assert "Immediate sale" not in html
    assert 'data-pricing-percent="broker_fee_basis_points"' in html
    assert 'data-config-percent="pi_tax_basis_points"' in html
    assert 'data-config-integer="science_solar_system_id"' in html
    assert 'data-config-percent="science_facility_tax_basis_points"' in html


def test_specialist_skill_payload_is_opt_in_and_excludes_trade_skills() -> None:
    _, _, _, core = _workspace_sources()

    assert "function readSpecialistSkills()" in core
    assert '[data-skill-role="industry"][data-skill-type-id]' in core
    assert "if (!hasSpecialistLevel) return null;" in core
    assert "if (specialistSkills) body.specialist_skills = specialistSkills;" in core


def test_inner_tab_headings_scroll_with_the_page() -> None:
    root = Path(__file__).resolve().parents[2]
    css = (root / "assets" / "styling" / "css" / "industry.css").read_text(
        encoding="utf-8"
    )
    heading_rule = css[css.index(".tab-heading {") : css.index(".tab-heading >")]

    assert "position: static;" in heading_rule
    assert "top: auto;" in heading_rule
    assert "z-index: auto;" in heading_rule


def test_shopping_tab_offers_only_eve_multibuy_copy() -> None:
    html, _, _, core = _workspace_sources()

    assert "Copy multibuy" in html
    assert "data-copy-shopping" in html
    assert "data-shopping-placeholder" in html
    assert "data-shopping-output" in html
    assert "data-download-shopping" not in html
    assert "Download CSV" not in html

    assert "function shoppingListText(plan)" in core
    assert "`${purchase.item.name} ${purchase.quantity}`" in core
    assert '.join("\\n")' in core
    assert "navigator.clipboard?.writeText" in core
    assert "await navigator.clipboard.writeText(value)" in core
    assert "shoppingListCsv" not in core
    assert "downloadShoppingList" not in core
    assert "text/csv" not in core


def test_owned_materials_are_sent_with_the_build_request() -> None:
    html, _, _, core = _workspace_sources()

    assert "data-owned-search-input" in html
    assert "data-owned-list" in html
    assert "data-clear-owned" in html
    assert "ownedMaterials: new Map()" in core
    assert "const ownedMaterials = readOwnedMaterials();" in core
    assert "if (ownedMaterials.length) body.owned_materials = ownedMaterials;" in core


def test_cleanup_removes_helper_copy_and_visible_sde_details() -> None:
    html, _, _, core = _workspace_sources()
    root = Path(__file__).resolve().parents[2]
    implants = (root / "assets" / "js" / "industry-implants.js").read_text(
        encoding="utf-8"
    )

    removed_helper_copy = (
        "Profiles stay on this browser",
        "Search published items with a manufacturing or reaction recipe",
        "the selected rig tier is applied to every manufactured item",
        "This interim rig choice assumes both material and time coverage",
        "Inputs use the cached best sell price",
        "Blueprint, skill, facility, and rig modifiers",
        "Build from top to bottom",
        "Aggregated across the full route",
    )
    for text in removed_helper_copy:
        assert text not in html
        assert text not in implants

    assert 'class="field-help"' not in html
    assert "industry-search-help" not in html
    assert "calculation-note" not in html
    assert "field-help" not in implants
    assert "calculation-note" not in implants

    visible_sde_copy = (
        "SDE build",
        "SDE database connected",
        "The SDE changed",
        "data-sde-build",
    )
    for text in visible_sde_copy:
        assert text not in html
        assert text not in core

    # Version pinning remains an internal safety contract even though it is hidden.
    assert "expected_sde_build_number" in core
    assert 'error.code === "sde_version_mismatch"' in core


def test_route_cards_show_final_values_without_base_or_profile_breakdowns() -> None:
    html, _, _, core = _workspace_sources()

    assert 'addMetric(metrics, "Runs", formatNumber(step.runs));' in core
    assert 'addMetric(metrics, "Surplus", formatNumber(step.surplus_quantity));' in core
    assert 'addMetric(metrics, "Job time", exactJobTime);' in core
    assert "formatNumber(input.total_quantity)" in core
    assert "renderCostComparison(comparison)" in core
    assert "data-economics-installation" in html
    assert "data-economics-profit" in html

    assert "renderProductionModifiers" not in core
    assert "route-profile-summary" not in core
    assert "baseJobTime" not in core
    assert "(base ${baseJobTime})" not in core
    assert "Base ${formatNumber(input.base_total_quantity)}" not in core
