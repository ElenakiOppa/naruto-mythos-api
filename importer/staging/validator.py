"""Pure validation and quarantine. Accepted means staging-valid, never write-approved."""

from collections import Counter, defaultdict
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .identity import Registry, printing_identity, treatment_identity
from .models import Model, Policy, PublicID, Record, RightsState, Source, State

GAMEPLAY = (
    "name",
    "subtitle",
    "type",
    "chakra",
    "power",
    "faction",
    "ability_text",
    "mission_points",
    "mission_rank",
)


class Issue(Model):
    index: int
    record_key: str | None
    code: str
    explanation: str
    evidence_references: list[str]


class Proposal(Model):
    index: int
    record_key: str
    identity: str
    public_id: str


class SourceSummary(Model):
    source: Source
    record_count: int


class Result(Model):
    schema_version: str = "1"
    accepted_record_count: int
    unresolved_record_count: int
    accepted: list[Proposal]
    unresolved: list[Issue]
    warnings: list[Issue]
    identity_collisions: list[Issue]
    duplicate_records: list[Issue]
    proposed_public_ids: list[Proposal]
    source_summary: list[SourceSummary]
    rights_summary: dict[str, dict[str, int]]


def validate_records(
    inputs: list[dict[str, Any] | Record], policy: Policy, registry: Registry | None = None
) -> Result:
    """No files, network, settings, ORM, importer planner or application imports.

    All members of duplicate/collision groups are quarantined, including dependent
    treatments. Structural failures are retained without echoing untrusted values.
    """
    policy = Policy.model_validate(policy.model_dump())
    registry = registry or Registry()
    records: dict[int, Record] = {}
    issues: list[Issue] = []
    warnings: list[Issue] = []
    keys: dict[str, list[int]] = defaultdict(list)
    identities: dict[int, str] = {}
    proposals: dict[int, Proposal] = {}

    def issue(i: int, code: str, message: str, *, warning: bool = False):
        record = records.get(i)
        item = Issue(
            index=i,
            record_key=record.record_key if record else None,
            code=code,
            explanation=message,
            evidence_references=sorted(record.field_evidence) if record else [],
        )
        (warnings if warning else issues).append(item)

    def blocked(i: int) -> bool:
        return any(item.index == i for item in issues)

    for i, raw in enumerate(inputs):
        try:
            # Revalidate instances too: model_copy(update=...) can bypass Pydantic validation.
            r = Record.model_validate(raw.model_dump() if isinstance(raw, Record) else raw)
        except ValidationError as exc:
            locations = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            issue(i, "MALFORMED_RECORD", "Invalid staging contract at: " + ", ".join(locations))
            continue
        records[i] = r
        keys[r.record_key].append(i)
        if r.review_status != "APPROVED" or r.unresolved_questions:
            issue(i, "UNRESOLVED_REVIEW", "Approval and resolution of open questions are required")
        try:
            identities[i] = printing_identity(r.identity)
        except ValueError:
            issue(
                i, "MISSING_IDENTITY", "Expansion, edition, language, namespace and number required"
            )
        if r.identity.numbering_namespace not in policy.namespaces:
            issue(i, "UNKNOWN_NAMESPACE", "Numbering namespace is not explicitly approved")
        if r.identity.scope not in policy.approved_scopes:
            issue(i, "UNAPPROVED_SCOPE", "Edition/language/territory combination is not approved")
        if r.images.state == State.VALUE and any(
            image.owner != r.kind for image in r.images.value or []
        ):
            issue(i, "IMAGE_OWNER_MISMATCH", "Image owner must match its containing record kind")
        if r.source.authority.value != "OFFICIAL_AUTHORITATIVE":
            issue(
                i,
                "SOURCE_REVIEW_REQUIRED",
                "Source authority is not sufficient for publication",
                warning=True,
            )
        if any(
            getattr(r.rights, k) != RightsState.PERMITTED for k in ("metadata", "text", "images")
        ):
            issue(
                i,
                "RIGHTS_NOT_CLEARED",
                "Staging acceptance does not authorize redistribution",
                warning=True,
            )

    for group in keys.values():
        if len(group) > 1:
            for i in group:
                issue(i, "DUPLICATE_RECORD_KEY", "Record reference is ambiguous within this batch")

    def assign(indices: list[int]):
        by_identity: dict[str, list[int]] = defaultdict(list)
        for i in indices:
            if i in identities:
                by_identity[identities[i]].append(i)
        for group in by_identity.values():
            if len(group) > 1:
                for i in group:
                    issue(
                        i,
                        "DUPLICATE_IDENTITY",
                        "Multiple records claim the same canonical identity",
                    )
        for i in indices:
            if blocked(i) or i not in identities:
                continue
            identity = identities[i]
            public_id = registry.propose(identity)
            try:
                TypeAdapter(PublicID).validate_python(public_id)
            except ValidationError:
                issue(i, "INVALID_PUBLIC_ID", "Registry returned an invalid public ID")
                continue
            existing = records[i].existing_public_id
            if existing is not None and registry.assignments.get(identity) != existing:
                issue(
                    i,
                    "EXISTING_ID_NOT_REGISTERED",
                    "Existing public ID must match registry; no reassignment",
                )
                continue
            proposals[i] = Proposal(
                index=i, record_key=records[i].record_key, identity=identity, public_id=public_id
            )
        by_id: dict[str, set[str]] = defaultdict(set)
        for identity, public_id in registry.assignments.items():
            by_id[public_id].add(identity)
        for p in proposals.values():
            by_id[p.public_id].add(p.identity)
        for i, p in proposals.items():
            if len(by_id[p.public_id]) > 1 and not any(
                x.index == i and x.code == "PUBLIC_ID_COLLISION" for x in issues
            ):
                issue(
                    i,
                    "PUBLIC_ID_COLLISION",
                    "Public ID is claimed by different canonical identities",
                )

    printing_indices = [i for i, r in records.items() if r.kind == "PRINTING"]
    assign(printing_indices)
    parents: dict[int, int] = {}
    treatment_indices = [i for i, r in records.items() if r.kind == "TREATMENT"]
    for i in treatment_indices:
        r = records[i]
        t = r.treatment
        assert t is not None
        candidates = keys.get(t.parent_record_key or "", [])
        if len(candidates) != 1:
            issue(i, "UNRESOLVED_PARENT", "Exactly one explicit parent printing is required")
            identities.pop(i, None)
            continue
        parent_index = candidates[0]
        parent = records[parent_index]
        parents[i] = parent_index
        if parent.kind != "PRINTING" or blocked(parent_index):
            issue(
                i, "UNRESOLVED_PARENT", "Parent must be an accepted printing, not another treatment"
            )
        if t.equivalence != "VERIFIED" or t.evidence_reference not in r.field_evidence:
            issue(i, "UNVERIFIED_PARENT", "Explicit equivalence evidence is required")
        if identities.get(i) != identities.get(parent_index):
            issue(
                i,
                "PARENT_IDENTITY_MISMATCH",
                "Treatment must explicitly reference the parent's printing identity",
            )
        if t.treatment_key not in policy.treatment_keys or (
            t.finish_key is not None and t.finish_key not in policy.finish_keys
        ):
            issue(i, "UNSUPPORTED_TREATMENT", "Treatment and finish keys require explicit approval")
        for field in GAMEPLAY:
            child_value, parent_value = getattr(r.card, field), getattr(parent.card, field)
            if child_value.state == State.CLEAR:
                issue(i, "GAMEPLAY_CONFLICT", f"Variant cannot clear gameplay field: {field}")
            elif child_value.state == State.VALUE:
                if parent_value.state != State.VALUE:
                    issue(i, "GAMEPLAY_UNVERIFIED", f"Parent has no comparable value for: {field}")
                elif child_value.value != parent_value.value:
                    issue(i, "GAMEPLAY_CONFLICT", f"Variant differs from parent in: {field}")
        if r.keywords.state in (State.CLEAR, State.VALUE) and (
            r.keywords.state != parent.keywords.state or r.keywords.value != parent.keywords.value
        ):
            issue(i, "GAMEPLAY_CONFLICT", "Variant keyword changes cannot override parent gameplay")
        if not blocked(i):
            identities[i] = treatment_identity(identities[parent_index], t)
        else:
            identities.pop(i, None)
    assign(treatment_indices)
    # A treatment proposal could collide with an earlier parent's ID: invalidate dependents.
    for i, parent_index in parents.items():
        if blocked(parent_index) and not any(
            x.index == i and x.code == "UNRESOLVED_PARENT" for x in issues
        ):
            issue(i, "UNRESOLVED_PARENT", "Parent was quarantined during final collision checks")

    issues.sort(key=lambda x: (x.index, x.code, x.explanation))
    warnings.sort(key=lambda x: (x.index, x.code))
    source_counts = Counter(r.source.model_dump_json() for r in records.values())
    rights = {
        k: dict(sorted(Counter(getattr(r.rights, k).value for r in records.values()).items()))
        for k in ("metadata", "text", "images")
    }
    return Result(
        accepted_record_count=sum(not blocked(i) for i in proposals),
        unresolved_record_count=len({x.index for x in issues}),
        accepted=[p for i, p in sorted(proposals.items()) if not blocked(i)],
        unresolved=issues,
        warnings=warnings,
        identity_collisions=[x for x in issues if x.code == "PUBLIC_ID_COLLISION"],
        duplicate_records=[x for x in issues if x.code.startswith("DUPLICATE_")],
        proposed_public_ids=[p for _, p in sorted(proposals.items())],
        source_summary=[
            SourceSummary(source=Source.model_validate_json(source), record_count=count)
            for source, count in sorted(source_counts.items())
        ],
        rights_summary=rights,
    )
