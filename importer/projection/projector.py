"""Fail-closed projection; reuse importer field validation, never its database planner."""

from collections import defaultdict

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from importer.schemas import ImportCard, ImportKeyword, ImportSet, ImportSource, ImportVariant
from importer.staging.identity import Registry
from importer.staging.models import Policy, Record, State
from importer.staging.validator import validate_records

from .canonical import digest, encode
from .models import Kind, Notice, Patch, Projection, ProjectionPolicy, ProposedEntity

IMPORT_MODELS: dict[str, type[BaseModel]] = {
    "sets": ImportSet,
    "cards": ImportCard,
    "variants": ImportVariant,
    "keywords": ImportKeyword,
}
CARD_FIELDS = (
    "name",
    "subtitle",
    "type",
    "chakra",
    "power",
    "faction",
    "ability_text",
    "flavor_text",
    "artist",
)
DIMENSIONS = {
    "expansion": "SUPPORTED_WITH_MAPPING",
    "edition": "SUPPORTED_WITH_MAPPING",
    "language": "SUPPORTED",
    "territory": "UNSUPPORTED",
    "numbering_namespace": "SUPPORTED_WITH_MAPPING",
    "printed_identifier": "SUPPORTED",
    "card_fields": "SUPPORTED",
    "mission_fields": "UNSUPPORTED",
    "rarity": "SUPPORTED",
    "rarity_abbreviation_and_normalized_key": "UNSUPPORTED",
    "keywords": "SUPPORTED_WITH_MAPPING",
    "treatment": "SUPPORTED_WITH_MAPPING",
    "finish": "SUPPORTED",
    "serialization": "REQUIRES_REVIEW",
    "images": "REQUIRES_REVIEW",
    "availability": "UNSUPPORTED",
    "provenance": "SUPPORTED_WITH_MAPPING",
}


def validate_fragment(kind: str, values: dict) -> None:
    """Validate sparse fields with existing constraints and reject lossy normalization."""
    model = IMPORT_MODELS[kind]
    for key, value in values.items():
        if key not in model.model_fields or key in ("cards", "variants", "images"):
            raise ValueError("Unsupported importer field")
        adapter = TypeAdapter(model.model_fields[key].rebuild_annotation())
        checked = adapter.validate_python(value)
        if adapter.dump_python(checked, mode="json") != value:
            raise ValueError("Importer normalization would change supplied data")
        if isinstance(value, str) and value != value.strip():
            raise ValueError("Importer whitespace normalization would lose information")
    if kind == "cards" and values.get("keywords") is not None:
        slugs = [k["slug"] for k in values["keywords"]]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Duplicate keyword identity")


def project(
    inputs: list, staging_policy: Policy, policy: ProjectionPolicy, registry: Registry | None = None
) -> Projection:
    """Re-run Phase 12B validation on these exact inputs; do not trust acceptance flags."""
    try:
        raw = [r.model_dump(mode="json") if isinstance(r, Record) else r for r in inputs]
        raw_hash = digest({"version": 1, "records": raw})
        staging_policy = Policy.model_validate(staging_policy.model_dump())
        policy = ProjectionPolicy.model_validate(policy.model_dump())
    except (ValueError, TypeError):
        raise ValueError("Invalid projection input or policy") from None
    result = validate_records(raw, staging_policy, registry)
    rejected = [
        Notice(
            record_key=str(i.index), code=i.code, explanation="Staging validation rejected record"
        )
        for i in result.unresolved
    ]
    warnings = [
        Notice(record_key=i.record_key or str(i.index), code=i.code, explanation=i.explanation)
        for i in result.warnings
    ]
    accepted = {
        p.record_key: (Record.model_validate(raw[p.index]), p.public_id) for p in result.accepted
    }
    candidates: list[ProposedEntity] = []
    evidence: dict[str, JsonValue] = {}
    failed: set[str] = set()

    def reject(key, code):
        rejected.append(
            Notice(record_key=key, code=code, explanation="Projection requires review: " + code)
        )
        failed.add(key)

    for key, (r, public_id) in sorted(accepted.items()):
        evidence[key] = r.model_dump(mode="json")
        scope = r.identity.scope
        if scope.territory is not None:
            reject(key, "UNSUPPORTED_TERRITORY")
        mappings = [
            m
            for m in policy.mappings
            if m.scope == scope and m.namespace == r.identity.numbering_namespace
        ]
        if len(mappings) != 1:
            reject(key, "UNMAPPED_PRINTING_SCOPE_OR_NAMESPACE")
        if any(
            getattr(r.card, f).state != State.ABSENT for f in ("mission_points", "mission_rank")
        ):
            reject(key, "UNSUPPORTED_MISSION_FIELDS")
        if r.availability.state != State.ABSENT:
            reject(key, "UNSUPPORTED_AVAILABILITY")
        if r.images.state in (State.VALUE, State.CLEAR):
            reject(key, "IMAGE_REVIEW_REQUIRED")
        if any(
            getattr(r.rarity, f).state != State.ABSENT for f in ("abbreviation", "normalized_key")
        ):
            reject(key, "UNSUPPORTED_RARITY_DIMENSION")
        if key in failed:
            continue
        mapping = mappings[0]
        fields: dict[str, Patch] = {}
        kind: Kind = "cards"
        owner = mapping.set_id
        if r.kind == "PRINTING":
            fields["number"] = Patch(state=State.VALUE, value=r.identity.printed_identifier)
            for field in CARD_FIELDS:
                fields[field] = Patch.model_validate(getattr(r.card, field).model_dump(mode="json"))
            kw = r.keywords
            fields["keywords"] = Patch(
                state=kw.state,
                approval_reference=kw.approval_reference,
                value=[{"slug": k.key, "name": k.label} for k in kw.value]
                if kw.value is not None
                else None,
            )
        else:
            t = r.treatment
            assert t is not None
            parent = accepted.get(t.parent_record_key or "")
            if parent is None:
                reject(key, "PARENT_NOT_PROJECTABLE")
                continue
            if any(
                getattr(r.card, f).state == State.CLEAR
                or (
                    getattr(r.card, f).state == State.VALUE
                    and getattr(r.card, f) != getattr(parent[0].card, f)
                )
                for f in CARD_FIELDS
            ):
                reject(key, "UNSUPPORTED_TREATMENT_OVERRIDE")
            if t.serial_numbered is None:
                reject(key, "UNKNOWN_SERIALIZATION")
            kind, owner = "variants", parent[1]
            for field, value in {
                "type": t.treatment_key,
                "finish": t.finish_key,
                "collector_number": t.collector_number,
                "language": scope.language,
                "edition": mapping.edition_label,
                "serial_numbered": t.serial_numbered,
                "serial_total": t.serial_total,
            }.items():
                fields[field] = Patch(
                    state=State.UNKNOWN if value is None else State.VALUE, value=value
                )
        fields["rarity"] = Patch.model_validate(r.rarity.official_label.model_dump(mode="json"))
        # Unknown image observations are retained as SKIP, never an image removal.
        fields["images"] = Patch(state=r.images.state)
        values: dict[str, JsonValue] = {"id": public_id}
        for field, patch in fields.items():
            if patch.state == State.VALUE:
                values[field] = patch.value
            elif patch.state == State.CLEAR:
                values[field] = [] if field == "keywords" else None
        set_values: dict[str, JsonValue] = {
            "id": mapping.set_id,
            "name": mapping.set_name,
            "edition": mapping.edition_label,
            "language": scope.language,
        }
        try:
            source_fields = r.source.model_dump(
                mode="json", exclude={"revision", "content_hash", "authority"}
            )
            if ImportSource.model_validate(source_fields).model_dump(mode="json") != source_fields:
                raise ValueError("Importer source normalization would lose information")
            validate_fragment("sets", set_values)
            validate_fragment(kind, values)
        except (ValueError, ValidationError):
            reject(key, "IMPORTER_INCOMPATIBLE_VALUE")
        if key not in failed:
            candidates.append(
                ProposedEntity(
                    kind="sets",
                    public_id=mapping.set_id,
                    record_key=key,
                    source=r.source,
                    fields={
                        k: Patch(state=State.VALUE, value=v)
                        for k, v in set_values.items()
                        if k != "id"
                    },
                    importer_fields=set_values,
                )
            )
            candidates.append(
                ProposedEntity(
                    kind=kind,
                    public_id=public_id,
                    owner_id=owner,
                    record_key=key,
                    source=r.source,
                    fields=fields,
                    importer_fields=values,
                )
            )
            if kind == "cards" and r.keywords.state == State.VALUE:
                for keyword in r.keywords.value or []:
                    keyword_values: dict[str, JsonValue] = {
                        "slug": keyword.key,
                        "name": keyword.label,
                    }
                    candidates.append(
                        ProposedEntity(
                            kind="keywords",
                            public_id=keyword.key,
                            record_key=key,
                            source=r.source,
                            fields={
                                k: Patch(state=State.VALUE, value=v)
                                for k, v in keyword_values.items()
                            },
                            importer_fields=keyword_values,
                        )
                    )

    groups: dict[tuple, list[ProposedEntity]] = defaultdict(list)
    for entity in candidates:
        groups[entity.kind, entity.public_id].append(entity)
    for group in groups.values():
        signatures = {encode(e.model_dump(mode="json", exclude={"record_key"})) for e in group}
        if len(signatures) > 1:
            for entity in group:
                reject(entity.record_key, "CONFLICTING_SHARED_ENTITY")
    # Propagate parent projection failures; never orphan an otherwise staging-valid treatment.
    for key, (r, _) in accepted.items():
        if r.treatment is not None and r.treatment.parent_record_key in failed:
            reject(key, "PARENT_NOT_PROJECTABLE")
    entities = {}
    for entity in candidates:
        if entity.record_key not in failed:
            entities[entity.kind, entity.public_id] = entity
    return Projection(
        staging_hash=raw_hash,
        staging_policy_hash=digest(staging_policy.model_dump(mode="json")),
        registry_hash=digest((registry or Registry()).assignments),
        policy_hash=digest(policy.model_dump(mode="json")),
        policy_version=policy.version,
        entities=[entities[k] for k in sorted(entities)],
        rejected=sorted(rejected, key=lambda n: (n.record_key, n.code)),
        warnings=sorted(warnings, key=lambda n: (n.record_key, n.code)),
        evidence=evidence,
    )
