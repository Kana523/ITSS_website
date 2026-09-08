from fractions import Fraction

import pytest

from app.industry.blueprint_library import BlueprintSelection, normalize_selections
from app.industry.errors import InvalidIndustryDataError
from app.industry.models import BlueprintEfficiency, RecipeKey
from app.industry.planner import _job_material_quantity
from test_industry_api import api_client  # noqa: F401


def selection(**changes):
    return {"recipe_key": {"blueprint_type_id": 2002, "activity_id": 1}, "kind": "bpc", "quantity": 2,
            "remaining_runs": 3, "material_efficiency": 10, "time_efficiency": 20, **changes}


def calculation(**changes):
    return {"demands": [{"type_id": 1003, "quantity": 6}], "blueprint_selections": [selection()], **changes}


def test_library_catalog_supports_blueprint_or_product_id(api_client):
    for search in ("Final Product", "2002", "1003"):
        response = api_client.get("/api/industry/blueprints", params={"search": search})
        assert response.status_code == 200
        assert response.json()["items"][0]["blueprint_type_id"] == 2002
        assert response.json()["sde_build_number"] == 9000001
    assert api_client.get("/api/industry/blueprints", params={"search": "x", "limit": 101}).status_code == 422


def test_copy_stock_applies_efficiencies_and_checks_total_capacity(api_client):
    response = api_client.post("/api/industry/calculate", json=calculation())
    assert response.status_code == 200, response.text
    step = next(step for step in response.json()["build_steps"] if step["recipe_key"]["blueprint_type_id"] == 2002)
    assert step["runs"] == 6
    assert step["blueprint_efficiency"] == {"material_efficiency": 10, "time_efficiency": 20}
    response = api_client.post("/api/industry/calculate", json=calculation(demands=[{"type_id": 1003, "quantity": 7}]))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_blueprint_stock"
    assert response.json()["error"]["details"]["available_runs"] == 6
    assert response.json()["error"]["details"]["required_runs"] == 7


def test_originals_are_unlimited_and_exhausted_copies_only_block_needed_jobs(api_client):
    response = api_client.post("/api/industry/calculate", json=calculation(blueprint_selections=[selection(kind="bpo", remaining_runs=None, quantity=1)]))
    assert response.status_code == 200
    exhausted = calculation(blueprint_selections=[selection(remaining_runs=0)])
    assert api_client.post("/api/industry/calculate", json=exhausted).status_code == 409
    exhausted["owned_materials"] = [{"type_id": 1003, "quantity": 6}]
    assert api_client.post("/api/industry/calculate", json=exhausted).status_code == 200


def test_ownership_mode_checks_only_manufacturing_jobs_after_inventory(api_client):
    payload = calculation(blueprint_selections=[], require_owned_blueprints=True)
    assert api_client.post("/api/industry/calculate", json=payload).status_code == 409
    payload["owned_materials"] = [{"type_id": 1003, "quantity": 6}]
    assert api_client.post("/api/industry/calculate", json=payload).status_code == 200
    payload = calculation(require_owned_blueprints=True)
    # The reaction predecessor does not require a manufacturing BPO/BPC selection.
    assert api_client.post("/api/industry/calculate", json=payload).status_code == 200


def test_selected_library_recipe_resolves_ambiguous_product(api_client):
    payload = calculation(demands=[{"type_id": 1006, "quantity": 1}], blueprint_selections=[
        selection(recipe_key={"blueprint_type_id": 2005, "activity_id": 1})])
    response = api_client.post("/api/industry/calculate", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["build_steps"][0]["recipe_key"]["blueprint_type_id"] == 2005


@pytest.mark.parametrize("changes", [
    {"kind": "bpo"}, {"remaining_runs": None}, {"quantity": 0}, {"quantity": True},
    {"remaining_runs": -1}, {"time_efficiency": 3}, {"material_efficiency": 11},
    {"quantity": 9007199254740991, "remaining_runs": 2},
    {"recipe_key": {"blueprint_type_id": 2001, "activity_id": 9}},
])
def test_invalid_library_stock_is_rejected(api_client, changes):
    assert api_client.post("/api/industry/calculate", json=calculation(blueprint_selections=[selection(**changes)])).status_code == 422


def test_duplicate_and_conflicting_manual_inputs_rejected(api_client):
    assert api_client.post("/api/industry/calculate", json=calculation(blueprint_selections=[selection(), selection()])).status_code == 422
    manual = {"recipe_key": selection()["recipe_key"], "material_efficiency": 0, "time_efficiency": 0}
    assert api_client.post("/api/industry/calculate", json=calculation(blueprint_efficiencies=[manual])).status_code == 422
    assert api_client.post("/api/industry/calculate", json=calculation(blueprint_copy_run_limits=[{"recipe_key": selection()["recipe_key"], "runs_per_copy": 3}])).status_code == 422


def test_unused_stock_is_retained_without_breaking_a_different_project_route(api_client):
    assert api_client.post("/api/industry/calculate", json=calculation(demands=[{"type_id": 1002, "quantity": 1}])).status_code == 200


def test_copy_boundaries_preserve_each_time_limited_job_ceiling():
    # Two 10-run copies with a 6-run time limit must use 6+4+6+4, not 6+6+6+2.
    assert _job_material_quantity(2, 20, Fraction(9, 10), max_runs_per_job=6, runs_per_copy=10) == 38
    assert _job_material_quantity(2, 20, Fraction(9, 10), max_runs_per_job=6) == 37
    assert _job_material_quantity(2, 13, Fraction(9, 10), max_runs_per_job=6, runs_per_copy=10) == 25


def test_domain_rejects_duplicate_lots():
    lot = BlueprintSelection(RecipeKey(2002, 1), "bpc", 2, 3, BlueprintEfficiency(10, 20))
    with pytest.raises(InvalidIndustryDataError):
        normalize_selections([lot, lot])


def test_catalog_sql_matches_ids_and_names_and_excludes_unsupported_products():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.database.repositories.industry import SqlAlchemyIndustryRepository

    # Execute the catalog query against a small relational fixture. PostgreSQL
    # snapshot locking is covered separately by the integration suite.
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        session.execute(text("CREATE TABLE eve_types (type_id INTEGER, name TEXT, published BOOLEAN)"))
        session.execute(text("CREATE TABLE industry_activity_products (blueprint_type_id INTEGER, activity_id INTEGER, product_type_id INTEGER)"))
        session.execute(text("INSERT INTO eve_types VALUES (100, 'Rifter', 1), (200, 'Rifter Blueprint', 1), (300, 'Hidden Blueprint', 0), (400, 'Reaction Formula', 1), (500, 'Multi Blueprint', 1), (101, 'Other Product', 1)"))
        session.execute(text("INSERT INTO industry_activity_products VALUES (200, 1, 100), (300, 1, 100), (400, 9, 100), (500, 1, 100), (500, 1, 101)"))
        repository = SqlAlchemyIndustryRepository(session)
        repository._lock_sde_snapshot = lambda: None
        for query in ("rifter", "Rifter Blueprint", "200", "100"):
            assert [item.blueprint_type_id for item in repository.search_blueprints(query)] == [200]
        for query in ("%", "_", "Hidden", "Reaction", "Multi", "9999"):
            assert repository.search_blueprints(query) == ()
