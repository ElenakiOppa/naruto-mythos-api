"""Focused command tests: mocked acquisition/configuration and fictional SQLite only."""

import copy
import hashlib
import json
from dataclasses import asdict
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from importer.catalogue_importer import _build_plan
from importer.catalogue_persistence import count_catalogue
from scripts import import_catalogue as command
from tests.test_catalogue_persistence import record


@pytest.fixture
def approved(monkeypatch):
    plan = {
        "cards": [{} for _ in range(318)],
        "printings": [
            {"identity": {"expansion": expansion}}
            for expansion, count in command.EXPECTED_SETS.items()
            for _ in range(count)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    monkeypatch.setattr(command, "PLAN_SHA256", digest)
    return {
        "plan": plan,
        "report": {
            **command.EXPECTED_REPORT,
            "plan_sha256": digest,
            "identity_collision_count": 0,
            "quarantined_records": {},
        },
    }


def test_production_guards_are_exact():
    assert command.PLAN_SHA256 == "2a209a10ab4a59c25a2730f991ac4a3978fd0758e7e232a0d1d94815cb34a091"
    assert command.EXPECTED_COUNTS == {
        "sets": 2,
        "cards": 318,
        "printings": 636,
        "translations": 2544,
        "provenance": 2544,
        "image_references": 2544,
        "keywords": 46,
        "associations": 701,
    }


@pytest.mark.parametrize("field", list(command.EXPECTED_REPORT))
def test_every_report_drift_aborts_before_engine(approved, monkeypatch, field):
    approved["report"][field] += 1
    monkeypatch.setattr(command, "acquire_one", lambda *a: {"http_status": 200, "sha256": "hash"})
    monkeypatch.setattr(command, "build_dry_run", lambda root: approved)
    engine = Mock()
    monkeypatch.setattr(command, "configured_engine", engine)
    assert command.main() == 1
    engine.assert_not_called()


@pytest.mark.parametrize("mutation", ["hash", "plan", "sets", "cards", "quarantine", "collision"])
def test_plan_tampering_rejected(approved, monkeypatch, mutation):
    altered = copy.deepcopy(approved)
    if mutation == "hash":
        altered["report"]["plan_sha256"] = "0" * 64
    elif mutation == "plan":
        altered["plan"]["extra"] = True
    elif mutation == "sets":
        altered["plan"]["printings"][0]["identity"]["expansion"] = "Fictional drift"
    elif mutation == "cards":
        altered["plan"]["cards"].pop()
    elif mutation == "quarantine":
        altered["report"]["quarantined_records"] = {"fictional": "conflict"}
    else:
        altered["report"]["identity_collision_count"] = 1
    if mutation in ("sets", "cards"):
        digest = hashlib.sha256(
            json.dumps(
                altered["plan"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        monkeypatch.setattr(command, "PLAN_SHA256", digest)
        altered["report"]["plan_sha256"] = digest
    with pytest.raises(command.ImportRefused, match="SOURCE_DRIFT"):
        command.validate_plan(altered)


def test_only_api_sources_and_fresh_temporary_snapshot(approved, monkeypatch):
    calls = []

    def acquire(source, raw, manifest, observations):
        calls.append((source, raw.parent))
        return {"http_status": 200, "sha256": "hash"}

    monkeypatch.setattr(command, "acquire_one", acquire)
    monkeypatch.setattr(command, "build_dry_run", lambda root: approved)
    assert command.acquire_plan() == approved
    assert [c[0] for c in calls] == list(command.APPROVED_API_SOURCES)
    assert len(calls) == 4
    assert all(not c[1].exists() for c in calls)


def test_failed_fetch_cannot_use_stale_snapshot(monkeypatch, capsys):
    monkeypatch.setattr(
        command, "acquire_one", lambda *a: {"http_status": 503, "error": "sensitive"}
    )
    build, engine = Mock(), Mock()
    monkeypatch.setattr(command, "build_dry_run", build)
    monkeypatch.setattr(command, "configured_engine", engine)
    assert command.main() == 1
    build.assert_not_called()
    engine.assert_not_called()
    assert capsys.readouterr().err.strip() == "SOURCE_DRIFT"


@pytest.fixture
def fictional_execution(db_session, monkeypatch):
    plan, report = _build_plan(
        {
            "en": [
                record(1),
                record(2),
                record(3, CardType="Mission", Power="", Chakra="", Points="2"),
            ]
        }
    )
    monkeypatch.setattr(
        command,
        "EXPECTED_COUNTS",
        {
            "sets": 1,
            "cards": 3,
            "printings": 3,
            "translations": 3,
            "provenance": 3,
            "image_references": 3,
            "keywords": 2,
            "associations": 6,
        },
    )
    # SQLite's deferred BEGIN differs from PostgreSQL; explicitly begin to test
    # the real outer-transaction/savepoint rollback contract with the unchanged helper.
    monkeypatch.setattr(command, "lock_catalogue", lambda c: c.execute(text("BEGIN")))
    return db_session.get_bind(), {"plan": plan, "report": report}


def test_commit_gameplay_and_refuse_nonempty_repeat(fictional_execution):
    engine, result = fictional_execution
    command.execute_import(engine, result)
    with Session(engine) as session:
        assert asdict(count_catalogue(session)) == command.EXPECTED_COUNTS
    with pytest.raises(command.ImportRefused, match="CATALOGUE_NOT_EMPTY"):
        command.execute_import(engine, result)


@pytest.mark.parametrize("failure", ["counts", "gameplay", "persistence"])
def test_any_precommit_failure_rolls_back_helper_writes(fictional_execution, monkeypatch, failure):
    engine, result = fictional_execution
    if failure == "counts":
        monkeypatch.setitem(command.EXPECTED_COUNTS, "cards", 4)
    elif failure == "gameplay":
        original = command.verify_catalogue

        def bad_gameplay(session, data):
            session.execute(text("UPDATE cards SET power=0 WHERE power=-1"))
            original(session, data)

        monkeypatch.setattr(command, "verify_catalogue", bad_gameplay)
    else:
        from importer import catalogue_persistence

        original = catalogue_persistence.persist_catalogue_plan

        def fail(session, data):
            original(session, data)
            raise RuntimeError("fictional failure after helper commit")

        monkeypatch.setattr(catalogue_persistence, "persist_catalogue_plan", fail)
    with pytest.raises(RuntimeError):
        command.execute_import(engine, result)
    with Session(engine) as session:
        assert not any(asdict(count_catalogue(session)).values())


def test_postcommit_error_is_distinct(fictional_execution, monkeypatch):
    engine, result = fictional_execution
    original = command.verify_catalogue
    calls = 0

    def verify(session, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fictional read outage")
        original(session, data)

    monkeypatch.setattr(command, "verify_catalogue", verify)
    with pytest.raises(command.ImportRefused, match="POST_COMMIT_VERIFICATION_FAILED"):
        command.execute_import(engine, result)
    with Session(engine) as session:
        assert asdict(count_catalogue(session)) == command.EXPECTED_COUNTS


def test_main_suppresses_sensitive_errors_and_disposes(monkeypatch, capsys):
    monkeypatch.setattr(command, "acquire_plan", dict)
    engine = Mock()
    monkeypatch.setattr(command, "configured_engine", lambda: engine)
    monkeypatch.setattr(
        command, "execute_import", Mock(side_effect=RuntimeError("secret connection string"))
    )
    assert command.main() == 1
    assert capsys.readouterr().err.strip() == "IMPORT_FAILED"
    engine.dispose.assert_called_once()


def test_configuration_disables_dotenv(monkeypatch):
    from app import config, database

    monkeypatch.setattr(config.Settings, "model_config", dict(config.Settings.model_config))

    def settings():
        assert config.Settings.model_config["env_file"] is None

    monkeypatch.setattr(config, "get_settings", settings)
    assert command.configured_engine() is database.engine
