"""Version 2 Card/Printing staging. Version 1 contracts remain readable, never rehashed.

No writer, network or database. Acceptance is not approval or execution authorization.
"""

from collections import defaultdict
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, field_validator

from importer.catalogue_design.identity import CanonicalCardKey, CanonicalPrintingKey

from .identity import Registry, canonical
from .models import (
    FieldValue,
    Language,
    Model,
    Nonnegative,
    PublicID,
    Record,
    SignedPower,
    Source,
    Text,
)

Short = Annotated[str, Field(strict=True, min_length=1, max_length=64)]


class PrintingFingerprint(Model):
    expansion: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    edition: Short | None
    printed_identifier: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    rarity: Short
    variant: Short | None
    card_version: Short | None
    stamp: Annotated[str, Field(strict=True, min_length=1, max_length=255)] | None

    @field_validator("*")
    @classmethod
    def no_silent_normalization(cls, value):
        if isinstance(value, str) and value != value.strip():
            raise ValueError("Identity values require explicit whitespace review")
        return value

    def key(self) -> CanonicalPrintingKey:
        return CanonicalPrintingKey(**self.model_dump())

    def card_key(self) -> CanonicalCardKey:
        return CanonicalCardKey(self.expansion, self.printed_identifier)


class PrintingRecord(Model):
    schema_version: Literal["2"] = "2"
    kind: Literal["PRINTING"] = "PRINTING"
    record_key: Text
    identity: PrintingFingerprint
    language: Language
    source: Source
    source_uid: Text | None = None
    source_sku: Text | None = None
    # Presentation/gameplay stay sparse; null never implies CLEAR.
    title: FieldValue[Text] = Field(default_factory=FieldValue)
    rules_text: FieldValue[Text] = Field(default_factory=FieldValue)
    card_type: FieldValue[Short] = Field(default_factory=FieldValue)
    chakra: FieldValue[Nonnegative] = Field(default_factory=FieldValue)
    power: FieldValue[SignedPower] = Field(default_factory=FieldValue)
    points: FieldValue[Nonnegative] = Field(default_factory=FieldValue)
    review_status: Literal["UNREVIEWED", "APPROVED", "REJECTED"] = "UNREVIEWED"
    existing_public_id: PublicID | None = None

    @field_validator("title", "rules_text", "card_type", "chakra", "power", "points", mode="before")
    @classmethod
    def null_is_unknown(cls, value):
        return {"state": "UNKNOWN"} if value is None else value


class DomainValidation(Model):
    accepted: dict[str, str]
    quarantined: dict[str, list[str]]
    production_execution_authorized: Literal[False] = False


def validate_printings(
    records: list[PrintingRecord], registry: Registry | None = None
) -> DomainValidation:
    """Quarantine all conflicts, including cross-record Card grouping disagreements."""
    records = [PrintingRecord.model_validate(r.model_dump()) for r in records]
    registry = registry or Registry()
    reasons: dict[str, list[str]] = defaultdict(list)
    groups: dict[tuple[str, str, str], list[PrintingRecord]] = defaultdict(list)
    identities: dict[str, list[PrintingRecord]] = defaultdict(list)
    keys: dict[str, int] = defaultdict(int)
    accepted = {}
    proposed_identities: dict[str, set[str]] = defaultdict(set)
    record_identities = {}
    for r in records:
        keys[r.record_key] += 1
        identity = r.identity.key()
        fingerprint = identity.payload()
        encoded = canonical(fingerprint)
        record_identities[r.record_key] = encoded
        identities[encoded].append(r)
        groups[r.identity.expansion, r.identity.printed_identifier, r.language].append(r)
        public_id = registry.assignments.get(encoded, identity.analysis_public_id())
        proposed_identities[public_id].add(encoded)
        try:
            TypeAdapter(PublicID).validate_python(public_id)
        except ValidationError:
            reasons[r.record_key].append("INVALID_PUBLIC_ID")
        if r.existing_public_id and registry.assignments.get(encoded) != r.existing_public_id:
            reasons[r.record_key].append("EXISTING_ID_NOT_REGISTERED")
        if any(k != encoded and v == public_id for k, v in registry.assignments.items()):
            reasons[r.record_key].append("PUBLIC_ID_COLLISION")
        if r.review_status != "APPROVED":
            reasons[r.record_key].append("UNRESOLVED_REVIEW")
        accepted[r.record_key] = public_id
    for key, public_id in accepted.items():
        if len(proposed_identities[public_id]) != 1:
            reasons[key].append("PUBLIC_ID_COLLISION")
    for group in identities.values():
        # Localized observations may share identity, but not duplicate a language observation.
        langs = [r.language for r in group]
        for r in group:
            if langs.count(r.language) > 1:
                reasons[r.record_key].append("DUPLICATE_IDENTITY")
    for group in groups.values():
        for field in ("title", "card_type", "points"):
            values = {getattr(r, field).value for r in group if getattr(r, field).state == "VALUE"}
            if len(values) > 1:
                for r in group:
                    reasons[r.record_key].append("CARD_GROUPING_CONFLICT")
    for key, count in keys.items():
        if count > 1:
            reasons[key].append("DUPLICATE_RECORD_KEY")
    return DomainValidation(
        accepted={k: v for k, v in accepted.items() if k not in reasons},
        quarantined={k: sorted(set(v)) for k, v in reasons.items()},
    )


LegacyRecord = Record  # Explicitly version 1: PRINTING/TREATMENT names have old semantics.
