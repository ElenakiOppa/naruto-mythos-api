"""
Tests for GET /ready.

Database connectivity is mocked rather than relying on whatever Postgres
state happens to exist on the machine running the tests -- this makes both
the "ready" and "not ready" paths deterministic and fast in any environment,
including one with no PostgreSQL installed at all.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ready_returns_200_when_database_is_reachable():
    with patch("app.api.v1.ready.engine") as mock_engine:
        mock_engine.connect.return_value.__enter__.return_value = MagicMock()

        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unreachable():
    with patch("app.api.v1.ready.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("connection refused")

        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ready_error_response_never_leaks_exception_details():
    sensitive_message = 'password authentication failed for user "admin" at host db.internal:5432'

    with patch("app.api.v1.ready.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception(sensitive_message)

        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}

    body_text = response.text.lower()
    assert "password" not in body_text
    assert "admin" not in body_text
    assert "db.internal" not in body_text
