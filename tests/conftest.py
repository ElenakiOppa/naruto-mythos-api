"""
Root pytest configuration.

Setting DATABASE_URL here, at module import time (before any test module or
application module is imported), ensures the test suite works even when no
.env file has been created yet. This is only used to satisfy the
application's fail-fast config validation (Settings requires DATABASE_URL to
be a non-empty string) -- no test in this suite ever opens a real connection
to it. Model tests use their own isolated in-memory SQLite database (see the
`db_session` fixture below), and the /ready tests mock database connectivity
entirely rather than depending on it.

This does NOT change the application's runtime behavior -- app/database.py
still targets whatever DATABASE_URL is configured for real usage. This only
affects what the test suite sees when it isn't told anything else.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test_db")
os.environ.setdefault("CORS_ORIGINS", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 -- registers all models on Base.metadata
from app.database import Base


@pytest.fixture()
def db_session():
    """A fresh, isolated in-memory SQLite database for a single test.

    Per the project's technology policy, SQLite is used only here -- inside
    isolated tests -- never as an application runtime database. Foreign key
    enforcement is off by default in SQLite and is explicitly turned on so
    that ON DELETE CASCADE / SET NULL / RESTRICT behavior actually matches
    what will happen against real PostgreSQL.
    """
    # TestClient runs handlers in worker threads. Share one connection so they
    # see the same in-memory database, and permit its use across those threads.
    # A new engine per test keeps databases isolated between tests.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """A TestClient for HTTP-level route tests, wired to the same isolated
    in-memory SQLite database as `db_session` rather than the real
    PostgreSQL database the app is configured for.

    Route handlers depend on `app.database.get_db`; FastAPI's dependency
    override mechanism swaps that dependency out for the duration of the
    test so route tests stay fast, isolated, and don't require (or
    pollute) a real Postgres database -- consistent with the project's
    policy that SQLite is only ever used inside isolated tests.
    """
    from app.database import get_db
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
