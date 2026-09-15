"""Export a RapidAPI-compatible OpenAPI document for the canonical app."""

from __future__ import annotations

from copy import deepcopy

from app.main import app


def _is_legal_content_examples(value):
    if not isinstance(value, dict):
        return False
    if not value:
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("value"), (dict, list, str, int, float, bool, type(None)))
        for item in value.values()
    )


def _normalize_schema(node):
    """Recursively convert canonical OpenAPI 3.1 constructs to RapidAPI-safe 3.0.2."""
    if isinstance(node, dict):
        converted = {}
        for key, value in node.items():
            if key == "type" and value == "null":
                continue

            if key == "const":
                if "enum" not in node:
                    converted["enum"] = [value]
                continue

            if key == "examples":
                if isinstance(value, list):
                    if value:
                        converted["example"] = _normalize_schema(value[0])
                    continue
                if isinstance(value, dict) and not _is_legal_content_examples(value):
                    if value:
                        first = next(iter(value.values()))
                        converted["example"] = _normalize_schema(first)
                    continue

            converted[key] = _normalize_schema(value)

        if isinstance(converted.get("anyOf"), list):
            non_null = []
            null_present = False
            for item in converted["anyOf"]:
                if isinstance(item, dict) and not item:
                    null_present = True
                    continue
                if isinstance(item, dict) and item.get("type") == "null":
                    null_present = True
                    continue
                non_null.append(item)

            if null_present:
                converted["nullable"] = True
                if len(non_null) == 1:
                    primary = non_null[0]
                    merged = {k: v for k, v in converted.items() if k != "anyOf"}
                    if isinstance(primary, dict):
                        for nested_key, nested_value in primary.items():
                            if nested_key not in merged:
                                merged[nested_key] = nested_value
                    return merged
                if len(non_null) > 1:
                    converted["anyOf"] = non_null
                    return converted
                converted.pop("anyOf", None)
                return converted

        return converted

    if isinstance(node, list):
        return [_normalize_schema(item) for item in node]

    return node


def generate_rapidapi_openapi() -> dict:
    """Return the canonical FastAPI schema converted to OpenAPI 3.0.2.

    RapidAPI is stricter about the OpenAPI version than the app's canonical
    3.1 schema. This exporter preserves the app's route contract while
    rewriting the document to the supported 3.0.2 shape. The canonical app
    remains unchanged for local docs and documentation consumers.
    """
    schema = deepcopy(app.openapi())
    schema = _normalize_schema(schema)
    schema["openapi"] = "3.0.2"
    return schema


if __name__ == "__main__":
    import json
    from pathlib import Path

    output = Path("docs/generated/openapi.rapidapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate_rapidapi_openapi(), indent=2), encoding="utf-8")
    print(f"Wrote {output}")
