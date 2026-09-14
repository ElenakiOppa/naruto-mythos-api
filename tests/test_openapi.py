"""
Confirms the application still starts and generates OpenAPI documentation
after the Phase 3 schema layer was added. New schemas aren't referenced by
any route yet (no catalogue endpoints exist until Phase 4+), so they won't
appear in the generated OpenAPI document -- this only proves adding them
didn't break app startup or /docs / /openapi.json, not that they're wired
into a route.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_docs_still_reachable():
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_json_still_reachable_and_well_formed():
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert schema["info"]["title"] == "Naruto Mythos TCG Developer API"
    # /health and /ready must still be documented.
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]
