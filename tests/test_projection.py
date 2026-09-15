"""Fictional-only projection and exact-plan binding tests, without a database."""

import ast
import copy
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from importer.projection.approval import verify_approval
from importer.projection.canonical import digest, encode
from importer.projection.models import (
    Approval,
    Plan,
    PlanningPolicy,
    ProjectionPolicy,
    Snapshot,
    frozen_plan,
)
from importer.projection.planner import build_plan
from importer.projection.projector import project
from importer.schemas import ImportCard, ImportSet, ImportVariant
from importer.staging.identity import Registry
from importer.staging.models import Policy

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def context():
    staging = json.loads((FIXTURES / "staging-fictional.json").read_text())
    fixture = json.loads((FIXTURES / "projection-fictional.json").read_text())
    records = [staging["records"][0], staging["records"][-1]]
    for r in records:
        r["source"].update(revision="fictional-2", retrieved_at="2026-02-01T00:00:00Z")
    return {
        "inputs": records,
        "staging_policy": Policy.model_validate(staging["policy"]),
        "projection_policy": ProjectionPolicy.model_validate(fixture["projection_policy"]),
        "snapshot": Snapshot(),
        "planning_policy": PlanningPolicy.model_validate(fixture["planning_policy"]),
    }


def projection(ctx):
    return project(ctx["inputs"], ctx["staging_policy"], ctx["projection_policy"])


def plan(ctx):
    return build_plan(**ctx)


def change(result, field="power", kind="cards"):
    return next(c for c in result.content.changes if c.kind == kind and c.field == field)


def with_snapshot(ctx):
    entities = []
    for e in projection(ctx).entities:
        values = copy.deepcopy(e.importer_fields)
        values.pop("id", None)
        for f in e.fields:
            if f != "images":
                values.setdefault(f, [] if f == "keywords" else None)
        source = e.source.model_dump(mode="json")
        source.update(revision="fictional-1", retrieved_at="2026-01-01T00:00:00Z")
        entities.append(
            {
                "kind": e.kind,
                "public_id": e.public_id,
                "owner_id": e.owner_id,
                "values": values,
                "baseline": {f: {"value": v, "source": source} for f, v in values.items()},
            }
        )
    ctx["snapshot"] = Snapshot.model_validate({"entities": entities})
    return ctx


def snapshot_card(ctx):
    return next(e for e in ctx["snapshot"].entities if e.kind == "cards")


def approved(result):
    return Approval(
        plan_hash=result.plan_hash,
        approver_reference="fictional-reviewer",
        approved_at=datetime(2026, 2, 2, tzinfo=UTC),
        review_reference="fictional-review",
    )


def verify(result, ctx, approval=None):
    return verify_approval(result, approval or approved(result), **ctx)


def test_safe_projection_and_importer_compatible_fragments(context):
    result = projection(context)
    assert result.rejected == []
    assert len(result.entities) == 3
    models = {"sets": ImportSet, "cards": ImportCard, "variants": ImportVariant}
    for e in result.entities:
        models[e.kind].model_validate(e.importer_fields)
    assert result == projection(context)


@pytest.mark.parametrize("field", ["mission_points", "mission_rank"])
def test_unsupported_mission_fields_reject(context, field):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["card"][field] = None
    assert "UNSUPPORTED_MISSION_FIELDS" in {n.code for n in projection(context).rejected}


@pytest.mark.parametrize(
    "case,code",
    [
        ("namespace", "UNMAPPED_PRINTING_SCOPE_OR_NAMESPACE"),
        ("territory", "UNSUPPORTED_TERRITORY"),
        ("availability", "UNSUPPORTED_AVAILABILITY"),
        ("images", "IMAGE_REVIEW_REQUIRED"),
        ("rarity", "UNSUPPORTED_RARITY_DIMENSION"),
        ("serialization", "UNKNOWN_SERIALIZATION"),
        ("unreviewed", "UNRESOLVED_REVIEW"),
    ],
)
def test_unsupported_dimensions(context, case, code):
    r = context["inputs"][0]
    if case == "namespace":
        context["inputs"] = [r]
        r["identity"]["numbering_namespace"] = "MISSION"
    elif case == "territory":
        context["inputs"] = [r]
        r["identity"]["scope"]["territory"] = "island"
        context["staging_policy"].approved_scopes.append(
            context["staging_policy"].approved_scopes[0].model_copy(update={"territory": "island"})
        )
    elif case == "availability":
        r["availability"] = {"state": "VALUE", "value": []}
    elif case == "images":
        r["images"] = {"state": "VALUE", "value": []}
    elif case == "rarity":
        r["rarity"] = {"abbreviation": {"state": "VALUE", "value": "RX"}}
    elif case == "serialization":
        context["inputs"][-1]["treatment"].update(serial_numbered=None, serial_total=None)
    else:
        r["review_status"] = "UNREVIEWED"
    result = plan(context)
    assert code in {n.code for n in result.content.projection.rejected}
    assert not result.approval_eligible


def test_explicit_namespace_mapping(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["identity"]["numbering_namespace"] = "MISSION"
    p = context["projection_policy"].model_dump()
    mapping = copy.deepcopy(p["mappings"][0])
    mapping.update(namespace="MISSION", set_id="set_ember_missions")
    p["mappings"] = [*p["mappings"], mapping]
    context["projection_policy"] = ProjectionPolicy.model_validate(p)
    assert projection(context).rejected == []


def test_mapping_cannot_collapse_scopes(context):
    p = context["projection_policy"].model_dump()
    p["mappings"][1]["set_id"] = p["mappings"][0]["set_id"]
    with pytest.raises(ValidationError):
        ProjectionPolicy.model_validate(p)


def test_absent_and_unknown_skip(context):
    result = plan(with_snapshot(context))
    assert change(result, "artist").operation == "SKIP"
    assert change(result, "artist").reason == "ABSENT"
    assert change(result, "subtitle").operation == "SKIP"
    assert change(result, "subtitle").reason == "UNKNOWN"
    card = next(e for e in result.content.projection.entities if e.kind == "cards")
    assert "artist" not in card.importer_fields and "subtitle" not in card.importer_fields


def test_clean_create(context):
    result = plan(context)
    assert change(result).operation == "CREATE"
    assert result.approval_eligible
    assert result.content.expected_entity_counts == {"cards": 1, "sets": 1, "variants": 1}


def test_clean_update(context):
    with_snapshot(context)
    card = snapshot_card(context)
    card.values["power"] = card.baseline["power"].value = 2
    result = plan(context)
    assert change(result).operation == "UPDATE"
    assert (change(result).current, change(result).proposed) == (2, 3)


def test_unchanged(context):
    assert change(plan(with_snapshot(context))).operation == "UNCHANGED"


def test_explicit_clear_retains_reference(context):
    context["inputs"] = context["inputs"][:1]
    with_snapshot(context)
    context["inputs"][0]["card"]["power"] = {
        "state": "CLEAR",
        "approval_reference": "fictional-clear",
    }
    result = plan(context)
    assert change(result).operation == "CLEAR"
    assert change(result).proposed is None
    assert change(result).approval_reference == "fictional-clear"


def test_manual_edit_conflict_even_when_source_agrees(context):
    with_snapshot(context)
    snapshot_card(context).baseline["power"].value = 1
    result = plan(context)
    assert change(result).reason == "CONFLICT_MANUAL_CHANGE"
    assert not result.approval_eligible
    assert not verify(result, context).valid


@pytest.mark.parametrize(
    "case,reason",
    [
        ("older_time", "CONFLICT_STALE_SOURCE"),
        ("older_revision", "CONFLICT_STALE_SOURCE"),
        ("same_revision", "REQUIRES_REVIEW_SAME_REVISION_CHANGE"),
        ("unknown_order", "REQUIRES_REVIEW_REVISION_ORDER"),
        ("different_source", "REQUIRES_REVIEW_SOURCE_PRECEDENCE"),
    ],
)
def test_source_precedence(context, case, reason):
    with_snapshot(context)
    card = snapshot_card(context)
    card.values["power"] = card.baseline["power"].value = 2
    old = card.baseline["power"].source
    if case == "older_time":
        old.retrieved_at = datetime(2026, 3, 1, tzinfo=UTC)
    elif case == "older_revision":
        old.revision = "fictional-3"
    elif case == "same_revision":
        old.revision = "fictional-2"
    elif case == "unknown_order":
        context["planning_policy"].revision_order = {}
    else:
        old.name = "Another fictional observer"
    result = plan(context)
    assert change(result).reason == reason
    assert not result.approval_eligible


@pytest.mark.parametrize("case", ["baseline", "current"])
def test_incomplete_snapshot_never_authorizes_overwrite(context, case):
    with_snapshot(context)
    card = snapshot_card(context)
    card.values["power"] = 1
    if case == "baseline":
        card.baseline.pop("power")
    else:
        card.values.pop("power")
    assert change(plan(context)).operation == "CONFLICT"


def test_plan_deep_immutability_and_timestamp_exclusion(context):
    first = build_plan(**context, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    second = build_plan(**context, created_at=datetime(2026, 2, 1, tzinfo=UTC))
    assert first.plan_hash == second.plan_hash
    assert first.content_json == second.content_json
    decoded = first.content
    decoded.changes.clear()
    assert first.content.changes
    with pytest.raises(ValidationError):
        first.content_json = "{}"
    assert Plan.model_validate_json(first.model_dump_json()) == first


def test_hash_unicode_and_order_are_canonical():
    assert digest({"schema_version": 1, "text": "é", "a": 1}) == digest(
        {"a": 1, "text": "e\u0301", "schema_version": 1}
    )
    with pytest.raises(ValueError):
        encode({"é": 1, "e\u0301": 2})
    with pytest.raises(ValueError):
        encode({"bad": float("nan")})


def test_approval_exact_plan(context):
    result = plan(context)
    verified = verify(result, context)
    assert verified.valid
    assert not verified.identity_authenticated
    assert not verified.execution_enabled


@pytest.mark.parametrize("mutation", ["value", "add", "remove", "source", "policy", "clear"])
def test_changed_inputs_invalidate_old_approval(context, mutation):
    first = plan(context)
    if mutation == "value":
        for r in context["inputs"]:
            r["card"]["power"]["value"] = 8
    elif mutation == "add":
        r = copy.deepcopy(context["inputs"][0])
        r["record_key"] = "another-fictional-card"
        r["identity"]["printed_identifier"] = "002/100"
        context["inputs"].append(r)
    elif mutation == "remove":
        context["inputs"].pop()
    elif mutation == "source":
        context["inputs"][0]["source"]["content_hash"] = "b" * 64
    elif mutation == "policy":
        context["projection_policy"].version = "different-policy"
    else:
        context["inputs"][0]["card"]["artist"] = {"state": "CLEAR", "approval_reference": "clear-2"}
    second = plan(context)
    assert first.plan_hash != second.plan_hash
    assert not verify(second, context, approved(first)).valid
    assert not verify(first, context).valid


def test_changed_current_state_invalidates_approval(context):
    with_snapshot(context)
    first = plan(context)
    snapshot_card(context).values["power"] = 99
    assert plan(context).plan_hash != first.plan_hash
    assert "SNAPSHOT_CHANGED" in verify(first, context).reasons


def test_changed_operation_and_conflicts_invalidate_approval(context):
    first = plan(context)
    content = first.content
    content.changes[0].operation = "SKIP"
    second = frozen_plan(content, first.created_at)
    assert first.plan_hash != second.plan_hash
    assert not verify(second, context, approved(first)).valid


def test_corrupt_content_hash_is_rejected(context):
    first = plan(context)
    broken = first.model_copy(update={"plan_hash": "0" * 64})
    assert "INVALID_VERIFICATION_INPUT" in verify(broken, context).reasons


def test_warnings_block_unless_explicitly_allowed(context):
    context["planning_policy"].nonblocking_warning_codes = ()
    result = plan(context)
    assert result.content.warnings
    assert not result.approval_eligible


def test_registry_and_other_policies_are_bound(context):
    first = plan(context)
    context["registry"] = Registry({"reserved-fictional-identity": "legacy_id"})
    assert "REGISTRY_CHANGED" in verify(first, context).reasons
    context.pop("registry")
    context["planning_policy"].version = "new-planning-policy"
    assert "PLANNING_POLICY_CHANGED" in verify(first, context).reasons
    context["staging_policy"].namespaces.append("EVENT")
    assert "STAGING_POLICY_CHANGED" in verify(first, context).reasons


def test_malformed_source_does_not_leak(context):
    context["inputs"][0]["source"]["url"] = "https://user:fictional-password@example.invalid"
    result = plan(context)
    assert not result.approval_eligible
    assert "fictional-password" not in result.content_json


def test_target_number_collision(context):
    with_snapshot(context)
    card = snapshot_card(context).model_dump(mode="json")
    card["public_id"] = "another_existing_card"
    context["snapshot"] = Snapshot.model_validate({"entities": [card]})
    assert "TARGET_NUMBER_COLLISION" in {n.code for n in plan(context).content.conflicts}


def test_reports_and_inputs_deterministic(context):
    original = copy.deepcopy(context)
    first, second = plan(context), plan(context)
    assert first.content_json == second.content_json
    assert first.plan_hash == second.plan_hash
    assert context == original


def test_offline_workflow_never_connects(context, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network access forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    assert verify(plan(context), context).valid


def test_package_imports_without_database_or_apply_modules():
    code = """
import sys
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'app' or fullname.startswith('sqlalchemy') or fullname in ('importer.runner', 'importer.planner'):
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Guard())
from importer.projection.planner import build_plan
from importer.projection.approval import verify_approval
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    folder = Path(__file__).parents[1] / "importer" / "projection"
    for file in folder.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in {
                    "apply_approved_plan",
                    "execute_plan",
                    "commit_plan",
                    "write_plan",
                }


def test_keyword_definitions_are_planned_and_manual_edits_protected(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["keywords"] = {
        "state": "VALUE",
        "value": [{"key": "glass", "label": "Glass Circle"}],
    }
    with_snapshot(context)
    keyword = next(e for e in context["snapshot"].entities if e.kind == "keywords")
    keyword.values["name"] = "Human revised label"
    result = plan(context)
    assert change(result, "name", "keywords").reason == "CONFLICT_MANUAL_CHANGE"
    assert not result.approval_eligible


def test_keyword_clear_requires_explicit_operation(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["keywords"] = {
        "state": "VALUE",
        "value": [{"key": "glass", "label": "Glass Circle"}],
    }
    with_snapshot(context)
    context["inputs"][0]["keywords"] = {"state": "VALUE", "value": []}
    assert change(plan(context), "keywords").reason == "REQUIRES_EXPLICIT_COLLECTION_CLEAR"
    context["inputs"][0]["keywords"] = {
        "state": "CLEAR",
        "approval_reference": "review-clear-links",
    }
    result = plan(context)
    assert change(result, "keywords").operation == "CLEAR"
    assert change(result, "keywords").proposed == []


def test_conflicting_shared_keyword_is_rejected(context):
    context["inputs"] = context["inputs"][:1]
    first = context["inputs"][0]
    first["keywords"] = {"state": "VALUE", "value": [{"key": "glass", "label": "Glass Circle"}]}
    second = copy.deepcopy(first)
    second["record_key"] = "other-card"
    second["identity"]["printed_identifier"] = "002/100"
    second["keywords"]["value"][0]["label"] = "Different Definition"
    context["inputs"].append(second)
    assert "CONFLICTING_SHARED_ENTITY" in {n.code for n in projection(context).rejected}


def test_projection_failure_propagates_to_treatment(context):
    context["inputs"][0]["images"] = {"state": "VALUE", "value": []}
    result = projection(context)
    assert "PARENT_NOT_PROJECTABLE" in {n.code for n in result.rejected}
    assert result.entities == []


@pytest.mark.parametrize(
    "field,value", [("name", "x" * 256), ("power", "3"), ("name", " Trailing space ")]
)
def test_importer_constraints_and_lossy_normalization_rejected(context, field, value):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["card"][field] = {"state": "VALUE", "value": value}
    assert projection(context).rejected


def test_missing_required_create_field_is_blocking(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["card"].pop("name")
    result = plan(context)
    assert "INCOMPLETE_CREATE" in {n.code for n in result.content.conflicts}
    assert not result.approval_eligible


def test_approval_eligibility_cannot_hide_conflict_operation(context):
    first = plan(context)
    content = first.content
    content.changes[0].operation = "CONFLICT"
    content.conflicts = []
    assert not frozen_plan(content, first.created_at).approval_eligible


def test_snapshot_baseline_and_unrelated_state_are_bound(context):
    with_snapshot(context)
    first = plan(context)
    snapshot_card(context).baseline["power"].source.content_hash = "c" * 64
    assert first.plan_hash != plan(context).plan_hash
    assert "SNAPSHOT_CHANGED" in verify(first, context).reasons


def test_invalid_snapshot_values_are_sanitized(context):
    with_snapshot(context)
    snapshot_card(context).values["unexpected-secret-field"] = "fictional-password"
    with pytest.raises(ValueError) as error:
        plan(context)
    assert "fictional-password" not in str(error.value)


def test_manual_clear_is_also_blocked(context):
    context["inputs"] = context["inputs"][:1]
    with_snapshot(context)
    snapshot_card(context).values["power"] = 9
    context["inputs"][0]["card"]["power"] = {"state": "CLEAR", "approval_reference": "clear-review"}
    assert change(plan(context)).reason == "CONFLICT_MANUAL_CHANGE"


def test_identity_owner_and_number_cannot_be_rebound(context):
    with_snapshot(context)
    snapshot_card(context).owner_id = "different_set"
    snapshot_card(context).values["number"] = "099/100"
    result = plan(context)
    codes = {n.code for n in result.content.conflicts}
    assert {"IDENTITY_OWNER_CHANGE", "IDENTITY_NUMBER_CHANGE"} <= codes


def test_version_one_plan_golden_vector(context):
    assert (
        plan(context).plan_hash
        == "21a2a70381d058f697cfdbcb71d2bff097be91fe28127350b3fc43aa449c02cc"
    )


def test_clear_reference_change_invalidates_approval(context):
    context["inputs"] = context["inputs"][:1]
    with_snapshot(context)
    clear = {"state": "CLEAR", "approval_reference": "review-one"}
    context["inputs"][0]["card"]["power"] = clear
    first = plan(context)
    clear["approval_reference"] = "review-two"
    second = plan(context)
    assert second.plan_hash != first.plan_hash
    assert not verify(second, context, approved(first)).valid


def test_stale_unchanged_observation_warns_without_updating(context):
    with_snapshot(context)
    snapshot_card(context).baseline["power"].source.revision = "fictional-3"
    result = plan(context)
    assert change(result).operation == "UNCHANGED"
    assert "STALE_OBSERVATION_NO_CHANGE" in {w.code for w in result.content.warnings}
    assert not result.approval_eligible


def test_lossy_source_name_normalization_rejects(context):
    context["inputs"] = context["inputs"][:1]
    context["inputs"][0]["source"]["name"] = " Fictional observer "
    assert "IMPORTER_INCOMPATIBLE_VALUE" in {n.code for n in projection(context).rejected}


@pytest.mark.parametrize("missing", ["baseline", "current"])
def test_blocked_clear_still_retains_review_reference(context, missing):
    context["inputs"] = context["inputs"][:1]
    with_snapshot(context)
    if missing == "baseline":
        snapshot_card(context).baseline.pop("power")
    else:
        snapshot_card(context).values.pop("power")
    context["inputs"][0]["card"]["power"] = {
        "state": "CLEAR",
        "approval_reference": "fictional-clear-ref",
    }
    result = plan(context)
    assert change(result).operation == "CONFLICT"
    assert change(result).approval_reference == "fictional-clear-ref"
