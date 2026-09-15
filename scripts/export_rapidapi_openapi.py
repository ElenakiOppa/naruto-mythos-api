"""Convert and validate a public OpenAPI 3.0.2 export without changing the app."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import routing
from openapi_spec_validator import OpenAPIV30SpecValidator

from app.main import app

OUTPUT = Path(__file__).resolve().parents[1] / "docs/generated/openapi.rapidapi.json"
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/ready",
        "/v1/sets",
        "/v1/sets/{public_id}",
        "/v1/sets/{public_id}/cards",
        "/v1/cards",
        "/v1/cards/random",
        "/v1/cards/{public_id}",
        "/v1/rarities",
        "/v1/keywords",
        "/v1/keywords/{slug}/cards",
        "/v1/search",
    }
)
METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
SCHEMA_KEYS = frozenset(
    {
        "title",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "maxLength",
        "minLength",
        "pattern",
        "maxItems",
        "minItems",
        "uniqueItems",
        "maxProperties",
        "minProperties",
        "required",
        "enum",
        "type",
        "allOf",
        "oneOf",
        "anyOf",
        "not",
        "items",
        "properties",
        "additionalProperties",
        "description",
        "format",
        "default",
        "nullable",
        "discriminator",
        "readOnly",
        "writeOnly",
        "xml",
        "externalDocs",
        "example",
        "deprecated",
        "$ref",
    }
)
ANNOTATIONS = frozenset(
    {
        "title",
        "description",
        "default",
        "example",
        "deprecated",
        "readOnly",
        "writeOnly",
        "externalDocs",
    }
)


def _normalize_schema(node: Any) -> dict[str, Any]:
    """Convert Schema Objects only, never instance/example data.

    Unsupported validation keywords fail closed instead of silently weakening a
    future contract. This converts the app's schemas, not arbitrary JSON Schema.
    """
    if isinstance(node, bool):
        return {} if node else {"not": {}}
    if not isinstance(node, dict):
        raise TypeError("Expected a Schema Object")
    result = deepcopy(node)
    result.pop("$schema", None)
    result.pop("$comment", None)
    if "examples" in result:
        examples = result.pop("examples")
        if not isinstance(examples, list):
            raise ValueError("Schema examples must be an array")
        if examples and "example" not in result:
            result["example"] = examples[0]
    if "const" in result:
        value = result.pop("const")
        if "enum" in result and value not in result["enum"]:
            raise ValueError("Conflicting const and enum")
        result["enum"] = [value]
        if value is None and "type" not in result:
            result.update(type="string", nullable=True)

    for exclusive, inclusive, choose in (
        ("exclusiveMinimum", "minimum", max),
        ("exclusiveMaximum", "maximum", min),
    ):
        bound = result.get(exclusive)
        if isinstance(bound, (int, float)) and not isinstance(bound, bool):
            effective = choose(result.get(inclusive, bound), bound)
            result[inclusive] = effective
            result[exclusive] = effective == bound

    schema_type = result.get("type")
    if isinstance(schema_type, list):
        if not schema_type or len(set(schema_type)) != len(schema_type):
            raise ValueError("Invalid type array")
        result.pop("type")
        union = {"anyOf": [_normalize_schema({"type": item}) for item in schema_type]}
        # Keep existing union constraints conjunctive.
        result.setdefault("allOf", []).append(union)
    elif schema_type == "null":
        result["type"] = "string"
        result["nullable"] = True
        if "enum" in result and None not in result["enum"]:
            raise ValueError("Null type conflicts with enum")
        result["enum"] = [None]

    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword not in result:
            continue
        branches = result[keyword]
        # Recognize actual null BEFORE conversion. An empty schema accepts any value.
        nulls = [branch for branch in branches if branch == {"type": "null"}]
        others = [branch for branch in branches if branch != {"type": "null"}]
        outer_keys = set(result) - {keyword}
        if (
            keyword in {"anyOf", "oneOf"}
            and len(nulls) == 1
            and len(others) == 1
            and outer_keys <= ANNOTATIONS
        ):
            primary = _normalize_schema(others[0])
            if (
                isinstance(primary.get("type"), str)
                and not any(k in primary for k in ("$ref", "anyOf", "oneOf", "allOf", "not"))
                and not primary.get("nullable")
            ):
                primary["nullable"] = True
                if "enum" in primary and None not in primary["enum"]:
                    primary["enum"].append(None)
                primary.update({k: v for k, v in result.items() if k != keyword})
                return primary
        result[keyword] = [_normalize_schema(branch) for branch in branches]

    if "properties" in result:
        result["properties"] = {
            name: _normalize_schema(value) for name, value in result["properties"].items()
        }
    for keyword in ("items", "not", "additionalProperties"):
        if keyword in result:
            if keyword == "additionalProperties" and isinstance(result[keyword], bool):
                continue
            result[keyword] = _normalize_schema(result[keyword])

    unknown = set(result) - SCHEMA_KEYS
    if any(not key.startswith("x-") for key in unknown):
        raise ValueError(f"Unsupported OpenAPI 3.0 schema keywords: {sorted(unknown)}")
    if "$ref" in result and len(result) > 1:
        # 3.0 Reference Objects ignore siblings. allOf preserves their meaning.
        ref = result.pop("$ref")
        result.setdefault("allOf", []).insert(0, {"$ref": ref})
    return result


def _convert_document(node: Any, location: tuple[str, ...] = ()) -> Any:
    """Visit OpenAPI structure, stopping at schemas and opaque instance values."""
    if isinstance(node, list):
        return [_convert_document(item, location) for item in node]
    if not isinstance(node, dict):
        return deepcopy(node)
    result = {}
    for key, value in node.items():
        if location == ("components", "schemas") or key == "schema":
            result[key] = _normalize_schema(value)
        elif key in {"example", "examples", "default", "enum", "value"} or key.startswith("x-"):
            result[key] = deepcopy(value)
        elif key == "jsonSchemaDialect" and not location:
            continue
        else:
            result[key] = _convert_document(value, (*location, key))
    return result


def _resolve(document: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/components/"):
        raise ValueError(f"Only local component references are supported: {ref}")
    value: Any = document
    try:
        for part in ref[2:].split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Unresolved component reference: {ref}") from exc
    return value


def validate_rapidapi_openapi(document: dict[str, Any]) -> None:
    """Validate OAS 3.0 and the fixed public export boundary before writing."""
    if document.get("openapi") != "3.0.2":
        raise ValueError("RapidAPI export must use OpenAPI 3.0.2")
    if set(document.get("paths", {})) != PUBLIC_PATHS:
        raise ValueError("The existing 12 public paths must be preserved")
    encoded = json.dumps(document, allow_nan=False).lower()
    if any(name in encoded for name in ("rapidapi_proxy_secret", "x-rapidapi-proxy-secret")):
        raise ValueError("Origin proxy credentials must not be documented")
    if document.get("security") or document.get("components", {}).get("securitySchemes"):
        raise ValueError("The public export must not add origin security schemes")

    operation_ids = set()
    for path, item in document["paths"].items():
        if set(item) & METHODS != {"get"}:
            raise ValueError(f"Only the existing GET operation is allowed: {path}")
        operation = item["get"]
        operation_id = operation.get("operationId", "")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", operation_id):
            raise ValueError(f"Invalid operationId on {path}")
        if operation_id in operation_ids:
            raise ValueError(f"Duplicate operationId: {operation_id}")
        operation_ids.add(operation_id)
        if operation.get("security") or operation.get("callbacks") or operation.get("requestBody"):
            raise ValueError(f"Unexpected public GET contract on {path}")
        parameters = {}
        for scope in (item.get("parameters", []), operation.get("parameters", [])):
            seen = set()
            for parameter in scope:
                if "$ref" in parameter:
                    parameter = _resolve(document, parameter["$ref"])
                identity = (parameter["in"], parameter["name"])
                if identity in seen:
                    raise ValueError(f"Duplicate parameter on {path}: {identity}")
                seen.add(identity)
                parameters[identity] = parameter
        declared = {name for (kind, name) in parameters if kind == "path"}
        if declared != set(re.findall(r"\{([^{}]+)\}", path)):
            raise ValueError(f"Path parameter declarations do not match {path}")
        if any(not parameters[("path", name)].get("required") for name in declared):
            raise ValueError(f"Path parameters must be required: {path}")

    def check_refs(value: Any) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                _resolve(document, value["$ref"])
                if len(value) > 1:
                    raise ValueError("OpenAPI 3.0 Reference Objects cannot have siblings")
            for key, child in value.items():
                if key not in {"example", "examples", "default", "enum"} and not key.startswith(
                    "x-"
                ):
                    check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)

    check_refs(document)
    OpenAPIV30SpecValidator(document).validate()


def generate_rapidapi_openapi() -> dict[str, Any]:
    """Export a detached schema; leave routes, security and cached schema intact."""
    # Recent FastAPI versions retain included routers; use the same flattened
    # contexts as its OpenAPI generator, with support for older flat route lists.
    iter_contexts: Any = getattr(routing, "iter_route_contexts", iter)
    routes = [
        (route.path_format, method.lower())
        for route in iter_contexts(app.routes)
        if isinstance(getattr(route, "original_route", route), routing.APIRoute)
        and route.include_in_schema
        for method in (route.methods or set())
    ]
    if len(routes) != len(set(routes)):
        raise ValueError("Duplicate public route registration")
    if set(routes) != {(path, "get") for path in PUBLIC_PATHS}:
        raise ValueError("Unexpected public route registration")
    schema = _convert_document(app.openapi())
    schema["openapi"] = "3.0.2"
    validate_rapidapi_openapi(schema)
    return schema


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def write_rapidapi_openapi(output: Path = OUTPUT) -> Path:
    payload = json.dumps(generate_rapidapi_openapi(), indent=2, allow_nan=False) + "\n"
    validate_rapidapi_openapi(json.loads(payload, object_pairs_hook=_unique_object))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    return output


if __name__ == "__main__":
    print(f"Wrote and validated {write_rapidapi_openapi()}")
