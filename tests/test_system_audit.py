"""Whole-system contract and hardening regressions (fictional input only)."""

import json
from pathlib import Path

import pytest
from sqlalchemy import event

from app.main import app
from importer.runner import run_import
from tests.test_importer import snapshot

PATHS = {
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


def test_openapi_semantic_contract(client):
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.1")
    assert set(spec["paths"]) == PATHS

    def paths(routes):
        found = set()
        for route in routes:
            if hasattr(route, "path"):
                found.add(route.path)
            else:
                found.update(paths(route.effective_candidates()))
        return found

    assert paths(app.routes) == PATHS | {"/docs", "/redoc", "/openapi.json"}
    for operations in spec["paths"].values():
        assert set(operations) == {"get"}
        operation = operations["get"]
        assert operation["tags"] and "200" in operation["responses"]
        assert "500" in operation["responses"]
        assert "schema" in operation["responses"]["200"]["content"]["application/json"]
    forbidden = {
        "card_id",
        "set_id",
        "variant_id",
        "hosted_by_us",
        "source_name",
        "source_url",
        "entity_id",
        "content_hash",
    }
    for name, schema in spec["components"]["schemas"].items():
        assert not name.startswith(("Import", "SourceRecord"))
        assert not forbidden.intersection(schema.get("properties", {}))
        assert '"format": "uuid"' not in json.dumps(schema)
    params = {p["name"] for p in spec["paths"]["/v1/cards"]["get"]["parameters"]}
    assert {
        "set",
        "type",
        "keyword",
        "variant",
        "chakra_min",
        "power_max",
        "page",
        "limit",
        "sort",
        "order",
    } <= params


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path", ["/v1/cards", "/v1/cards/TEST-IMPORT-0", "/v1/sets", "/v1/keywords"]
)
def test_write_methods_do_not_mutate(client, db_session, method, path):
    engine = db_session.get_bind()
    before = snapshot(engine)
    assert client.request(method, path, json={"name": "Fictional"}).status_code == 405
    assert snapshot(engine) == before


def test_injected_failure_sanitizes_response_and_logs(client, monkeypatch, caplog):
    from app.services import card_service

    secret = "postgresql://user:secret-password@host/database token=secret-token"

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(card_service, "list_cards", fail)
    response = client.get("/v1/cards")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }
    assert "secret-password" not in caplog.text and "secret-token" not in caplog.text
    assert "RuntimeError" in caplog.text and "fail" in caplog.text


def test_set_summaries_exclude_variant_images_without_mutations(client, db_session):
    payload = json.loads(Path("data/examples/fictional-catalogue.json").read_text())
    engine = db_session.get_bind()
    assert run_import(engine, payload)["status"] == "success"
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/v1/sets/test-import-set-0/cards")
        assert response.status_code == 200
        card = response.json()["data"][0]
        assert len(card["images"]) == 1
        assert "card-0.png" in card["images"][0]["url"]
        assert "variants" not in card
        assert not any(
            s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_get_db_closes_on_exception(monkeypatch):
    from app import database

    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    dependency = database.get_db()
    assert next(dependency) is session
    with pytest.raises(RuntimeError):
        dependency.throw(RuntimeError("fictional failure"))
    assert session.closed


def test_import_validation_does_not_echo_image_tokens():
    payload = json.loads(Path("data/examples/fictional-catalogue.json").read_text())
    images = payload["sets"][0]["cards"][0]["images"]
    images[0]["url"] = "https://example.invalid/image?token=secret-token"
    images.append(dict(images[0]))
    result = run_import(None, payload)
    assert result["status"] == "failed"
    assert "secret-token" not in json.dumps(result)


def test_config_hides_database_credentials():
    from app.config import Settings

    config = Settings(DATABASE_URL="postgresql+psycopg://u:secret-password@localhost/db")
    assert "secret-password" not in repr(config)
    assert config.docs_enabled


def test_readiness_recovers_after_failed_request(client, monkeypatch):
    from app.api.v1 import ready

    class BrokenEngine:
        def connect(self):
            raise RuntimeError("secret-password")

    real = ready.engine
    monkeypatch.setattr(ready, "engine", BrokenEngine())
    response = client.get("/ready")
    assert response.status_code == 503 and "secret-password" not in response.text
    monkeypatch.setattr(ready, "engine", real)
    assert client.get("/health").status_code == 200


def test_docs_can_be_disabled_in_configured_process():
    import os
    import subprocess
    import sys

    env = dict(os.environ, DOCS_ENABLED="false")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import app; assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None and app.debug is False",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_invalid_cli_input_is_reported_without_database_config(tmp_path):
    import os
    import subprocess
    import sys

    file = tmp_path / "invalid.json"
    file.write_text('{"sets": []}')
    env = dict(os.environ, DATABASE_URL="", PYTHONPATH=str(Path.cwd()))
    completed = subprocess.run(
        [sys.executable, "-m", "importer.cli", str(file)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["status"] == "failed"
    assert report["errors"][0]["location"] == "source"
    assert "Traceback" not in completed.stderr
