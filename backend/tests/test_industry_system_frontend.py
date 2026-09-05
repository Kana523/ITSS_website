from pathlib import Path


def _sources() -> tuple[str, str, str, str, str]:
    root = Path(__file__).resolve().parents[2]
    return (
        (root / "industry" / "index.html").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry.js").read_text(encoding="utf-8"),
        (root / "assets" / "js" / "industry-systems.js").read_text(
            encoding="utf-8"
        ),
        (root / "assets" / "js" / "industry-configs.js").read_text(
            encoding="utf-8"
        ),
        (root / "assets" / "styling" / "css" / "industry.css").read_text(
            encoding="utf-8"
        ),
    )


def test_system_names_replace_visible_numeric_id_fields() -> None:
    html, loader, systems, configs, css = _sources()

    assert html.count("data-system-picker") == 3
    assert html.count("data-system-search") == 3
    assert html.count("data-system-index") == 3
    assert 'data-pricing-integer="solar_system_id" type="hidden"' in html
    assert 'data-system-activity="manufacturing"' in html
    assert 'data-system-activity="reaction"' in html
    assert 'data-system-activity="invention"' in html
    assert 'data-config-choice="science_activity"' in html
    assert "Solar system ID" not in html

    assert "industry-systems.js" in loader
    assert loader.index("industry-configs.js") < loader.index("industry-systems.js")
    assert loader.index("industry-systems.js") < loader.index("industry-market.js")
    assert "/api/industry/systems" in systems
    assert "/api/market/industry-index" in systems
    assert "numeric * 100" in systems
    assert 'snapshot.status === "fresh" ? "fresh" : "stale"' in systems
    assert "data-config-choice" in configs
    assert ".system-index-row" in css


def test_profile_application_resolves_saved_system_names_and_indices() -> None:
    _, _, systems, configs, _ = _sources()

    assert 'new CustomEvent("industry:configuration-applied")' in configs
    assert 'app.addEventListener("industry:configuration-applied"' in systems
    assert "pickers.forEach(resolveStoredSystem)" in systems
    assert "loadIndex(picker)" in systems
