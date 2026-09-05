from pathlib import Path
import re


EXPECTED_CATEGORIES = (
    "advanced_components",
    "t1_small_ships",
    "t1_medium_ships",
    "t1_large_ships",
    "t2_small_ships",
    "t2_medium_ships",
    "t2_large_ships",
    "structures",
    "fighters_drones",
    "equipment",
    "ammunition",
    "capital_components",
    "capital_ships",
    "supercapital_ships",
)


def _sources() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    paths = {
        "html": root / "industry" / "index.html",
        "loader": root / "assets" / "js" / "industry.js",
        "overrides": root / "assets" / "js" / "industry-overrides.js",
        "configs": root / "assets" / "js" / "industry-configs.js",
        "core": root / "assets" / "js" / "industry-core.js",
        "systems": root / "assets" / "js" / "industry-systems.js",
        "css": root / "assets" / "styling" / "css" / "industry.css",
    }
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


def test_category_override_catalog_is_exact_and_has_no_freighter_row() -> None:
    source = _sources()["overrides"]
    catalog = source[
        source.index("const CATEGORIES") : source.index("const STRUCTURE_PROFILES")
    ]
    categories = tuple(re.findall(r'category: "([a-z0-9_]+)"', catalog))

    assert categories == EXPECTED_CATEGORIES
    assert len(categories) == len(set(categories)) == 14
    assert "freighters_jump_freighters" not in source
    assert "Includes Freighters" in catalog
    assert "Includes Jump Freighters" in catalog


def test_override_card_follows_pricing_and_rows_exist_before_configs() -> None:
    sources = _sources()
    html = sources["html"]
    loader = sources["loader"]
    overrides = sources["overrides"]

    assert html.index("data-pricing-details") < html.index(
        "data-category-overrides-card"
    )
    assert "Category setup overrides" in html
    assert "data-category-overrides-list" in html
    assert "data-category-overrides-count" in html
    assert loader.index("industry-overrides.js") < loader.index(
        "industry-configs.js"
    ) < loader.index("industry-systems.js")
    assert 'createElement("details", "category-override")' in overrides
    assert "CATEGORIES.forEach" in overrides
    assert "list.replaceChildren(fragment)" in overrides


def test_override_rows_are_inheriting_accessible_system_pickers_by_default() -> None:
    overrides = _sources()["overrides"]

    assert 'fields.disabled = true' in overrides
    assert 'rows.forEach((row) => setEnabled(row, false))' in overrides
    assert 'checkbox.type = "checkbox"' in overrides
    assert 'toggle.htmlFor = checkboxId' in overrides
    assert 'search.setAttribute("role", "combobox")' in overrides
    assert 'search.setAttribute("aria-controls", resultsId)' in overrides
    assert 'search.dataset.systemSearch = ""' in overrides
    assert 'results.setAttribute("role", "listbox")' in overrides
    assert "setup-override-${definition.category}-system-results" in overrides
    assert "setup-override-${definition.category}-enabled" in overrides


def test_profile_storage_keeps_source_choices_and_accepts_legacy_profiles() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    configs = sources["configs"]

    for function_name in (
        "capture",
        "normalize",
        "apply",
        "sourceControls",
        "readRequest",
    ):
        assert f"function {function_name}(" in overrides
        assert function_name in overrides[overrides.index("Object.freeze({") :]
    assert "setup_overrides: setupOverrides.capture()" in configs
    assert "setupOverrides.normalize(raw.setup_overrides)" in configs
    assert "setupOverrides.apply(configuration.setup_overrides)" in configs
    assert "if (raw === undefined || raw === null) return [];" in overrides
    assert 'const SCHEMA_VERSION = 1' in configs


def test_request_payload_contains_exact_setup_override_values() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    core = sources["core"]

    for field in (
        "category",
        "solar_system_id",
        "facility_material_reduction_basis_points",
        "facility_time_reduction_basis_points",
        "rig_material_reduction_basis_points",
        "rig_time_reduction_basis_points",
        "job_cost_reduction_basis_points",
    ):
        assert field in overrides
    assert "structureProfile(\"manufacturing\", entry.structure)" in overrides
    assert "rigProfile(\"manufacturing\", entry.rig, entry.security)" in overrides
    assert "globalThis.industrySetupOverrides?.readRequest()" in core
    assert "profile.setup_overrides = setupOverrideResult.value;" in core
    assert "profile.setup_overrides.length > 0" in core


def test_facility_and_rig_tables_are_shared_with_general_settings() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    configs = sources["configs"]

    assert "const STRUCTURE_PROFILES" in overrides
    assert "const RIG_PROFILES" in overrides
    assert "const STRUCTURE_PROFILES" not in configs
    assert "const RIG_PROFILES" not in configs
    assert "setupOverrides.structureProfile" in configs
    assert "setupOverrides.rigProfile" in configs


def test_override_layout_is_full_width_and_responsive_four_two_one() -> None:
    css = _sources()["css"]

    assert ".config-card--category-overrides" in css
    assert "grid-column: 1 / -1;" in css
    assert (
        "grid-template-columns: repeat(3, minmax(120px, 0.75fr)) "
        "minmax(280px, 1.6fr);"
    ) in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".category-override-grid {\n    grid-template-columns: 1fr;" in css
    assert ".category-override-summary:focus-visible" in css


def test_enabled_override_requires_system_without_requesting_blank_rows() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    systems = sources["systems"]

    assert 'valid ? "" : "Select a solar system from the results."' in overrides
    assert 'if (!Number.isInteger(solarSystemId) || solarSystemId <= 0)' in systems
    assert 'app.addEventListener("industry:system-picker-refresh"' in systems
    assert "if (pickers.includes(picker)) resolveStoredSystem(picker);" in systems


def test_generated_override_changes_invalidate_visible_calculations() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    core = sources["core"]

    assert 'new CustomEvent("industry:setup-overrides-changed")' in overrides
    assert 'app.addEventListener("industry:setup-overrides-changed"' in core
    assert (
        'markCalculationDirty("Category setup changed. '
        'Calculate a new production route.")'
    ) in core


def test_restored_override_summary_updates_after_system_name_resolution() -> None:
    sources = _sources()
    overrides = sources["overrides"]
    systems = sources["systems"]

    assert 'new CustomEvent("industry:system-picker-resolved"' in systems
    assert 'app.addEventListener("industry:system-picker-resolved"' in overrides
    assert "if (row && list.contains(row)) updateSummary(row);" in overrides
