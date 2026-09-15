import json

from openapi_spec_validator import validate_spec

from app import main as app_module
from scripts.export_rapidapi_openapi import generate_rapidapi_openapi


def _count_occurrences(obj, needle):
    count = 0

    def is_legal_content_examples(value):
        return (
            isinstance(value, dict)
            and value
            and all(isinstance(item, dict) and "value" in item for item in value.values())
        )

    def walk(value):
        nonlocal count
        if isinstance(value, dict):
            if value.get("type") == needle:
                count += 1
            if "const" in value and needle == "const":
                count += 1
            if (
                "examples" in value
                and needle == "schema_examples"
                and not is_legal_content_examples(value["examples"])
            ):
                count += 1
            if "nullable" in value and needle == "nullable":
                count += 1
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(obj)
    return count


def _find_parameter(spec, path, name):
    for parameter in spec["paths"][path]["get"]["parameters"]:
        if parameter["name"] == name:
            return parameter["schema"]
    raise AssertionError(f"Parameter {name!r} not found in {path}")


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
    assert all(method.lower() in {"get"} for path in spec["paths"].values() for method in path)
    assert all(not path.startswith("/admin") for path in spec["paths"])
    assert all(not path.startswith("/importer") for path in spec["paths"])
    assert all(not path.startswith("/v1/import") for path in spec["paths"])
    validate_spec(spec)
    assert _count_occurrences(spec, "schema_examples") == 0
    assert _count_occurrences(spec, "nullable") >= 1

    language_schema = _find_parameter(spec, "/v1/sets", "language")
    assert language_schema["nullable"] is True
    assert language_schema["type"] == "string"
    assert "anyOf" not in language_schema

    cards_language = _find_parameter(spec, "/v1/cards", "language")
    assert cards_language["nullable"] is True
    assert cards_language["type"] == "string"

    card_detail = spec["components"]["schemas"]["CardDetail"]
    assert card_detail["properties"]["subtitle"]["nullable"] is True
    assert card_detail["properties"]["type"]["nullable"] is True
    assert card_detail["properties"]["rarity"]["nullable"] is True

    card_summary = spec["components"]["schemas"]["CardSummary"]
    assert card_summary["properties"]["subtitle"]["nullable"] is True
    assert card_summary["properties"]["type"]["nullable"] is True

    variant = spec["components"]["schemas"]["CardVariantResponse"]
    assert variant["properties"]["finish"]["nullable"] is True
    assert variant["properties"]["rarity"]["nullable"] is True
    assert variant["properties"]["serial_total"]["nullable"] is True

    set_detail = spec["components"]["schemas"]["SetDetail"]
    assert set_detail["properties"]["code"]["nullable"] is True
    assert set_detail["properties"]["edition"]["nullable"] is True
    assert set_detail["properties"]["release_date"]["nullable"] is True

    set_summary = spec["components"]["schemas"]["SetSummary"]
    assert set_summary["properties"]["code"]["nullable"] is True
    assert set_summary["properties"]["edition"]["nullable"] is True

    type_schema = spec["components"]["schemas"]["CardSearchResult"]["properties"]["type"]
    assert type_schema["enum"] == ["card"]
    assert "const" not in type_schema

    payload = json.dumps(spec)
    assert "RAPIDAPI_PROXY_SECRET" not in payload
    assert "X-RapidAPI-Proxy-Secret" not in payload
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
