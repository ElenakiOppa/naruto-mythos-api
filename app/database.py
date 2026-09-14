"""
Database engine and session management.

The engine is created lazily from configuration so importing this module
never has side effects that require a live database connection (important
for tooling like Alembic autogeneration and for unit tests that don't touch
the database).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _build_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        future=True,
        # A short connect timeout ensures that an unreachable/misconfigured
        # database (e.g. Postgres not running locally yet) fails fast rather
        # than hanging for the OS-level TCP timeout. This matters especially
        # for /health, which should always respond quickly.
        connect_args={"connect_timeout": 3},
    )


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
