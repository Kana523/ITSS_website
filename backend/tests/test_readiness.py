from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from app.main import create_app
from app.readiness import calculator_readiness
from app.sde.importer import import_sde
from app.sde.models import EveSolarSystem, IndustryActivityProduct


@pytest.mark.integration
def test_readiness_requires_imported_recipes_and_security(migrated_connection):
    connection = migrated_connection
    assert calculator_readiness(connection)["reason"] == "sde_not_imported"
    import_sde(Path(__file__).parent / "fixtures" / "sde", connection=connection)
    assert calculator_readiness(connection)["status"] == "ready"
    connection.execute(update(EveSolarSystem).values(security_status=None))
    assert calculator_readiness(connection)["reason"] == "system_security_incomplete"
    import_sde(Path(__file__).parent / "fixtures" / "sde", connection=connection)
    assert calculator_readiness(connection)["status"] == "ready"
    connection.execute(delete(IndustryActivityProduct))
    assert calculator_readiness(connection)["reason"] == "industry_data_incomplete"


@pytest.mark.parametrize("status_code,state", [(200, "ready"), (503, "unavailable")])
def test_readiness_http_status(monkeypatch, status_code, state):
    monkeypatch.setattr("app.main.calculator_readiness", lambda: {
        "status": state, "reason": None if state == "ready" else "sde_not_imported", "sde_build_number": None,
    })
    with TestClient(create_app()) as client:
        response = client.get("/api/ready")
    assert response.status_code == status_code
    assert response.json()["status"] == state
