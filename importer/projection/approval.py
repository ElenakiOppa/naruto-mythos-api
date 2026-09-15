"""Exact-plan and supplied-state verification only. Approval is not authentication."""

from importer.staging.identity import Registry
from importer.staging.models import Policy, Record

from .canonical import digest
from .models import (
    Approval,
    Plan,
    PlanningPolicy,
    ProjectionPolicy,
    Snapshot,
    Verification,
    snapshot_hash,
)
from .planner import checked_snapshot


def verify_approval(
    plan: Plan,
    approval: Approval,
    *,
    snapshot: Snapshot,
    inputs: list,
    staging_policy: Policy,
    projection_policy: ProjectionPolicy,
    planning_policy: PlanningPolicy,
    registry: Registry | None = None,
) -> Verification:
    reasons: list[str] = []
    try:
        plan = Plan.model_validate(plan.model_dump(mode="json"))
        approval = Approval.model_validate(approval.model_dump(mode="json"))
        snapshot = checked_snapshot(snapshot)
        staging_policy = Policy.model_validate(staging_policy.model_dump())
        projection_policy = ProjectionPolicy.model_validate(projection_policy.model_dump())
        planning_policy = PlanningPolicy.model_validate(planning_policy.model_dump())
        content = plan.content
        raw = [r.model_dump(mode="json") if isinstance(r, Record) else r for r in inputs]
        checks = {
            "APPROVAL_HASH_MISMATCH": approval.plan_hash == plan.plan_hash,
            "SNAPSHOT_CHANGED": snapshot_hash(snapshot) == content.snapshot_hash,
            "STAGING_INPUT_CHANGED": digest({"version": 1, "records": raw})
            == content.projection.staging_hash,
            "STAGING_POLICY_CHANGED": digest(staging_policy.model_dump(mode="json"))
            == content.projection.staging_policy_hash,
            "PROJECTION_POLICY_CHANGED": digest(projection_policy.model_dump(mode="json"))
            == content.projection.policy_hash,
            "PLANNING_POLICY_CHANGED": planning_policy == content.planning_policy,
            "REGISTRY_CHANGED": digest((registry or Registry()).assignments)
            == content.projection.registry_hash,
            "PLAN_NOT_ELIGIBLE": plan.approval_eligible,
        }
        reasons.extend(code for code, passed in checks.items() if not passed)
    except (ValueError, TypeError, KeyError):
        reasons.append("INVALID_VERIFICATION_INPUT")
    return Verification(valid=not reasons, reasons=tuple(sorted(reasons)))
