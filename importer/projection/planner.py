"""Pure field-level dry runs against supplied snapshots. Never uses an engine."""

from collections import Counter
from datetime import UTC, datetime

from importer.staging.identity import Registry
from importer.staging.models import Policy, Source, State

from .canonical import encode
from .models import (
    Change,
    Content,
    Notice,
    Plan,
    PlanningPolicy,
    ProjectionPolicy,
    Snapshot,
    frozen_plan,
    snapshot_hash,
)
from .projector import project, validate_fragment


def checked_snapshot(snapshot: Snapshot) -> Snapshot:
    try:
        snapshot = Snapshot.model_validate(snapshot.model_dump(mode="json"))
        for e in snapshot.entities:
            if (e.kind in ("sets", "keywords")) != (e.owner_id is None):
                raise ValueError("Invalid snapshot owner")
            validate_fragment(e.kind, e.values)
            if "id" in e.values and e.values["id"] != e.public_id:
                raise ValueError("Snapshot public ID mismatch")
            if e.kind == "keywords" and e.values.get("slug") != e.public_id:
                raise ValueError("Snapshot keyword identity mismatch")
            if e.kind == "cards" and not isinstance(e.values.get("number"), str):
                raise ValueError("Complete card number inventory is required")
            for field, observation in e.baseline.items():
                validate_fragment(e.kind, {field: observation.value})
        return snapshot
    except (ValueError, TypeError, KeyError):
        raise ValueError("Invalid supplied snapshot") from None


def source_order(new: Source, old: Source, policy: PlanningPolicy) -> str | None:
    """Retrieval time is not publisher chronology. Only approved revision order permits updates."""
    if new.name != old.name:
        return "REQUIRES_REVIEW_SOURCE_PRECEDENCE"
    if new.retrieved_at < old.retrieved_at:
        return "CONFLICT_STALE_SOURCE"
    order = policy.revision_order.get(new.name, ())
    if new.revision not in order or old.revision not in order:
        return "REQUIRES_REVIEW_REVISION_ORDER"
    if order.index(new.revision) < order.index(old.revision):
        return "CONFLICT_STALE_SOURCE"
    if new.revision == old.revision:
        return "REQUIRES_REVIEW_SAME_REVISION_CHANGE"
    return None


def build_plan(
    inputs: list,
    staging_policy: Policy,
    projection_policy: ProjectionPolicy,
    snapshot: Snapshot,
    planning_policy: PlanningPolicy,
    *,
    registry: Registry | None = None,
    created_at: datetime | None = None,
) -> Plan:
    snapshot = checked_snapshot(snapshot)
    try:
        planning_policy = PlanningPolicy.model_validate(planning_policy.model_dump())
    except ValueError:
        raise ValueError("Invalid planning policy") from None
    projection = project(inputs, staging_policy, projection_policy, registry)
    current = {(e.kind, e.public_id): e for e in snapshot.entities}
    proposed = {(e.kind, e.public_id): e for e in projection.entities}
    changes = []
    conflicts = []
    warnings = list(projection.warnings)
    occupied = {}
    for stored in snapshot.entities:
        if stored.kind == "cards":
            number_key = (stored.owner_id, encode(stored.values["number"]))
            if number_key in occupied:
                conflicts.append(
                    Notice(
                        record_key=stored.public_id,
                        code="SNAPSHOT_NUMBER_COLLISION",
                        explanation="Supplied snapshot has duplicate card numbers",
                    )
                )
            occupied[number_key] = stored.public_id
    for e in projection.entities:
        old = current.get((e.kind, e.public_id))

        def add(field, operation, reason, before=None, after=None, approval=None, e=e, old=old):
            changes.append(
                Change(
                    kind=e.kind,
                    public_id=e.public_id,
                    field=field,
                    current=before,
                    proposed=after,
                    operation=operation,
                    reason=reason,
                    source=e.source,
                    approval_reference=approval,
                    baseline=old.baseline.get(field) if old else None,
                )
            )
            if operation == "CONFLICT":
                conflicts.append(
                    Notice(
                        record_key=e.record_key,
                        code=reason,
                        explanation="Review required for " + field,
                    )
                )

        if e.kind not in ("sets", "keywords"):
            parent_kind = "sets" if e.kind == "cards" else "cards"
            if (parent_kind, e.owner_id) not in current and (
                parent_kind,
                e.owner_id,
            ) not in proposed:
                add("$owner", "CONFLICT", "MISSING_OWNER", after=e.owner_id)
            elif old is not None and old.owner_id != e.owner_id:
                add("$owner", "CONFLICT", "IDENTITY_OWNER_CHANGE", old.owner_id, e.owner_id)
            else:
                add(
                    "$owner",
                    "UNCHANGED" if old else "CREATE",
                    "OWNER_REFERENCE",
                    old.owner_id if old else None,
                    e.owner_id,
                )
        if e.kind == "cards":
            key = (e.owner_id, encode(e.importer_fields["number"]))
            occupant = occupied.get(key)
            if occupant is not None and occupant != e.public_id:
                add("$identity", "CONFLICT", "TARGET_NUMBER_COLLISION")
            occupied[key] = e.public_id
            if old is not None and old.values["number"] != e.importer_fields["number"]:
                add("$identity", "CONFLICT", "IDENTITY_NUMBER_CHANGE")
        if old is None:
            required = {
                "sets": ("name", "language", "edition"),
                "cards": ("number", "name"),
                "variants": ("type", "language", "serial_numbered"),
                "keywords": ("slug", "name"),
            }[e.kind]
            if any(f not in e.importer_fields or e.importer_fields[f] is None for f in required):
                add("$entity", "CONFLICT", "INCOMPLETE_CREATE")
        for field, patch in sorted(e.fields.items()):
            before = old.values.get(field) if old else None
            if patch.state in (State.ABSENT, State.UNKNOWN):
                add(field, "SKIP", patch.state.value, before)
                continue
            after = (
                ([] if field == "keywords" else None) if patch.state == State.CLEAR else patch.value
            )
            if old is None:
                if patch.state == State.CLEAR:
                    add(
                        field,
                        "SKIP",
                        "CLEAR_ON_NEW_ENTITY",
                        after=after,
                        approval=patch.approval_reference,
                    )
                else:
                    add(field, "CREATE", "NEW_ENTITY_VALUE", after=after)
                continue
            if field not in old.values:
                add(
                    field,
                    "CONFLICT",
                    "REQUIRES_REVIEW_INCOMPLETE_SNAPSHOT",
                    after=after,
                    approval=patch.approval_reference,
                )
                continue
            baseline = old.baseline.get(field)
            if baseline is not None and encode(before) != encode(baseline.value):
                add(
                    field,
                    "CONFLICT",
                    "CONFLICT_MANUAL_CHANGE",
                    before,
                    after,
                    patch.approval_reference,
                )
            elif encode(before) == encode(after):
                add(field, "UNCHANGED", "IDENTICAL_VALUE", before, after, patch.approval_reference)
                if (
                    baseline is not None
                    and source_order(e.source, baseline.source, planning_policy)
                    == "CONFLICT_STALE_SOURCE"
                ):
                    warnings.append(
                        Notice(
                            record_key=e.record_key,
                            code="STALE_OBSERVATION_NO_CHANGE",
                            explanation="Older observation retained for review; no value or provenance update",
                        )
                    )
            elif baseline is None:
                add(
                    field,
                    "CONFLICT",
                    "REQUIRES_REVIEW_MISSING_BASELINE",
                    before,
                    after,
                    patch.approval_reference,
                )
            elif (reason := source_order(e.source, baseline.source, planning_policy)) is not None:
                add(field, "CONFLICT", reason, before, after, patch.approval_reference)
            elif field == "keywords" and after == [] and patch.state != State.CLEAR:
                add(field, "CONFLICT", "REQUIRES_EXPLICIT_COLLECTION_CLEAR", before, after)
            else:
                add(
                    field,
                    "CLEAR" if patch.state == State.CLEAR else "UPDATE",
                    "EXPLICIT_APPROVED_CLEAR"
                    if patch.state == State.CLEAR
                    else "NEWER_REVIEWED_SOURCE",
                    before,
                    after,
                    patch.approval_reference,
                )
    content = Content(
        projection=projection,
        snapshot_hash=snapshot_hash(snapshot),
        planning_policy=planning_policy,
        changes=sorted(changes, key=lambda c: (c.kind, c.public_id, c.field)),
        conflicts=sorted(conflicts, key=lambda n: (n.record_key, n.code, n.explanation)),
        warnings=sorted(warnings, key=lambda n: (n.record_key, n.code)),
        expected_entity_counts=dict(sorted(Counter(e.kind for e in projection.entities).items())),
        expected_operation_counts=dict(sorted(Counter(c.operation for c in changes).items())),
    )
    return frozen_plan(content, created_at or datetime.now(UTC))
