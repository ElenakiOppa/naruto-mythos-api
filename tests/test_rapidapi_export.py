"""Regression tests for export-only compatibility and semantic preservation."""

import json
from copy import deepcopy

import pytest
from fastapi.routing import APIRoute
from jsonschema import Draft202012Validator, ValidationError
from openapi_schema_validator import OAS30Validator
from openapi_spec_validator import OpenAPIV30SpecValidator

from app.main import app
from scripts.export_rapidapi_openapi import (
    OUTPUT,
    PUBLIC_PATHS,
    _convert_document,
    _normalize_schema,
    _unique_object,
    generate_rapidapi_openapi,
    validate_rapidapi_openapi,
    write_rapidapi_openapi,
)


@pytest.mark.parametrize(
    "schema",
    [
        {"anyOf": [{"type": "string"}, {"type": "null"}]},
        {"anyOf": [{"type": "string", "enum": ["test"]}, {"type": "null"}]},
        {"anyOf": [{}, {"type": "integer"}]},
        {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
        {"oneOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
        {"oneOf": [{}, {"type": "null"}]},
        {"anyOf": [{"type": "string"}, {"type": "null"}], "enum": ["test"]},
        {"type": ["string", "integer", "null"]},
        {"type": ["string", "null"], "enum": ["test"]},
        {"type": "null"},
        {"const": None},
        {"type": "string", "const": "test", "enum": ["test", "other"]},
        {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 4},
        {"type": "number", "minimum": 2, "exclusiveMinimum": 0},
        {"type": "number", "maximum": 2, "exclusiveMaximum": 4},
        {"type": "array", "items": False},
        {"type": "object", "additionalProperties": False},
        True,
        False,
    ],
)
def test_conversion_preserves_validation_semantics(schema):
    original = deepcopy(schema)
    converted = _normalize_schema(schema)
    OpenAPIV30SpecValidator(
        {
            "openapi": "3.0.2",
            "info": {"title": "Test", "version": "1"},
            "paths": {},
            "components": {"schemas": {"Test": converted}},
        }
    ).validate()
    canonical_validator = Draft202012Validator(schema)
    exported_validator = OAS30Validator(converted)
    for value in (None, "test", "other", "", -1, 0, 1, 2, 3, 4, 4.5, True, [], [1], {}):
        assert exported_validator.is_valid(value) == canonical_validator.is_valid(value), (
            schema,
            converted,
            value,
        )
    assert schema == original


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#/components/schemas/Test", "description": "Keep this", "maxLength": 4},
        {"anyOf": [{"$ref": "#/components/schemas/Test"}, {"type": "null"}]},
    ],
)
def test_reference_siblings_and_nullable_references(schema):
    components = {"schemas": {"Test": {"type": "string", "minLength": 2}}}
    converted = _normalize_schema(schema)
    source = {**schema, "components": components}
    target = {**converted, "components": components}
    for value in (None, "", "a", "test", "longer", 1, {}, []):
        assert OAS30Validator(target).is_valid(value) == Draft202012Validator(source).is_valid(
            value
        )
    assert "$ref" not in converted


def test_examples_are_opaque_and_named_examples_stay_named():
    payload = {"const": "literal", "type": "null", "examples": [1, 2], "$ref": "data"}
    source = {
        "components": {
            "schemas": {
                "Test": {
                    "type": "object",
                    "examples": [payload],
                    "default": payload,
                    "properties": {"examples": {"type": "string"}},
                    "x-custom": payload,
                }
            }
        },
        "paths": {
            "/test": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "examples": {
                                        "inline": {"value": payload, "description": "Keep me"},
                                        "external": {
                                            "externalValue": "https://example.invalid/example.json"
                                        },
                                        "reference": {"$ref": "#/components/examples/Test"},
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    original = deepcopy(source)
    converted = _convert_document(source)
    assert converted["paths"] == source["paths"]
    result = converted["components"]["schemas"]["Test"]
    assert result["example"] == payload
    assert result["default"] == payload
    assert result["x-custom"] == payload
    assert result["properties"]["examples"] == {"type": "string"}
    assert source == original
    assert _normalize_schema({"examples": ["a"], "example": "b"}) == {"example": "b"}


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("$defs", {}),
        ("$id", "https://example.invalid/schema"),
        ("unevaluatedProperties", False),
        ("prefixItems", []),
        ("contains", {}),
        ("if", {}),
        ("then", {}),
        ("else", {}),
        ("dependentSchemas", {}),
        ("patternProperties", {}),
        ("contentEncoding", "base64"),
    ],
)
def test_unrepresentable_keywords_fail_closed(keyword, value):
    with pytest.raises(ValueError, match="Unsupported"):
        _normalize_schema({keyword: value})


def test_schema_dialect_annotations_are_removed_only_from_schema():
    assert _normalize_schema({"$schema": "dialect", "$comment": "comment", "type": "string"}) == {
        "type": "string"
    }
    assert _convert_document({"jsonSchemaDialect": "dialect"}) == {}


def test_export_preserves_canonical_contract_and_is_deterministic():
    original = deepcopy(app.openapi())
    exported = generate_rapidapi_openapi()
    assert app.openapi() == original
    assert original["openapi"].startswith("3.1")
    assert exported == generate_rapidapi_openapi()
    assert set(exported["paths"]) == PUBLIC_PATHS
    assert len(exported["paths"]) == 12
    for path in PUBLIC_PATHS:
        source = original["paths"][path]["get"]
        target = exported["paths"][path]["get"]
        for field in ("operationId", "tags", "description", "summary"):
            assert source.get(field) == target.get(field)
        assert target.get("parameters", []) == _convert_document(source.get("parameters", []))
        assert target["responses"] == _convert_document(source["responses"])
    assert set(original["components"]["schemas"]) == set(exported["components"]["schemas"])
    OpenAPIV30SpecValidator(exported).validate()


@pytest.mark.parametrize(
    "problem",
    [
        "path",
        "method",
        "operation_id",
        "duplicate_id",
        "path_required",
        "path_missing",
        "duplicate_parameter",
        "ref",
        "response",
        "security",
        "credential",
        "ref_sibling",
    ],
)
def test_invalid_export_is_rejected(problem):
    spec = generate_rapidapi_openapi()
    operation = spec["paths"]["/v1/sets/{public_id}"]["get"]
    if problem == "path":
        spec["paths"]["/admin"] = spec["paths"].pop("/health")
    elif problem == "method":
        spec["paths"]["/health"]["post"] = {}
    elif problem == "operation_id":
        operation["operationId"] = "invalid id"
    elif problem == "duplicate_id":
        operation["operationId"] = spec["paths"]["/health"]["get"]["operationId"]
    elif problem == "path_required":
        operation["parameters"][0]["required"] = False
    elif problem == "path_missing":
        operation["parameters"] = []
    elif problem == "duplicate_parameter":
        operation["parameters"].append(deepcopy(operation["parameters"][0]))
    elif problem == "ref":
        spec["components"]["schemas"]["Test"] = {"$ref": "#/components/schemas/Missing"}
    elif problem == "response":
        operation["responses"]["200"] = {"description": 42}
    elif problem == "security":
        spec["components"]["securitySchemes"] = {
            "consumer": {"type": "apiKey", "in": "header", "name": "X-RapidAPI-Key"}
        }
    elif problem == "credential":
        spec["info"]["description"] = "X-RapidAPI-Proxy-Secret"
    elif problem == "ref_sibling":
        spec["components"]["schemas"]["Test"] = {
            "$ref": "#/components/schemas/HealthResponse",
            "description": "ignored sibling",
        }
    with pytest.raises((ValueError, ValidationError)):
        validate_rapidapi_openapi(spec)


def test_duplicate_json_keys_and_duplicate_route_registrations_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        json.loads('{"paths": {"/health": {}, "/health": {}}}', object_pairs_hook=_unique_object)

    def duplicate_endpoint():
        return {}

    duplicate = APIRoute("/health", duplicate_endpoint, methods=["GET"])
    monkeypatch.setattr(app.router, "routes", [*app.routes, duplicate])
    with pytest.raises(ValueError, match="Duplicate public route"):
        generate_rapidapi_openapi()


def test_serialized_artifact_matches_export_and_is_written_independently_of_cwd(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "generated.json"
    write_rapidapi_openapi(target)
    loaded = json.loads(target.read_text(), object_pairs_hook=_unique_object)
    assert loaded == generate_rapidapi_openapi()
    assert loaded == json.loads(OUTPUT.read_text(), object_pairs_hook=_unique_object)
    assert OUTPUT.is_absolute()


def test_all_exported_schema_examples_validate():
    spec = generate_rapidapi_openapi()
    checked = 0

    def visit(schema):
        nonlocal checked
        if "example" in schema:
            OAS30Validator({**schema, "components": spec["components"]}).validate(schema["example"])
            checked += 1
        for child in schema.get("properties", {}).values():
            visit(child)
        for key in ("items", "additionalProperties", "not"):
            if isinstance(schema.get(key), dict):
                visit(schema[key])
        for key in ("anyOf", "allOf", "oneOf"):
            for child in schema.get(key, []):
                visit(child)

    for schema in spec["components"]["schemas"].values():
        visit(schema)
    assert checked == 78  # 63 converted arrays plus 15 existing singular examples.
