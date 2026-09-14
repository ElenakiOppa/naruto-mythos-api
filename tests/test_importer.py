"""Fictional importer validation, atomicity, and public contract regression."""

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import event, select

from app.models.keyword import card_keywords
from importer import runner
from importer.hashing import canonical_hash
from importer.planner import TABLES


@pytest.fixture
def payload():
    return json.loads(Path("data/examples/fictional-catalogue.json").read_text())


def snapshot(engine):
    with engine.connect() as conn:
        return {
            k: [dict(r) for r in conn.execute(select(t).order_by(t.c.id)).mappings()]
            for k, t in TABLES.items()
        }


def success(engine, payload, **kwargs):
    result = runner.run_import(engine, payload, **kwargs)
    assert result["status"] == "success", result["errors"]
    return result


@pytest.mark.parametrize("case", range(17))
def test_invalid_no_changes(db_session, payload, case):
    card = payload["sets"][0]["cards"][0]
    variant = card["variants"][0]
    if case == 0:
        payload = "{invalid"
    elif case == 1:
        del payload["source"]
    elif case == 2:
        del payload["source"]["retrieved_at"]
    elif case == 3:
        payload["sets"][0]["id"] = " "
    elif case == 4:
        payload["sets"].append(copy.deepcopy(payload["sets"][0]))
    elif case == 5:
        payload["sets"][1]["cards"][0]["id"] = card["id"]
    elif case == 6:
        card["variants"].append(copy.deepcopy(variant))
    elif case == 7:
        another = copy.deepcopy(card)
        another["id"] = "other"
        another["variants"] = []
        payload["sets"][0]["cards"].append(another)
    elif case == 8:
        card["chakra"] = -1
    elif case == 9:
        variant["serial_total"] = 0
    elif case == 10:
        card["images"][0]["width"] = 0
    elif case == 11:
        card["images"][0]["url"] = "not-a-url"
    elif case == 12:
        payload["sets"][1]["cards"][0]["keywords"][0]["name"] = "Conflict"
    elif case == 13:
        card["images"].append(copy.deepcopy(card["images"][0]))
    elif case == 14:
        card["number"] = 1
    elif case == 15:
        variant["serial_total"] = 10
    elif case == 16:
        payload = '{"sets":[],"sets":[]}'
    engine = db_session.get_bind()
    before = snapshot(engine)
    assert runner.run_import(engine, payload)["status"] == "failed"
    assert snapshot(engine) == before


def test_dry_run_idempotency_updates_sources_and_omission(db_session, payload):
    engine = db_session.get_bind()
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    before = snapshot(engine)
    a = success(engine, payload, dry_run=True)
    b = success(engine, payload, dry_run=True)
    assert a["plan"] == b["plan"]
    assert snapshot(engine) == before
    assert not any(
        s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements
    )
    event.remove(engine, "before_cursor_execute", capture)
    first = success(engine, payload)
    assert first["counts"]["provenance"]["created"] == 11
    original = snapshot(engine)
    repeat = success(engine, payload)
    assert all(
        group.get("created", 0) == group.get("updated", 0) == 0
        for group in repeat["counts"].values()
    )
    assert snapshot(engine) == original
    payload["sets"][0]["cards"][0]["name"] = "Fictional Updated"
    dry = success(engine, payload, dry_run=True)
    assert dry["counts"]["cards"]["updated"] == 1
    assert dry["counts"]["sets"]["updated"] == 0
    assert dry["counts"]["provenance"]["updated"] == 1
    assert snapshot(engine) == original
    success(engine, payload)
    updated = snapshot(engine)
    assert {r["id"] for r in original["cards"]} == {r["id"] for r in updated["cards"]}
    payload["source"]["retrieved_at"] = "2026-09-14T12:00:00Z"
    success(engine, payload)
    later = snapshot(engine)
    for old in updated["provenance"]:
        new = next(r for r in later["provenance"] if r["id"] == old["id"])
        assert new["first_seen_at"] == old["first_seen_at"]
        assert new["last_seen_at"] > old["last_seen_at"]
        assert new["content_hash"] == old["content_hash"]
    payload["source"]["name"] = "fictional-second-source"
    assert success(engine, payload)["counts"]["provenance"]["created"] == 11
    assert len(snapshot(engine)["provenance"]) == 22
    payload["sets"] = payload["sets"][:1]
    card = payload["sets"][0]["cards"][0]
    card.pop("keywords")
    card["variants"] = []
    card["images"] = []
    success(engine, payload)
    assert len(snapshot(engine)["cards"]) == 2
    assert len(snapshot(engine)["variants"]) == 2
    assert len(snapshot(engine)["images"]) == 4
    card["keywords"] = []
    result = success(engine, payload)
    assert result["counts"]["relationships"]["removed"] == 1
    assert len(snapshot(engine)["keywords"]) == 1
    with engine.connect() as conn:
        assert len(conn.execute(select(card_keywords)).all()) == 1


def test_rollback(db_session, payload, monkeypatch):
    engine = db_session.get_bind()
    before = snapshot(engine)
    real = runner.apply_plan

    def fail(conn, plan):
        real(conn, plan)
        raise RuntimeError("secret should never appear")

    monkeypatch.setattr(runner, "apply_plan", fail)
    result = runner.run_import(engine, payload)
    assert result["transaction"] == "rolled_back"
    assert "secret" not in json.dumps(result)
    assert snapshot(engine) == before


def test_ownership_and_number_conflict(db_session, payload):
    engine = db_session.get_bind()
    success(engine, payload)
    before = snapshot(engine)
    moved = copy.deepcopy(payload)
    moved["sets"][0]["cards"][0]["id"] = "NEW-CARD"
    assert runner.run_import(engine, moved)["status"] == "failed"
    moved = copy.deepcopy(payload)
    moved["sets"][0]["cards"], moved["sets"][1]["cards"] = (
        moved["sets"][1]["cards"],
        moved["sets"][0]["cards"],
    )
    assert runner.run_import(engine, moved)["status"] == "failed"
    assert snapshot(engine) == before


def test_hash_and_normalization(payload):
    from importer.schemas import parse_catalogue

    assert canonical_hash({"a": None, "b": "Ã©"}) == canonical_hash({"b": "Ã©", "a": None})
    payload["sets"][0]["cards"][0]["name"] = " Fictional Name "
    payload["sets"][0]["cards"][0]["subtitle"] = " "
    data = parse_catalogue(payload)
    assert data.sets[0].cards[0].name == "Fictional Name"
    assert data.sets[0].cards[0].subtitle is None
    assert data.sets[0].cards[0].number == "001"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/sets",
        "/v1/sets/test-import-set-0",
        "/v1/sets/test-import-set-0/cards",
        "/v1/cards",
        "/v1/cards/TEST-IMPORT-0",
        "/v1/cards/random",
        "/v1/rarities",
        "/v1/keywords",
        "/v1/keywords/test-import-keyword/cards",
        "/v1/search?q=Fictional",
    ],
)
def test_imported_public_api(db_session, client, payload, path):
    success(db_session.get_bind(), payload)
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert "source_records" not in response.text
    assert "content_hash" not in response.text


def test_variant_images_and_aliases(db_session, payload):
    success(db_session.get_bind(), payload)
    data = snapshot(db_session.get_bind())
    assert {v["variant_type"] for v in data["variants"]} == {"holographic", "experimental-unknown"}
    assert sum(i["variant_id"] is not None for i in data["images"]) == 2
    assert all(i["hosted_by_us"] is False for i in data["images"])
    assert any(v["serial_total"] == 100 and v["serial_numbered"] for v in data["variants"])


def test_cli_validation_report(tmp_path, capsys):
    from importer.cli import main

    source = tmp_path / "invalid.json"
    report = tmp_path / "report.json"
    source.write_text('{"sets": []}', encoding="utf-8")
    assert main([str(source), "--report", str(report)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["validation"]["valid"] is False
    assert any(e["location"] == "source" for e in data["errors"])
    assert json.loads(report.read_text()) == data
    original = source.read_text()
    assert main([str(source), "--report", str(source)]) == 1
    assert source.read_text() == original


def test_schema_matches_models():
    from importer.schemas import ImportCatalogue

    assert (
        json.loads(Path("data/schema/catalogue.schema.json").read_text())
        == ImportCatalogue.model_json_schema()
    )
