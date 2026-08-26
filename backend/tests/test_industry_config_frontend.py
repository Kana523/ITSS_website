from pathlib import Path


def _frontend_sources() -> tuple[str, str, str]:
    root = Path(__file__).resolve().parents[2]
    return (
        (root / "industry" / "index.html").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry.js").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry-configs.js").read_text(
            encoding="utf-8"
        ),
    )


def test_industry_frontend_loads_saved_configs_after_implants() -> None:
    html, loader, configs = _frontend_sources()

    assert loader.index("industry-core.js") < loader.index("industry-implants.js")
    assert loader.index("industry-implants.js") < loader.index(
        "industry-configs.js"
    )
    assert loader.index("industry-configs.js") < loader.index("industry-market.js")
    assert "data-config-name" in html
    assert "data-config-select" in html
    assert "data-config-save" in html
    assert "data-config-load" in html
    assert "data-config-delete" in html
    assert 'data-config-status role="status" aria-live="polite"' in html
    assert 'const STORAGE_KEY = "itss_industry_configurations_v1"' in configs
    assert 'const DRAFT_KEY = "itss_industry_configuration_draft_v1"' in configs
    assert "schema_version: SCHEMA_VERSION" in configs
    assert "window.localStorage.getItem" in configs
    assert "window.localStorage.setItem" in configs


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
