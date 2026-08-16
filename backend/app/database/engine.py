from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings


engine = create_engine(
    get_settings().database_url.get_secret_value(),
    pool_pre_ping=True,
)


def is_database_available() -> bool:
    """Return whether the database accepts a simple query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False

    return True
