"""Complete scoped state contracts and a fictional in-memory reader. No database imports."""

from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import AwareDatetime, Field, StrictBool, TypeAdapter

from importer.projection.canonical import digest
from importer.projection.models import Hash, Kind, Model, Plan, Snapshot, snapshot_hash
from importer.projection.projector import IMPORT_MODELS
from importer.schemas import ImportKeyword
from importer.staging.models import PublicID, Text

CoverageStatus = Literal["PRESENT", "PROVEN_ABSENT", "MISSING", "AMBIGUOUS"]


def association_entries(value) -> list[dict[str, str]]:
    if value is None:
        return []  # Completeness separately blocks unknown association state.
    return [
        {"slug": k.slug, "name": k.name}
        for k in TypeAdapter(list[ImportKeyword]).validate_python(value)
    ]


def row_fields(kind: Kind) -> set[str]:
    return set(IMPORT_MODELS[kind].model_fields) - {"id", "cards", "variants", "images"}


class Target(Model):
    kind: Kind
    public_id: PublicID


class SnapshotScope(Model):
    version: Literal["1"] = "1"
    targets: tuple[Target, ...]
    set_ids: tuple[str, ...]
    # Each set inventory includes every card, its variants, keywords and field provenance.
    closure: Literal["ALL_SET_CARDS_VARIANTS_KEYWORDS_AND_BASELINES"] = (
        "ALL_SET_CARDS_VARIANTS_KEYWORDS_AND_BASELINES"
    )

    @property
    def scope_hash(self) -> str:
        return digest(self.model_dump(mode="json"))


def derive_scope(plan: Plan) -> SnapshotScope:
    plan = Plan.model_validate(plan.model_dump(mode="json"))
    entities = plan.content.projection.entities
    return SnapshotScope(
        targets=tuple(
            Target(kind=e.kind, public_id=e.public_id)
            for e in sorted(entities, key=lambda e: (e.kind, e.public_id))
        ),
        set_ids=tuple(sorted({e.public_id for e in entities if e.kind == "sets"})),
    )


class Coverage(Model):
    key: str
    status: CoverageStatus
    exhaustive: StrictBool = False
    value_hash: Hash | None = None


class SnapshotEnvelope(Model):
    schema_version: Literal["1"] = "1"
    scope_hash: Hash
    state: Snapshot
    registry: dict[str, str] = Field(default_factory=dict)
    coverage: tuple[Coverage, ...]
    captured_at: AwareDatetime
    reader_reference: Text
    read_context: Text

    @property
    def semantic_hash(self) -> str:
        # Exactly compatible with the Phase 12C approved snapshot hash.
        return snapshot_hash(self.state)

    @property
    def content_hash(self) -> str:
        return digest(
            {
                "version": 1,
                "scope": self.scope_hash,
                "state": self.semantic_hash,
                "registry": self.registry,
                "coverage": sorted(
                    (c.model_dump(mode="json") for c in self.coverage), key=lambda c: c["key"]
                ),
            }
        )


class CompletenessResult(Model):
    complete: bool
    components: tuple[Coverage, ...]
    reasons: tuple[str, ...]


def required_components(scope: SnapshotScope, state: Snapshot, registry: dict) -> dict:
    """Expand the symbolic inventory contract, without interpreting a missing row as absent."""
    entities = {(e.kind, e.public_id): e for e in state.entities}
    required: dict[str, Any] = {"registry": registry}
    for t in scope.targets:
        e = entities.get((t.kind, t.public_id))
        required[f"entity:{t.kind}:{t.public_id}"] = e.model_dump(mode="json") if e else None
        required[f"baseline:{t.kind}:{t.public_id}"] = (
            {k: v.model_dump(mode="json") for k, v in e.baseline.items()} if e else None
        )
        if t.kind in ("cards", "variants"):
            required[f"owner:{t.kind}:{t.public_id}"] = e.owner_id if e else None
    for set_id in scope.set_ids:
        cards = sorted(
            (e for e in state.entities if e.kind == "cards" and e.owner_id == set_id),
            key=lambda e: e.public_id,
        )
        required[f"cards:{set_id}"] = [e.public_id for e in cards]
        required[f"numbers:{set_id}"] = [[e.values.get("number"), e.public_id] for e in cards]
    for e in sorted(state.entities, key=lambda e: (e.kind, e.public_id)):
        prefix = f"{e.kind}:{e.public_id}"
        required[f"entity:{prefix}"] = e.model_dump(mode="json")
        required[f"baseline:{prefix}"] = {
            k: v.model_dump(mode="json") for k, v in e.baseline.items()
        }
        if e.kind in ("cards", "variants"):
            required[f"owner:{prefix}"] = e.owner_id
        if e.kind == "cards":
            required[f"variants:{e.public_id}"] = sorted(
                v.public_id
                for v in state.entities
                if v.kind == "variants" and v.owner_id == e.public_id
            )
            required[f"associations:{e.public_id}"] = e.values.get("keywords")
    return required


def check_completeness(scope: SnapshotScope, envelope: SnapshotEnvelope) -> CompletenessResult:
    envelope = SnapshotEnvelope.model_validate(envelope.model_dump(mode="json"))
    reasons = []
    observed: dict[str, list[Coverage]] = {}
    for observation in envelope.coverage:
        observed.setdefault(observation.key, []).append(observation)
    components = []
    if scope.scope_hash != envelope.scope_hash:
        reasons.append("SNAPSHOT_SCOPE_MISMATCH")
    required = required_components(scope, envelope.state, envelope.registry)
    for key, value in sorted(required.items()):
        status: CoverageStatus
        proof = observed.get(key, [])
        empty = value is None or value == [] or value == {}
        if len(proof) != 1:
            status = "AMBIGUOUS" if proof else "MISSING"
        elif proof[0].status in ("MISSING", "AMBIGUOUS"):
            status = proof[0].status
        elif not proof[0].exhaustive:
            status = "MISSING"
        elif proof[0].value_hash != digest(value) or proof[0].status != (
            "PROVEN_ABSENT" if empty else "PRESENT"
        ):
            status = "AMBIGUOUS"
        else:
            status = proof[0].status
        components.append(
            Coverage(
                key=key,
                status=status,
                exhaustive=status in ("PRESENT", "PROVEN_ABSENT"),
                value_hash=digest(value),
            )
        )
        if status in ("MISSING", "AMBIGUOUS"):
            reasons.append("AMBIGUOUS_ABSENCE" if status == "AMBIGUOUS" else "INCOMPLETE_SNAPSHOT")
    for e in envelope.state.entities:
        if row_fields(e.kind) - set(e.values):
            reasons.append("INCOMPLETE_FIELDS")
        if e.kind == "cards" and not isinstance(e.values.get("keywords"), list):
            reasons.append("INCOMPLETE_ASSOCIATIONS")
    return CompletenessResult(
        complete=not reasons, components=tuple(components), reasons=tuple(sorted(set(reasons)))
    )


class SnapshotReader(Protocol):
    """Future trusted reader must exhaustively read scope under the required transaction locks."""

    def read_snapshot(self, scope: SnapshotScope) -> SnapshotEnvelope: ...


class FictionalMemoryReader:
    """The supplied state is the COMPLETE fictional universe, never a partial query result.

    The implementation proves absence only by exhaustively scanning that supplied universe.
    This establishes a test contract, not authenticity of an external database observation.
    """

    def __init__(self, state: Snapshot, registry: dict[str, str] | None = None):
        self._state = Snapshot.model_validate(state.model_dump(mode="json"))
        self._registry = dict(registry or {})
        self._generation = 0

    def simulate_change(self, state: Snapshot) -> None:
        self._state = Snapshot.model_validate(state.model_dump(mode="json"))
        self._generation += 1

    def read_snapshot(self, scope: SnapshotScope) -> SnapshotEnvelope:
        targets = {(t.kind, t.public_id) for t in scope.targets}
        selected = {
            (e.kind, e.public_id): e
            for e in self._state.entities
            if (e.kind, e.public_id) in targets
            or (e.kind == "cards" and e.owner_id in scope.set_ids)
        }
        cards = {key[1] for key in selected if key[0] == "cards"}
        keyword_slugs = {
            kw["slug"]
            for e in selected.values()
            if e.kind == "cards"
            for kw in association_entries(e.values.get("keywords"))
        }
        for e in self._state.entities:
            if (e.kind == "variants" and e.owner_id in cards) or (
                e.kind == "keywords" and e.public_id in keyword_slugs
            ):
                selected[e.kind, e.public_id] = e
        state = Snapshot(entities=tuple(selected[k] for k in sorted(selected)))
        values = required_components(scope, state, self._registry)
        coverage = tuple(
            Coverage(
                key=k,
                status="PROVEN_ABSENT" if v is None or v == [] or v == {} else "PRESENT",
                exhaustive=True,
                value_hash=digest(v),
            )
            for k, v in sorted(values.items())
        )
        return SnapshotEnvelope(
            scope_hash=scope.scope_hash,
            state=state,
            registry=self._registry,
            coverage=coverage,
            captured_at=datetime.now(UTC),
            reader_reference="fictional-memory-v1",
            read_context=f"fictional-generation:{self._generation}",
        )
