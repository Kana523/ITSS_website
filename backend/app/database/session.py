from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import engine


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db_session() -> Generator[Session, None, None]:
    """Provide a database session and always close it after use."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
