"""Pure context-fence checks. No lock acquisition, transaction or write implementation."""

from importer.projection.models import Model

from .preconditions import ExecutionCandidate
from .snapshot import SnapshotEnvelope, SnapshotScope, check_completeness


class FenceResult(Model):
    unchanged: bool
    reasons: tuple[str, ...]


def verify_fence(
    candidate: ExecutionCandidate, scope: SnapshotScope, fresh: SnapshotEnvelope
) -> FenceResult:
    try:
        candidate = ExecutionCandidate.model_validate(candidate.model_dump(mode="json"))
    except ValueError:
        return FenceResult(unchanged=False, reasons=("INVALID_CANDIDATE",))
    reasons = []
    if not check_completeness(scope, fresh).complete:
        reasons.append("INCOMPLETE_SNAPSHOT")
    if candidate.scope_hash != scope.scope_hash or candidate.scope_hash != fresh.scope_hash:
        reasons.append("SNAPSHOT_SCOPE_MISMATCH")
    if (
        candidate.snapshot_content_hash != fresh.content_hash
        or candidate.state_hash != fresh.semantic_hash
    ):
        reasons.append("CONCURRENT_STATE_CHANGE")
    if (
        candidate.read_context != fresh.read_context
        or candidate.reader_reference != fresh.reader_reference
    ):
        reasons.append("READ_CONTEXT_CHANGED_REVALIDATION_REQUIRED")
    return FenceResult(unchanged=not reasons, reasons=tuple(sorted(reasons)))


def lock_order(scope: SnapshotScope) -> tuple[str, ...]:
    """Symbolic deterministic resources only; these strings are never executed as SQL."""
    resources = ["00:catalogue-writer-gate"]
    resources += ["10:set:" + set_id for set_id in scope.set_ids]
    resources += ["20:entity:" + target.kind + ":" + target.public_id for target in scope.targets]
    resources.append("30:registry-and-receipts")
    return tuple(sorted(set(resources)))
