"""Export a RapidAPI-compatible OpenAPI document for the canonical app."""

from __future__ import annotations

from copy import deepcopy

from app.main import app


def generate_rapidapi_openapi() -> dict:
    """Return the canonical FastAPI schema converted to OpenAPI 3.0.2.

    RapidAPI is stricter about the OpenAPI version than the app's canonical
    3.1 schema. This exporter preserves the app's route contract while
    rewriting the document to the supported 3.0.2 shape. The canonical app
    remains unchanged for local docs and documentation consumers.
    """
    schema = deepcopy(app.openapi())
    schema["openapi"] = "3.0.2"

    for path, methods in list(schema.get("paths", {}).items()):
        for method, operation in list(methods.items()):
            if not isinstance(operation, dict):
                continue
            if "responses" not in operation:
                continue

            for code, response in list(operation["responses"].items()):
                if not isinstance(response, dict):
                    continue

                content = response.get("content")
                if not isinstance(content, dict):
                    continue

                for media_type, media in list(content.items()):
                    if media_type != "application/json":
                        continue
                    payload = media.get("schema")
                    if not isinstance(payload, dict):
                        continue

                    # OpenAPI 3.0.x does not allow nullable in the same way as 3.1.
                    # The project's models already generate JSON-compatible schemas
                    # without using the 3.1-only `anyOf`/`nullable` semantics.
                    if payload.get("nullable") is True:
                        payload.pop("nullable", None)

                    if "$ref" in payload:
                        continue

                    if "allOf" in payload:
                        continue

    return schema


if __name__ == "__main__":
    import json
    from pathlib import Path

    output = Path("docs/generated/openapi.rapidapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate_rapidapi_openapi(), indent=2), encoding="utf-8")
    print(f"Wrote {output}")
