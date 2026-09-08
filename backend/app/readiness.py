"""Calculator readiness, separate from the process/database health probe."""
from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError

from app.database.engine import engine
from app.sde.models import (
    EveSolarSystem, EveType, IndustryActivity, IndustryActivityMaterial,
    IndustryActivityProduct, SdeImport,
)


def calculator_readiness(connection=None) -> dict[str, str | int | None]:
    if connection is None:
        try:
            with engine.connect() as active:
                return calculator_readiness(active)
        except SQLAlchemyError:
            return {"status": "unavailable", "reason": "database_or_schema_unavailable", "sde_build_number": None}
    latest = connection.execute(
        select(SdeImport.id, SdeImport.build_number).order_by(SdeImport.id.desc()).limit(1)
    ).one_or_none()
    if latest is None:
        return {"status": "unavailable", "reason": "sde_not_imported", "sde_build_number": None}
    for model in (EveType, IndustryActivity, IndustryActivityMaterial, IndustryActivityProduct, EveSolarSystem):
        if not connection.scalar(select(exists().where(model.last_seen_import_id == latest.id))):
            return {"status": "unavailable", "reason": "industry_data_incomplete", "sde_build_number": latest.build_number}
    if connection.scalar(select(exists().where(
        EveSolarSystem.last_seen_import_id == latest.id,
        EveSolarSystem.security_status.is_(None),
    ))):
        return {"status": "unavailable", "reason": "system_security_incomplete", "sde_build_number": latest.build_number}
    return {"status": "ready", "reason": None, "sde_build_number": latest.build_number}


if __name__ == "__main__":
    import json
    result = calculator_readiness()
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "ready" else 1)
