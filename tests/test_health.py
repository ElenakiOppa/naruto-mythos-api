"""
Tests for GET /health.

/health must be a pure liveness endpoint: no database access, so it must
respond quickly regardless of whether PostgreSQL is reachable. This is
enforced with a timing assertion, not just a correctness assertion, since a
previous version of this endpoint pinged the database and could take
minutes to respond when Postgres was unavailable.
"""

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Generous but meaningful ceiling: a pure in-process liveness check should
# take milliseconds. A few seconds still proves it isn't doing network I/O
# (which, unreachable, would take multiple seconds at an absolute minimum
# given the database engine's own 3-second connect_timeout).
MAX_HEALTH_RESPONSE_SECONDS = 2.0


def test_health_returns_ok_status_and_version():
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"


def test_health_response_has_no_extra_sensitive_fields():
    response = client.get("/health")
    body = response.json()

    # Ensure only the documented, safe fields are present -- nothing that
    # could leak database URLs, credentials, or infra details.
    assert set(body.keys()) == {"status", "version"}


def test_health_responds_quickly_even_without_a_database():
    start = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < MAX_HEALTH_RESPONSE_SECONDS, (
        f"/health took {elapsed:.2f}s -- it must never perform database I/O"
    )
