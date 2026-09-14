import json

from app import main as app_module
from scripts.export_rapidapi_openapi import generate_rapidapi_openapi


def test_generate_rapidapi_openapi_exports_3_0_2(client):
    spec = generate_rapidapi_openapi()
    assert spec["openapi"] == "3.0.2"
    assert "/health" in spec["paths"]
    assert "/ready" in spec["paths"]
    assert "/v1/sets" in spec["paths"]
    assert "/v1/cards" in spec["paths"]
    assert "/v1/search" in spec["paths"]

    operations = [
        operation
        for path in spec["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operations) == 12
    assert len({item["operationId"] for item in operations}) == len(operations)

    payload = json.dumps(spec)
    assert "RAPIDAPI_PROXY_SECRET" not in payload
    assert "secret" not in payload.lower()


def test_rapidapi_proxy_secret_is_optional_and_safe(client, monkeypatch):
    monkeypatch.setattr(app_module.settings, "rapidapi_proxy_secret", None)
    response = client.get("/v1/sets")
    assert response.status_code == 200

    monkeypatch.setattr(app_module.settings, "rapidapi_proxy_secret", "proxy-secret")
    missing = client.get("/v1/sets")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "FORBIDDEN"
    assert "proxy-secret" not in json.dumps(missing.json()).lower()

    wrong = client.get("/v1/sets", headers={"X-RapidAPI-Proxy-Secret": "wrong"})
    assert wrong.status_code == 403

    ok = client.get(
        "/v1/sets",
        headers={"X-RapidAPI-Proxy-Secret": "proxy-secret"},
    )
    assert ok.status_code == 200

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
