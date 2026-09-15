"""Fictional-only completeness, materialization, receipt and concurrency contracts."""

import copy
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from importer.execution_design.concurrency import lock_order, verify_fence
from importer.execution_design.materializer import PayloadContent
from importer.execution_design.preconditions import prepare_candidate
from importer.execution_design.receipt import (
    ExecutionReceipt,
    idempotency_key,
    previously_succeeded,
)
from importer.execution_design.snapshot import (
    FictionalMemoryReader,
    check_completeness,
    derive_scope,
)
from importer.projection.models import Approval, EntitySnapshot, Observation, Snapshot, frozen_plan
from importer.projection.planner import build_plan
from importer.schemas import ImportCatalogue
from tests.test_projection import context as projection_context

FIXTURE = Path(__file__).parent / "fixtures" / "execution-design-fictional.json"


@pytest.fixture
def context():
    ctx = projection_context.__wrapped__()
    fixture = json.loads(FIXTURE.read_text())
    ctx["snapshot"] = Snapshot.model_validate({"entities": [fixture["complete_existing_set"]]})
    for r in ctx["inputs"]:
        r["card"] = {
            f: {"state": "VALUE", "value": v} for f, v in fixture["complete_card_fields"].items()
        }
        r["keywords"] = {"state": "VALUE", "value": []}
        rarity = fixture["rarities"]["treatment" if r.get("kind") == "TREATMENT" else "printing"]
        r["rarity"] = {"official_label": {"state": "VALUE", "value": rarity}}
    return ctx


def approval(plan):
    return Approval(
        plan_hash=plan.plan_hash,
        approver_reference="fictional-reviewer",
        approved_at=datetime(2026, 2, 2, tzinfo=UTC),
        review_reference="fictional-review",
    )


def prepare(ctx, plan=None, reader=None, approved=None, **kwargs):
    plan = plan or build_plan(**ctx)
    args = {k: v for k, v in ctx.items() if k != "snapshot"}
    return prepare_candidate(
        plan,
        approved or approval(plan),
        reader or FictionalMemoryReader(ctx["snapshot"]),
        **args,
        **kwargs,
    )


def payload(result):
    assert result.technically_eligible, result.blocking_reasons
    return PayloadContent.model_validate_json(result.candidate.payload.content_json)


def current_context(ctx):
    materialized = payload(prepare(ctx))
    source = (
        build_plan(**ctx)
        .content.projection.entities[0]
        .source.model_copy(
            update={"revision": "fictional-1", "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC)}
        )
    )
    entities = []
    for full in materialized.entities:
        values = copy.deepcopy(full.values)
        values.pop("id", None)
        entities.append(
            EntitySnapshot(
                kind=full.kind,
                public_id=full.public_id,
                owner_id=full.owner_id,
                values=values,
                baseline={f: Observation(value=v, source=source) for f, v in values.items()},
            )
        )
    ctx["snapshot"] = Snapshot(entities=tuple(entities))
    return ctx


def card(snapshot):
    return next(e for e in snapshot.entities if e.kind == "cards")


class SuppliedReader:
    def __init__(self, envelope):
        self.envelope = envelope

    def read_snapshot(self, scope):
        return self.envelope


def test_complete_create_and_legacy_schema(context):
    result = prepare(context)
    data = payload(result)
    assert all(result.checks.values())
    assert not result.production_execution_authorized
    assert not result.approval_identity_authenticated
    assert "APPROVAL_NOT_AUTHENTICATED" in result.limitations
    assert not data.legacy_writer_safe
    for catalogue in data.catalogues:
        ImportCatalogue.model_validate(catalogue)
    assert any(c.operation == "CREATE" for c in data.approved_operations)


def test_deterministic_scope_and_target_changes(context):
    first = build_plan(**context)
    assert derive_scope(first) == derive_scope(first)
    context["inputs"] = context["inputs"][:1]
    assert derive_scope(build_plan(**context)).scope_hash != derive_scope(first).scope_hash


def test_complete_coverage_and_explicit_negative_observations(context):
    plan = build_plan(**context)
    scope = derive_scope(plan)
    observed = FictionalMemoryReader(context["snapshot"]).read_snapshot(scope)
    complete = check_completeness(scope, observed)
    assert complete.complete
    assert any(
        c.key.startswith("entity:cards:") and c.status == "PROVEN_ABSENT"
        for c in complete.components
    )
    assert any(
        c.key.startswith("numbers:") and c.status == "PROVEN_ABSENT" for c in complete.components
    )
    assert any(
        c.key.startswith("owner:variants:") and c.status == "PROVEN_ABSENT"
        for c in complete.components
    )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("missing", "INCOMPLETE_SNAPSHOT"),
        ("ambiguous", "AMBIGUOUS_ABSENCE"),
        ("not_exhaustive", "INCOMPLETE_SNAPSHOT"),
        ("duplicate", "AMBIGUOUS_ABSENCE"),
        ("false_presence", "AMBIGUOUS_ABSENCE"),
        ("wrong_hash", "AMBIGUOUS_ABSENCE"),
    ],
)
def test_missing_or_ambiguous_coverage_blocks(context, mutation, reason):
    plan = build_plan(**context)
    env = FictionalMemoryReader(context["snapshot"]).read_snapshot(derive_scope(plan))
    index = next(i for i, c in enumerate(env.coverage) if c.key.startswith("entity:cards:"))
    if mutation == "missing":
        env.coverage = env.coverage[:index] + env.coverage[index + 1 :]
    elif mutation == "duplicate":
        env.coverage = (*env.coverage, env.coverage[index])
    elif mutation == "ambiguous":
        env.coverage[index].status = "AMBIGUOUS"
    elif mutation == "not_exhaustive":
        env.coverage[index].exhaustive = False
    elif mutation == "false_presence":
        env.coverage[index].status = "PRESENT"
    else:
        env.coverage[index].value_hash = "0" * 64
    result = prepare(context, plan, SuppliedReader(env))
    assert reason in result.blocking_reasons
    assert result.candidate is None


def test_empty_collection_without_exhaustive_read_is_not_proof(context):
    plan = build_plan(**context)
    env = FictionalMemoryReader(context["snapshot"]).read_snapshot(derive_scope(plan))
    next(c for c in env.coverage if c.key.startswith("cards:")).exhaustive = False
    assert not prepare(context, plan, SuppliedReader(env)).technically_eligible


def test_capture_time_is_incidental(context):
    plan = build_plan(**context)
    reader = FictionalMemoryReader(context["snapshot"])
    first = reader.read_snapshot(derive_scope(plan))
    second = reader.read_snapshot(derive_scope(plan))
    second.captured_at = datetime(2027, 1, 1, tzinfo=UTC)
    assert first.semantic_hash == second.semantic_hash == plan.content.snapshot_hash
    assert first.content_hash == second.content_hash


def test_missing_full_fields_blocks_without_fabricating_defaults(context):
    context["snapshot"].entities[0].values.pop("logo_url")
    result = prepare(context)
    assert "INCOMPLETE_FIELDS" in result.blocking_reasons


def test_unknown_associations_are_not_proven_absent(context):
    current_context(context)
    card(context["snapshot"]).values["keywords"] = None
    result = prepare(context)
    assert "INCOMPLETE_ASSOCIATIONS" in result.blocking_reasons


def test_clean_update_and_carried_forward_state(context):
    current_context(context)
    for r in context["inputs"]:
        r["card"]["power"]["value"] = 5
    data = payload(prepare(context))
    full = next(e for e in data.entities if e.kind == "cards")
    assert full.values["power"] == 5
    assert full.origins["power"] == "APPROVED_MODIFICATION"
    assert full.origins["name"] == "CARRIED_FORWARD"
    assert {c.field for c in full.modifications} == {"power"}


def test_explicit_clear(context):
    context["inputs"] = context["inputs"][:1]
    current_context(context)
    context["inputs"][0]["card"]["power"] = {
        "state": "CLEAR",
        "approval_reference": "fictional-clear",
    }
    full = next(e for e in payload(prepare(context)).entities if e.kind == "cards")
    assert full.values["power"] is None
    assert full.modifications[0].operation == "CLEAR"
    assert full.modifications[0].approval_reference == "fictional-clear"


@pytest.mark.parametrize("state", ["ABSENT", "UNKNOWN"])
def test_skips_carry_existing_values_without_writes(context, state):
    context["inputs"] = context["inputs"][:1]
    current_context(context)
    context["inputs"][0]["card"]["power"] = {"state": state}
    data = payload(prepare(context))
    full = next(e for e in data.entities if e.kind == "cards")
    assert full.values["power"] == 3
    assert full.origins["power"] == "CARRIED_FORWARD"
    assert not full.modifications


def test_unchanged_is_not_modification(context):
    data = payload(prepare(current_context(context)))
    assert all(not e.modifications for e in data.entities)


def test_new_entity_missing_optional_value_is_explicit_compatibility_failure(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["card"].pop("artist")
    result = prepare(context)
    assert "LEGACY_SCHEMA_INCOMPATIBLE" in result.blocking_reasons


def test_new_entity_missing_required_value_is_blocked(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["card"].pop("name")
    assert not prepare(context).technically_eligible


def test_new_set_defaults_are_not_invented(context):
    context["snapshot"] = Snapshot()
    assert "LEGACY_SCHEMA_INCOMPATIBLE" in prepare(context).blocking_reasons


@pytest.mark.parametrize(
    "mutation", ["manual", "number", "card_owner", "variant_parent", "association"]
)
def test_fresh_state_drift_invalidates_approval(context, mutation):
    current_context(context)
    plan = build_plan(**context)
    fresh = context["snapshot"].model_copy(deep=True)
    if mutation == "manual":
        card(fresh).values["power"] = 9
    elif mutation == "number":
        card(fresh).values["number"] = "099/100"
    elif mutation == "card_owner":
        card(fresh).owner_id = "another_set"
    elif mutation == "variant_parent":
        next(e for e in fresh.entities if e.kind == "variants").owner_id = "another_card"
    else:
        card(fresh).values["keywords"] = [{"slug": "unexpected", "name": "Invented"}]
    result = prepare(context, plan, FictionalMemoryReader(fresh))
    assert "STATE_CHANGED" in result.blocking_reasons
    assert not result.technically_eligible


def test_occupied_number_added_after_approval_blocks(context):
    plan = build_plan(**context)
    occupied = current_context(copy.deepcopy(context))["snapshot"]
    assert (
        "STATE_CHANGED" in prepare(context, plan, FictionalMemoryReader(occupied)).blocking_reasons
    )


def test_plan_hash_and_approval_corruption(context):
    plan = build_plan(**context)
    broken = plan.model_copy(update={"plan_hash": "0" * 64})
    assert "PLAN_HASH_MISMATCH" in prepare(context, broken).blocking_reasons
    wrong = approval(plan).model_copy(update={"plan_hash": "0" * 64})
    assert "APPROVAL_MISMATCH" in prepare(context, plan, approved=wrong).blocking_reasons


def test_exact_operations_used_without_replanning(context, monkeypatch):
    plan = build_plan(**context)
    from importer.projection import planner, projector

    def forbidden(*args, **kwargs):
        raise AssertionError("Must not rebuild approved operations")

    monkeypatch.setattr(planner, "build_plan", forbidden)
    monkeypatch.setattr(projector, "project", forbidden)
    data = payload(prepare(context, plan))
    assert [c.model_dump() for c in data.approved_operations] == [
        c.model_dump() for c in plan.content.changes
    ]


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("id", "IDENTITY_REBIND"),
        ("number", "IDENTITY_REBIND"),
        ("parent", "RELATIONSHIP_CHANGED"),
        ("operation", "UNSUPPORTED_OPERATION"),
    ],
)
def test_malformed_approved_operation_graph_blocks(context, mutation, reason):
    current_context(context)
    plan = build_plan(**context)
    content = plan.content
    target = next(
        e
        for e in content.projection.entities
        if e.kind == ("variants" if mutation == "parent" else "cards")
    )
    if mutation == "id":
        target.importer_fields["id"] = "different_id"
    elif mutation == "number":
        target.importer_fields["number"] = "099/100"
    elif mutation == "parent":
        target.owner_id = "different_card"
    else:
        content.changes.append(content.changes[0])
    altered = frozen_plan(content, plan.created_at)
    assert reason in prepare(context, altered).blocking_reasons


def test_registry_and_policy_binding_preserved(context):
    plan = build_plan(**context)
    reader = FictionalMemoryReader(context["snapshot"], {"identity": "different"})
    assert "REGISTRY_CHANGED" in prepare(context, plan, reader).blocking_reasons
    context["planning_policy"].version = "changed"
    assert not prepare(context, plan).technically_eligible


def test_concurrent_change_and_read_context_fence(context):
    current_context(context)
    plan = build_plan(**context)
    reader = FictionalMemoryReader(context["snapshot"])
    candidate = prepare(context, plan, reader).candidate
    scope = derive_scope(plan)
    assert verify_fence(candidate, scope, reader.read_snapshot(scope)).unchanged
    changed = context["snapshot"].model_copy(deep=True)
    card(changed).values["power"] = 9
    reader.simulate_change(changed)
    result = verify_fence(candidate, scope, reader.read_snapshot(scope))
    assert "CONCURRENT_STATE_CHANGE" in result.reasons
    reader.simulate_change(context["snapshot"])
    assert (
        "READ_CONTEXT_CHANGED_REVALIDATION_REQUIRED"
        in verify_fence(candidate, scope, reader.read_snapshot(scope)).reasons
    )


def receipt(plan, outcome="SUCCESS"):
    return ExecutionReceipt(
        plan_hash=plan.plan_hash,
        destination_reference="fictional-local",
        idempotency_key=idempotency_key(plan.plan_hash, "fictional-local"),
        approval_reference="fictional-review",
        pre_state_hash=plan.content.snapshot_hash,
        post_state_hash="f" * 64 if outcome == "SUCCESS" else plan.content.snapshot_hash,
        operation_counts={"CREATE": 1},
        executed_at=datetime(2026, 2, 2, tzinfo=UTC),
        executor_authentication_reference="fictional-auth",
        transaction_reference="fictional-transaction",
        outcome=outcome,
        rolled_back=outcome == "FAILED",
        provenance_reference="fictional-provenance",
    )


def test_receipt_and_replay_contract(context):
    plan = build_plan(**context)
    item = receipt(plan)
    assert previously_succeeded(plan.plan_hash, "fictional-local", (item,))
    assert not previously_succeeded(plan.plan_hash, "other-fictional-context", (item,))
    assert "ALREADY_EXECUTED" in prepare(context, plan, receipts=(item,)).blocking_reasons
    assert idempotency_key(plan.plan_hash, "fictional-local") == item.idempotency_key


def test_atomic_rollback_receipt(context):
    plan = build_plan(**context)
    failed = receipt(plan, "FAILED")
    assert not previously_succeeded(plan.plan_hash, "fictional-local", (failed,))
    assert prepare(context, plan, receipts=(failed,)).technically_eligible
    bad = failed.model_dump()
    bad["post_state_hash"] = "b" * 64
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(bad)


def test_payload_determinism_and_freezing(context):
    first, second = prepare(context), prepare(context)
    assert first.candidate.payload == second.candidate.payload
    with pytest.raises(ValidationError):
        first.candidate.payload.content_json = "{}"
    scope = derive_scope(build_plan(**context))
    assert lock_order(scope) == tuple(sorted(set(lock_order(scope))))


def test_scope_or_reader_context_cannot_be_substituted(context):
    plan = build_plan(**context)
    env = FictionalMemoryReader(context["snapshot"]).read_snapshot(derive_scope(plan))
    env.scope_hash = "0" * 64
    assert "SNAPSHOT_SCOPE_MISMATCH" in prepare(context, plan, SuppliedReader(env)).blocking_reasons


def test_new_package_no_db_network_or_apply_imports(context, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    assert prepare(context).technically_eligible
    code = """
import sys
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'app' or fullname.startswith('sqlalchemy') or fullname in ('importer.runner', 'importer.planner'):
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Guard())
from importer.execution_design.preconditions import prepare_candidate
from importer.execution_design.snapshot import FictionalMemoryReader
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("field", ["payload", "plan_hash", "idempotency_key"])
def test_corrupted_candidate_cannot_pass_fence(context, field):
    plan = build_plan(**context)
    reader = FictionalMemoryReader(context["snapshot"])
    candidate = prepare(context, plan, reader).candidate
    replacement = (
        candidate.payload.model_copy(update={"content_json": "{}"})
        if field == "payload"
        else "0" * 64
    )
    candidate = candidate.model_copy(update={field: replacement})
    scope = derive_scope(plan)
    assert verify_fence(candidate, scope, reader.read_snapshot(scope)).reasons == (
        "INVALID_CANDIDATE",
    )


@pytest.mark.parametrize(
    "prefix", ["baseline:", "owner:", "variants:", "associations:", "registry"]
)
def test_every_inventory_requires_explicit_coverage(context, prefix):
    current_context(context)
    plan = build_plan(**context)
    envelope = FictionalMemoryReader(context["snapshot"]).read_snapshot(derive_scope(plan))
    removed = next(c.key for c in envelope.coverage if c.key.startswith(prefix))
    envelope.coverage = tuple(c for c in envelope.coverage if c.key != removed)
    assert (
        "INCOMPLETE_SNAPSHOT" in prepare(context, plan, SuppliedReader(envelope)).blocking_reasons
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("rolled_back", True),
        ("post_state_hash", None),
        ("provenance_reference", None),
        ("idempotency_key", "0" * 64),
    ],
)
def test_invalid_success_receipt_rejected(context, field, value):
    data = receipt(build_plan(**context)).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(data)
