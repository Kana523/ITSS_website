import json
from pathlib import Path
from shutil import copytree

import pytest

from app.industry.models import SolarSystem
from app.sde.errors import SdeValidationError
from app.sde.parser import parse_sde
from app.sde.source import SdeSource


@pytest.mark.parametrize("system_id,status,expected", [
    (30000142, 0.945913, "highsec"),
    (30000142, 0.45, "highsec"),
    (30000142, 0.449999, "lowsec"),
    (30000142, 0.00001, "lowsec"),
    (30000142, 0, "nullsec"),
    (30000142, -0.9, "nullsec"),
    (31000005, -0.99, "wormhole"),
    (32000001, -1, None),
    (30000142, None, None),
])
def test_security_uses_true_status_and_space(system_id, status, expected):
    assert SolarSystem(system_id, "Test system", status).security_space == expected


@pytest.mark.parametrize("security", [True, "0.5", 1.1, -1.1, float("nan"), float("inf")])
def test_import_rejects_invalid_security(tmp_path, security):
    source = tmp_path / "sde"
    copytree(Path(__file__).parent / "fixtures" / "sde", source)
    path = source / "mapSolarSystems.jsonl"
    path.write_text(json.dumps({"_key": 30000142, "name": {"en": "Jita"}, "securityStatus": security}), encoding="utf-8")
    with pytest.raises(SdeValidationError, match="securityStatus"):
        parse_sde(SdeSource(source))
