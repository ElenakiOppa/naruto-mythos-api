"""Contracts for offline projection. Snapshots are caller-supplied, never queried."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from importer.staging.models import PublicID, Scope, Source, State, Text

from .canonical import digest, encode

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Kind = Literal["sets", "cards", "variants", "keywords"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Mapping(Model):
    scope: Scope
    namespace: str
    set_id: PublicID
    set_name: Annotated[str, Field(min_length=1, max_length=255)]
    edition_label: Annotated[str, Field(min_length=1, max_length=64)]


class ProjectionPolicy(Model):
    version: Text
    mappings: tuple[Mapping, ...]

    @model_validator(mode="after")
    def unambiguous(self):
        scopes = [encode([m.scope.model_dump(), m.namespace]) for m in self.mappings]
        if len(scopes) != len(set(scopes)) or len({m.set_id for m in self.mappings}) != len(scopes):
            raise ValueError("Projection mappings must be one-to-one with target sets")
        if any(m.scope.territory is not None for m in self.mappings):
            raise ValueError("Territory mappings are unsupported")
        return self


class PlanningPolicy(Model):
    version: Text = "1"
    revision_order: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    nonblocking_warning_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def distinct_revisions(self):
        if any(len(v) != len(set(v)) for v in self.revision_order.values()):
            raise ValueError("Revision order must not contain duplicates")
        return self


class Notice(Model):
    record_key: str
    code: str
    explanation: str


class Patch(Model):
    state: State
    value: JsonValue = None
    approval_reference: str | None = None


class ProposedEntity(Model):
    kind: Kind
    public_id: PublicID
    owner_id: PublicID | None = None
    record_key: str
    source: Source
    fields: dict[str, Patch]
    # Sparse importer field names; NEVER a full-snapshot input for the existing writer.
    importer_fields: dict[str, JsonValue]


class Projection(Model):
    staging_hash: Hash
    staging_policy_hash: Hash
    registry_hash: Hash
    policy_hash: Hash
    policy_version: str
    entities: list[ProposedEntity]
    rejected: list[Notice]
    warnings: list[Notice]
    evidence: dict[str, JsonValue]


class Observation(Model):
    value: JsonValue
    source: Source


class EntitySnapshot(Model):
    kind: Kind
    public_id: PublicID
    owner_id: PublicID | None = None
    values: dict[str, JsonValue]
    baseline: dict[str, Observation] = Field(default_factory=dict)


class Snapshot(Model):
    version: Literal["1"] = "1"
    entities: tuple[EntitySnapshot, ...] = ()

    @model_validator(mode="after")
    def unique_entities(self):
        keys = [(e.kind, e.public_id) for e in self.entities]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate snapshot entity")
        return self


class Change(Model):
    kind: Kind
    public_id: str
    field: str
    current: JsonValue = None
    proposed: JsonValue = None
    operation: Literal["CREATE", "UPDATE", "CLEAR", "UNCHANGED", "CONFLICT", "SKIP"]
    reason: str
    source: Source
    approval_reference: str | None = None
    baseline: Observation | None = None


class Content(Model):
    schema_version: Literal["1"] = "1"
    projection: Projection
    snapshot_hash: Hash
    planning_policy: PlanningPolicy
    changes: list[Change]
    conflicts: list[Notice]
    warnings: list[Notice]
    expected_entity_counts: dict[str, int]
    expected_operation_counts: dict[str, int]

    @property
    def approval_eligible(self) -> bool:
        return (
            not any(c.operation == "CONFLICT" for c in self.changes)
            and not self.conflicts
            and not self.projection.rejected
            and all(w.code in self.planning_policy.nonblocking_warning_codes for w in self.warnings)
        )


class Plan(Model):
    """Deeply immutable envelope: content is canonical JSON, decoded only into fresh copies."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)
    content_json: str
    plan_hash: Hash
    created_at: AwareDatetime

    @model_validator(mode="after")
    def integrity(self):
        content = Content.model_validate_json(self.content_json)
        value = content.model_dump(mode="json")
        if encode(value) != self.content_json or digest(value) != self.plan_hash:
            raise ValueError("Plan content or hash integrity failure")
        return self

    @property
    def content(self) -> Content:
        return Content.model_validate_json(self.content_json)

    @property
    def approval_eligible(self) -> bool:
        return self.content.approval_eligible


class Approval(Model):
    plan_hash: Hash
    approver_reference: Text
    approved_at: AwareDatetime
    review_reference: Text | None = None


class Verification(Model):
    valid: bool
    reasons: tuple[str, ...]
    identity_authenticated: Literal[False] = False
    execution_enabled: Literal[False] = False


def snapshot_hash(snapshot: Snapshot) -> str:
    value = snapshot.model_dump(mode="json")
    value["entities"] = sorted(value["entities"], key=lambda e: (e["kind"], e["public_id"]))
    return digest(value)


def frozen_plan(content: Content, created_at: AwareDatetime) -> Plan:
    value = content.model_dump(mode="json")
    return Plan(content_json=encode(value), plan_hash=digest(value), created_at=created_at)
