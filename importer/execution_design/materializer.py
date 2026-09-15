"""Private pure materialization helpers. The public entry point is preconditions.prepare_candidate."""

from collections import Counter
from typing import Literal

from pydantic import ConfigDict, JsonValue, model_validator

from importer.projection.canonical import digest, encode
from importer.projection.models import Change, Hash, Kind, Model, Plan
from importer.projection.planner import source_order
from importer.projection.projector import IMPORT_MODELS
from importer.schemas import ImportCatalogue

from .snapshot import SnapshotEnvelope, association_entries, row_fields

Origin = Literal["APPROVED_MODIFICATION", "CARRIED_FORWARD", "APPROVED_IDENTITY"]


class MaterializationError(ValueError):
    """Only safe machine codes cross this boundary."""


class FullEntity(Model):
    kind: Kind
    public_id: str
    owner_id: str | None
    values: dict[str, JsonValue]
    origins: dict[str, Literal["APPROVED_MODIFICATION", "CARRIED_FORWARD", "APPROVED_IDENTITY"]]
    modifications: tuple[Change, ...]


class PayloadContent(Model):
    version: Literal["1"] = "1"
    plan_hash: Hash
    entities: tuple[FullEntity, ...]
    catalogues: tuple[dict[str, JsonValue], ...]
    approved_operations: tuple[Change, ...]
    legacy_schema_compatible: Literal[True] = True
    legacy_writer_safe: Literal[False] = False
    # Empty images/variants/cards containers select no additional child operations.
    container_semantics: Literal["ONLY_APPROVED_CHILD_SELECTIONS"] = (
        "ONLY_APPROVED_CHILD_SELECTIONS"
    )


class MaterializedPayload(Model):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    content_json: str
    payload_hash: Hash

    @model_validator(mode="after")
    def integrity(self):
        value = PayloadContent.model_validate_json(self.content_json).model_dump(mode="json")
        if encode(value) != self.content_json or digest(value) != self.payload_hash:
            raise ValueError("Materialized payload integrity failure")
        return self


def _materialize_exact(plan: Plan, envelope: SnapshotEnvelope) -> MaterializedPayload:
    content = plan.content
    targets = {(e.kind, e.public_id): e for e in content.projection.entities}
    if len(targets) != len(content.projection.entities):
        raise MaterializationError("IDENTITY_REBIND")
    state = {(e.kind, e.public_id): e for e in envelope.state.entities}
    operations = {}
    for operation in content.changes:
        op_key = (operation.kind, operation.public_id, operation.field)
        if op_key in operations or op_key[:2] not in targets:
            raise MaterializationError("UNSUPPORTED_OPERATION")
        if operation.operation == "CONFLICT":
            raise MaterializationError("BLOCKING_CONFLICT")
        operations[op_key] = operation
    if dict(Counter(c.operation for c in content.changes)) != content.expected_operation_counts:
        raise MaterializationError("PLAN_OPERATION_COUNT_MISMATCH")
    if dict(Counter(e.kind for e in targets.values())) != content.expected_entity_counts:
        raise MaterializationError("PLAN_ENTITY_COUNT_MISMATCH")
    expected_keys = {(e.kind, e.public_id, f) for e in targets.values() for f in e.fields}
    expected_keys |= {
        (e.kind, e.public_id, "$owner") for e in targets.values() if e.kind in ("cards", "variants")
    }
    if set(operations) != expected_keys:
        raise MaterializationError("UNSUPPORTED_OPERATION")
    full: dict[tuple[Kind, str], FullEntity] = {}
    for key, entity in sorted(targets.items()):
        old = state.get(key)
        identity_field = "slug" if entity.kind == "keywords" else "id"
        if entity.importer_fields.get(identity_field) != entity.public_id:
            raise MaterializationError("IDENTITY_REBIND")
        if old is not None and old.owner_id != entity.owner_id:
            raise MaterializationError("RELATIONSHIP_CHANGED")
        if entity.kind in ("cards", "variants"):
            owner_op = operations[*key, "$owner"]
            if owner_op.proposed != entity.owner_id or owner_op.operation != (
                "UNCHANGED" if old else "CREATE"
            ):
                raise MaterializationError("IDENTITY_REBIND")
            if owner_op.current != (old.owner_id if old else None):
                raise MaterializationError("RELATIONSHIP_CHANGED")
            owner_kind = "sets" if entity.kind == "cards" else "cards"
            if (owner_kind, entity.owner_id) not in targets:
                raise MaterializationError("RELATIONSHIP_CHANGED")
        values: dict[str, JsonValue] = {identity_field: entity.public_id}
        origins: dict[str, Origin] = {identity_field: "APPROVED_IDENTITY"}
        modifications = []
        for field, patch in entity.fields.items():
            operation = operations[*key, field]
            current = old.values.get(field) if old else None
            if encode(operation.current) != encode(current):
                raise MaterializationError("STATE_CHANGED")
            if operation.source != entity.source:
                raise MaterializationError("SOURCE_BINDING_CHANGED")
            if operation.baseline != (old.baseline.get(field) if old else None):
                raise MaterializationError("STATE_CHANGED")
            if operation.operation in ("CREATE", "UPDATE", "CLEAR"):
                if field not in row_fields(entity.kind):
                    raise MaterializationError("UNSUPPORTED_OPERATION")
                if operation.operation == "CREATE" and old is not None:
                    raise MaterializationError("IDENTITY_REBIND")
                if operation.operation != "CREATE" and old is None:
                    raise MaterializationError("STATE_CHANGED")
                if old is not None:
                    baseline = old.baseline.get(field)
                    if baseline is None:
                        raise MaterializationError("MISSING_FIELD_BASELINE")
                    if encode(current) != encode(baseline.value):
                        raise MaterializationError("CONFLICT_MANUAL_CHANGE")
                    if (
                        source_order(operation.source, baseline.source, content.planning_policy)
                        is not None
                    ):
                        raise MaterializationError("AMBIGUOUS_SOURCE_PRECEDENCE")
                expected = (
                    ([] if field == "keywords" else None)
                    if operation.operation == "CLEAR"
                    else patch.value
                )
                if operation.operation == "CLEAR":
                    if (
                        patch.state != "CLEAR"
                        or not operation.approval_reference
                        or operation.approval_reference != patch.approval_reference
                    ):
                        raise MaterializationError("UNSUPPORTED_OPERATION")
                elif patch.state != "VALUE":
                    raise MaterializationError("UNSUPPORTED_OPERATION")
                if encode(expected) != encode(operation.proposed):
                    raise MaterializationError("PLAN_OPERATION_MISMATCH")
                if (
                    old
                    and field
                    in (
                        "number",
                        "slug",
                        "language",
                        "edition",
                        "collector_number",
                        "type",
                        "finish",
                    )
                    and (
                        entity.kind == "variants"
                        or field in ("number", "slug")
                        or (entity.kind == "sets" and field in ("language", "edition"))
                    )
                    and encode(current) != encode(expected)
                ):
                    raise MaterializationError("IDENTITY_REBIND")
                values[field] = operation.proposed
                origins[field] = "APPROVED_MODIFICATION"
                modifications.append(operation)
            elif operation.operation == "UNCHANGED":
                if old is None or encode(operation.proposed) != encode(current):
                    raise MaterializationError("STATE_CHANGED")
                unchanged_value = (
                    ([] if field == "keywords" else None) if patch.state == "CLEAR" else patch.value
                )
                if patch.state not in ("VALUE", "CLEAR") or encode(unchanged_value) != encode(
                    current
                ):
                    raise MaterializationError("PLAN_OPERATION_MISMATCH")
            elif operation.operation == "SKIP":
                if patch.state not in ("ABSENT", "UNKNOWN") and not (
                    patch.state == "CLEAR"
                    and old is None
                    and operation.reason == "CLEAR_ON_NEW_ENTITY"
                ):
                    raise MaterializationError("UNSUPPORTED_OPERATION")
            else:
                raise MaterializationError("UNSUPPORTED_OPERATION")
        for field in sorted(row_fields(entity.kind)):
            if field in values:
                continue
            if old is None or field not in old.values:
                required = IMPORT_MODELS[entity.kind].model_fields[field].is_required()
                raise MaterializationError(
                    "MISSING_REQUIRED_CREATE_FIELD" if required else "LEGACY_SCHEMA_INCOMPATIBLE"
                )
            values[field] = old.values[field]
            origins[field] = "CARRIED_FORWARD"
        if entity.kind == "cards" and values["number"] != entity.importer_fields["number"]:
            raise MaterializationError("IDENTITY_REBIND")
        if entity.kind == "keywords" and values["slug"] != entity.public_id:
            raise MaterializationError("IDENTITY_REBIND")
        try:
            # Explicit containers are operation selections, not row values/default updates.
            validation = dict(values)
            for container in {
                "sets": ("cards",),
                "cards": ("variants", "images"),
                "variants": ("images",),
                "keywords": (),
            }[entity.kind]:
                validation[container] = []
            checked = IMPORT_MODELS[entity.kind].model_validate(validation).model_dump(mode="json")
            if encode(checked) != encode(validation):
                raise ValueError("Legacy normalization changed meaning")
        except ValueError:
            raise MaterializationError("LEGACY_SCHEMA_INCOMPATIBLE") from None
        full[key] = FullEntity(
            kind=entity.kind,
            public_id=entity.public_id,
            owner_id=entity.owner_id,
            values=values,
            origins=origins,
            modifications=tuple(modifications),
        )
    # Validate all scoped current relationships as well as future approved ownership.
    for old in state.values():
        if old.kind in ("cards", "variants"):
            parent_kind = "sets" if old.kind == "cards" else "cards"
            if (parent_kind, old.owner_id) not in state:
                raise MaterializationError("RELATIONSHIP_CHANGED")
        if old.kind == "cards":
            for keyword in association_entries(old.values.get("keywords")):
                target = state.get(("keywords", keyword["slug"]))
                if target is None or target.values.get("name") != keyword["name"]:
                    raise MaterializationError("RELATIONSHIP_CHANGED")
    catalogues: list[dict[str, JsonValue]] = []
    for key, st in sorted(full.items()):
        if st.kind != "sets":
            continue
        source = targets[key].source
        set_value = dict(st.values)
        cards: list[JsonValue] = []
        for card_key, card in sorted(full.items()):
            if card.kind != "cards" or card.owner_id != st.public_id:
                continue
            if targets[card_key].source != source:
                raise MaterializationError("AMBIGUOUS_SOURCE_PRECEDENCE")
            card_value = dict(card.values)
            variants: list[JsonValue] = []
            for variant_key, variant in sorted(full.items()):
                if variant.kind == "variants" and variant.owner_id == card.public_id:
                    if targets[variant_key].source != source:
                        raise MaterializationError("AMBIGUOUS_SOURCE_PRECEDENCE")
                    variants.append({**variant.values, "images": []})
            card_value.update(variants=variants, images=[])
            cards.append(card_value)
        set_value["cards"] = cards
        catalogue: dict[str, JsonValue] = {
            "source": source.model_dump(
                mode="json", exclude={"revision", "content_hash", "authority"}
            ),
            "variant_aliases": {},
            "sets": [set_value],
        }
        try:
            if encode(ImportCatalogue.model_validate(catalogue).model_dump(mode="json")) != encode(
                catalogue
            ):
                raise ValueError("Legacy coercion")
        except ValueError:
            raise MaterializationError("LEGACY_SCHEMA_INCOMPATIBLE") from None
        catalogues.append(catalogue)
    payload = PayloadContent(
        plan_hash=plan.plan_hash,
        entities=tuple(full[k] for k in sorted(full)),
        catalogues=tuple(catalogues),
        approved_operations=tuple(content.changes),
    )
    data = payload.model_dump(mode="json")
    return MaterializedPayload(content_json=encode(data), payload_hash=digest(data))
