import pytest
from sqlalchemy.exc import StatementError

from app.market.__main__ import _safe_error_message, _validate_user_agent


@pytest.mark.parametrize(
    "value",
    ("", "python/3.14", "httpx/0.28.1", "generic"),
)
def test_refresh_cli_rejects_generic_user_agents(value: str) -> None:
    with pytest.raises(ValueError):
        _validate_user_agent(value)


def test_refresh_cli_accepts_an_application_specific_user_agent() -> None:
    assert _validate_user_agent(
        "ITS-S-EVE-Industry/0.1 (ops@example.com)"
    ) == "ITS-S-EVE-Industry/0.1 (ops@example.com)"


def test_refresh_cli_redacts_database_error_details() -> None:
    error = StatementError(
        "failed for postgresql://user:secret@database/example",
        "SELECT :password",
        {"password": "secret"},
        RuntimeError("secret"),
    )

    assert _safe_error_message(error) == "Database operation failed"
