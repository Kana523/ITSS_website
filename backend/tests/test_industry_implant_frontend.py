from pathlib import Path


def test_industry_frontend_loads_implant_extension() -> None:
    root = Path(__file__).resolve().parents[2]
    loader = (root / "assets" / "js" / "industry.js").read_text(encoding="utf-8")
    core = (root / "assets" / "js" / "industry-core.js").read_text(encoding="utf-8")
    implants = (root / "assets" / "js" / "industry-implants.js").read_text(
        encoding="utf-8"
    )

    assert "industry-core.js" in loader
    assert "industry-implants.js" in loader
    assert 'data-profile-skill="industry_level"' in core
    assert 'select.dataset.profileImplant = "manufacturing_time_implant"' in implants
    assert '["27170", "BX-801 · 1%"]' in implants
    assert '["27167", "BX-802 · 2%"]' in implants
    assert '["27171", "BX-804 · 4%"]' in implants
    assert "body.production_profile.manufacturing_time_implant" in implants
