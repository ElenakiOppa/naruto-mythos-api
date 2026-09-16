"""Public pure execution gate. Even an eligible fictional candidate cannot authorize production."""

from typing import Literal

from pydantic import ConfigDict, model_validator

from importer.projection.approval import verify_approval
from importer.projection.canonical import digest
from importer.projection.models import Approval, Hash, Model, Plan, PlanningPolicy, ProjectionPolicy
from importer.staging.identity import Registry
from importer.staging.models import Policy

from .materializer import (
    MaterializationError,
    MaterializedPayload,
    PayloadContent,
    _materialize_exact,
)
from .receipt import ExecutionReceipt, idempotency_key, previously_succeeded
from .snapshot import SnapshotReader, check_completeness, derive_scope


class ExecutionCandidate(Model):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    plan_hash: Hash
    scope_hash: Hash
    state_hash: Hash
    snapshot_content_hash: Hash
    reader_reference: str
    read_context: str
    idempotency_key: Hash
    destination_reference: str
    payload: MaterializedPayload
    production_execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def integrity(self):
        checked = MaterializedPayload.model_validate(self.payload.model_dump())
        if PayloadContent.model_validate_json(checked.content_json).plan_hash != self.plan_hash:
            raise ValueError("Candidate plan binding mismatch")
        if self.idempotency_key != idempotency_key(self.plan_hash, self.destination_reference):
            raise ValueError("Candidate idempotency mismatch")
        return self


class ExecutionPreconditionsResult(Model):
    technically_eligible: bool
    checks: dict[str, bool]
    blocking_reasons: tuple[str, ...]
    candidate: ExecutionCandidate | None = None
    approval_identity_authenticated: Literal[False] = False
    authentication_status: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    production_execution_authorized: Literal[False] = False
    limitations: tuple[str, ...] = ("APPROVAL_NOT_AUTHENTICATED", "NO_EXECUTOR_IMPLEMENTED")


def prepare_candidate(
    plan: Plan,
    approval: Approval,
    reader: SnapshotReader,
    *,
    inputs: list,
    staging_policy: Policy,
    projection_policy: ProjectionPolicy,
    planning_policy: PlanningPolicy,
    registry: Registry | None = None,
    destination_reference: str = "fictional-local",
    receipts: tuple[ExecutionReceipt, ...] = (),
) -> ExecutionPreconditionsResult:
    checks = {
        k: False
        for k in (
            "plan_integrity",
            "approval_exact_match",
            "approval_eligible",
            "snapshot_complete",
            "state_matches",
            "context_bindings_match",
            "registry_matches",
            "materialization",
            "identity_and_relationships",
            "not_previously_executed",
        )
    }
    reasons: list[str] = []

    # Domain-v2 previews cannot be smuggled through a legacy v1 approval/execution contract.
    # A separately reviewed versioned planner/materializer is required before that boundary.
    if any(
        (r.get("schema_version") if isinstance(r, dict) else getattr(r, "schema_version", None))
        == "2"
        for r in inputs
    ):
        return ExecutionPreconditionsResult(
            technically_eligible=False,
            checks=checks,
            blocking_reasons=("DOMAIN_V2_EXECUTION_NOT_SUPPORTED",),
        )

    def result(candidate=None):
        return ExecutionPreconditionsResult(
            technically_eligible=not reasons and candidate is not None,
            checks=checks,
            blocking_reasons=tuple(sorted(set(reasons))),
            candidate=candidate,
        )

    try:
        plan = Plan.model_validate(plan.model_dump(mode="json"))
        checks["plan_integrity"] = True
    except (ValueError, TypeError):
        reasons.append("PLAN_HASH_MISMATCH")
        return result()
    try:
        approval = Approval.model_validate(approval.model_dump(mode="json"))
        checks["approval_exact_match"] = approval.plan_hash == plan.plan_hash
        checks["approval_eligible"] = plan.approval_eligible
        if not checks["approval_exact_match"]:
            reasons.append("APPROVAL_MISMATCH")
        if plan.content.projection.rejected:
            reasons.append("PROJECTION_REJECTION")
        if not plan.approval_eligible:
            reasons.append("BLOCKING_CONFLICT")
        scope = derive_scope(plan)
        envelope = reader.read_snapshot(scope)
        completeness = check_completeness(scope, envelope)
        checks["snapshot_complete"] = completeness.complete
        reasons.extend(completeness.reasons)
        checks["state_matches"] = envelope.semantic_hash == plan.content.snapshot_hash
        if not checks["state_matches"]:
            reasons.extend(("STATE_CHANGED", "STALE_APPROVAL"))
        verified = verify_approval(
            plan,
            approval,
            snapshot=envelope.state,
            inputs=inputs,
            staging_policy=staging_policy,
            projection_policy=projection_policy,
            planning_policy=planning_policy,
            registry=registry,
        )
        checks["context_bindings_match"] = verified.valid
        reasons.extend(verified.reasons)
        checks["registry_matches"] = (
            digest(envelope.registry) == plan.content.projection.registry_hash
        )
        if not checks["registry_matches"]:
            reasons.append("REGISTRY_CHANGED")
        checks["not_previously_executed"] = not previously_succeeded(
            plan.plan_hash, destination_reference, receipts
        )
        if not checks["not_previously_executed"]:
            reasons.append("ALREADY_EXECUTED")
        if reasons:
            return result()
        payload = _materialize_exact(plan, envelope)
        checks["materialization"] = checks["identity_and_relationships"] = True
        candidate = ExecutionCandidate(
            plan_hash=plan.plan_hash,
            scope_hash=scope.scope_hash,
            state_hash=envelope.semantic_hash,
            snapshot_content_hash=envelope.content_hash,
            reader_reference=envelope.reader_reference,
            read_context=envelope.read_context,
            idempotency_key=idempotency_key(plan.plan_hash, destination_reference),
            destination_reference=destination_reference,
            payload=payload,
        )
        return result(candidate)
    except MaterializationError as error:
        reasons.extend(("MATERIALIZATION_FAILED", str(error)))
    except (ValueError, TypeError, KeyError):
        reasons.append("INVALID_EXECUTION_INPUT")
    return result()
