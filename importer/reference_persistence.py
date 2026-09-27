"""Transactional persistence for approved curated Printing references."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Card,
    CardVariant,
    Edition,
    EditionCollectorSnapshot,
    PrintingReference,
    SourceRecord,
)
from importer.catalogue_persistence import _require_equal
from importer.reference_catalogue import REFERENCE_SOURCE, ReferenceReconciliationError

WORKBOOK_IDENTITY_SCHEMA_VERSION = "printing-reference-set-v1"


def _workbook_identity_digest(edition_public_id: str, identities: list[dict[str, str]]) -> str:
    payload = {
        "edition_public_id": edition_public_id,
        "expected_printing_count": 396,
        "identity_schema_version": WORKBOOK_IDENTITY_SCHEMA_VERSION,
        "identities": sorted(identities, key=lambda item: item["reference_key"]),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ensure_workbook_snapshot(session: Session, edition: Edition, source_hash: str) -> None:
    snapshot = session.scalar(
        select(EditionCollectorSnapshot).where(
            EditionCollectorSnapshot.edition_id == edition.id,
            EditionCollectorSnapshot.source_type == "CURATED_WORKBOOK",
            EditionCollectorSnapshot.source_snapshot_sha256 == source_hash,
        )
    )
    rows = session.execute(
        select(PrintingReference, CardVariant)
        .join(CardVariant, CardVariant.id == PrintingReference.printing_id)
        .where(
            CardVariant.edition_id == edition.id,
            PrintingReference.source_name == REFERENCE_SOURCE,
        )
        .order_by(PrintingReference.reference_key)
    ).all()
    if len(rows) != 396 or len({reference.reference_key for reference, _ in rows}) != 396:
        raise ReferenceReconciliationError("REFERENCE_SNAPSHOT_NOT_COMPLETE")
    if len({printing.id for _, printing in rows}) != 396:
        raise ReferenceReconciliationError("REFERENCE_PRINTING_REUSED")

    identities = []
    for reference, printing in rows:
        fingerprint = hashlib.sha256(printing.public_id.encode("utf-8")).hexdigest()
        if reference.source_sha256 != source_hash:
            raise ReferenceReconciliationError("REFERENCE_SOURCE_HASH_MISMATCH")
        reference.semantic_fingerprint = fingerprint
        identities.append(
            {
                "reference_key": reference.reference_key,
                "semantic_fingerprint": fingerprint,
                "printing_public_id": printing.public_id,
            }
        )
    digest = _workbook_identity_digest(edition.public_id, identities)
    if snapshot is None:
        snapshot = EditionCollectorSnapshot(
            edition_id=edition.id,
            set_id=edition.set_id,
            source_type="CURATED_WORKBOOK",
            source_url="data/reference/konoha_shido_1st_edition_master.json",
            source_snapshot_sha256=source_hash,
            expected_printing_count=396,
            identity_digest=digest,
            identity_schema_version=WORKBOOK_IDENTITY_SCHEMA_VERSION,
            exhaustive=False,
        )
        session.add(snapshot)
        session.flush()
    elif snapshot.identity_digest != digest or snapshot.expected_printing_count != 396:
        raise ReferenceReconciliationError("EXISTING_WORKBOOK_SNAPSHOT_CONFLICT")
    for reference, _ in rows:
        if reference.snapshot_id not in (None, snapshot.id):
            raise ReferenceReconciliationError("REFERENCE_BOUND_TO_OTHER_SNAPSHOT")
        reference.snapshot_id = snapshot.id


@dataclass(frozen=True)
class ReferencePersistenceCounts:
    canonical_cards: int
    upstream_printings: int
    curated_reference_entries: int
    curated_reference_only_printings: int
    upstream_and_curated_printings: int
    upstream_only_printings: int
    total_printings: int


REFERENCE_FIELDS = (
    "printing_id",
    "source_sha256",
    "worksheet",
    "workbook_row",
    "collector_number",
    "card_name",
    "rarity_raw",
    "variant_raw",
    "normalized_rarity",
    "collector_class",
    "normalized_treatment",
)


def _reference_values(item: dict[str, Any], printing: CardVariant) -> dict[str, Any]:
    taxonomy = item["taxonomy"]
    return {
        "printing_id": printing.id,
        "source_sha256": item["source_sha256"],
        "worksheet": item["worksheet"],
        "workbook_row": item["workbook_row"],
        "collector_number": item["collector_number"],
        "card_name": item["card_name"],
        "rarity_raw": item["rarity_raw"],
        "variant_raw": item["variant_raw"],
        "normalized_rarity": taxonomy["normalized_rarity"],
        "collector_class": taxonomy["collector_class"],
        "normalized_treatment": taxonomy["normalized_treatment"],
    }


def _attach_reference(
    session: Session,
    item: dict[str, Any],
    printing: CardVariant,
) -> None:
    expected = _reference_values(item, printing)
    reference = session.scalar(
        select(PrintingReference).where(
            PrintingReference.source_name == REFERENCE_SOURCE,
            PrintingReference.reference_key == item["reference_key"],
        )
    )
    if reference is None:
        session.add(
            PrintingReference(
                source_name=REFERENCE_SOURCE,
                reference_key=item["reference_key"],
                **expected,
            )
        )
        session.flush()
        return
    for field, value in expected.items():
        _require_equal(reference, field, value)


def _require_upstream_provenance(session: Session, printing: CardVariant, source_uid: int) -> None:
    provenance = session.scalar(
        select(SourceRecord).where(
            SourceRecord.printing_id == printing.id,
            SourceRecord.source_uid == str(source_uid),
        )
    )
    if provenance is None:
        raise ReferenceReconciliationError("UPSTREAM_PRINTING_PROVENANCE_MISSING")


def _get_curated_printing(
    session: Session,
    item: dict[str, Any],
    card: Card,
    edition: Edition,
) -> CardVariant:
    public_id = item["printing_public_id"]
    reference_identity = item["reference_identity"]
    taxonomy = item["taxonomy"]
    values = {
        "public_id": public_id,
        "reference_identity": reference_identity,
        "card_id": card.id,
        "set_id": card.set_id,
        "edition_id": edition.id,
        "variant_type": "curated-reference",
        "finish": None,
        "rarity_override": None,
        "collector_number": item["collector_number"],
        "language": "EN",
        "edition": edition.name,
        "source_variant": None,
        "card_version": None,
        "stamp": None,
        "normalized_rarity": taxonomy["normalized_rarity"],
        "collector_class": taxonomy["collector_class"],
        "normalized_treatment": taxonomy["normalized_treatment"],
        "rarity_resolution_status": taxonomy["rarity_resolution_status"],
        "variant_resolution_status": taxonomy["variant_resolution_status"],
        "serial_numbered": None,
        "serial_total": None,
    }
    printing = session.scalar(select(CardVariant).where(CardVariant.public_id == public_id))
    if printing is None:
        existing_identity = session.scalar(
            select(CardVariant).where(CardVariant.reference_identity == reference_identity)
        )
        if existing_identity is not None:
            raise ReferenceReconciliationError("CURATED_IDENTITY_ALREADY_BOUND_TO_OTHER_PRINTING")
        printing = CardVariant(**values)
        session.add(printing)
        session.flush()
    else:
        for field, expected in values.items():
            _require_equal(printing, field, expected)
    if printing.images:
        raise ReferenceReconciliationError("CURATED_PRINTING_MUST_NOT_INHERIT_IMAGES")
    if printing.translations:
        raise ReferenceReconciliationError("CURATED_PRINTING_MUST_NOT_INHERIT_TRANSLATIONS")
    return printing


def persist_reference_reconciliation(
    session: Session, reconciliation: dict[str, Any]
) -> ReferencePersistenceCounts:
    """Persist references and missing curated Printings in one caller-owned transaction."""
    if reconciliation.get("ambiguities"):
        raise ReferenceReconciliationError("UNRESOLVED_REFERENCE_AMBIGUITIES")
    if reconciliation.get("counts", {}).get("konoha_1e_checklist_count") != 396:
        raise ReferenceReconciliationError("REFERENCE_COUNT_MISMATCH")

    if session.in_transaction():
        session.rollback()
    try:
        with session.begin():
            edition_public_ids = {
                item["edition_public_id"]
                for item in reconciliation["matches"] + reconciliation["curated_printings"]
            }
            if len(edition_public_ids) != 1:
                raise ReferenceReconciliationError("REFERENCE_EDITION_SCOPE_MISMATCH")
            edition = session.scalar(
                select(Edition).where(Edition.public_id == next(iter(edition_public_ids)))
            )
            if edition is None:
                raise ReferenceReconciliationError("TARGET_EDITION_NOT_PERSISTED")

            for item in reconciliation["matches"]:
                printing = session.scalar(
                    select(CardVariant).where(CardVariant.public_id == item["printing_public_id"])
                )
                if printing is None:
                    raise ReferenceReconciliationError("MATCHED_UPSTREAM_PRINTING_NOT_PERSISTED")
                if printing.edition_id != edition.id:
                    raise ReferenceReconciliationError("MATCHED_PRINTING_EDITION_MISMATCH")
                _require_upstream_provenance(session, printing, item["source_uid"])
                _attach_reference(session, item, printing)

            for item in reconciliation["curated_printings"]:
                card = session.scalar(select(Card).where(Card.public_id == item["card_public_id"]))
                if card is None:
                    raise ReferenceReconciliationError("CANONICAL_CARD_NOT_PERSISTED")
                if card.set_id != edition.set_id:
                    raise ReferenceReconciliationError("CURATED_PRINTING_CARD_SET_MISMATCH")
                printing = _get_curated_printing(session, item, card, edition)
                if (
                    session.scalar(
                        select(SourceRecord.id)
                        .where(SourceRecord.printing_id == printing.id)
                        .limit(1)
                    )
                    is not None
                ):
                    raise ReferenceReconciliationError("CURATED_PRINTING_HAS_UPSTREAM_PROVENANCE")
                _attach_reference(session, item, printing)

            source_hashes = {
                item["source_sha256"]
                for item in reconciliation["matches"] + reconciliation["curated_printings"]
            }
            if len(source_hashes) != 1:
                raise ReferenceReconciliationError("REFERENCE_SOURCE_HASH_INCONSISTENT")
            _ensure_workbook_snapshot(session, edition, next(iter(source_hashes)))

        return count_reference_catalogue(session)
    except Exception:
        session.rollback()
        raise


def count_reference_catalogue(session: Session) -> ReferencePersistenceCounts:
    upstream_ids = select(SourceRecord.printing_id).where(SourceRecord.printing_id.is_not(None))
    curated_only_ids = (
        session.scalar(
            select(func.count(func.distinct(PrintingReference.printing_id))).where(
                ~PrintingReference.printing_id.in_(upstream_ids)
            )
        )
        or 0
    )
    upstream_and_curated = (
        session.scalar(
            select(func.count(func.distinct(PrintingReference.printing_id))).where(
                PrintingReference.printing_id.in_(upstream_ids)
            )
        )
        or 0
    )
    upstream_count = (
        session.scalar(
            select(func.count(func.distinct(SourceRecord.printing_id))).where(
                SourceRecord.printing_id.is_not(None)
            )
        )
        or 0
    )
    return ReferencePersistenceCounts(
        canonical_cards=session.scalar(select(func.count()).select_from(Card)) or 0,
        upstream_printings=upstream_count,
        curated_reference_entries=session.scalar(
            select(func.count()).select_from(PrintingReference)
        )
        or 0,
        curated_reference_only_printings=curated_only_ids,
        upstream_and_curated_printings=upstream_and_curated,
        upstream_only_printings=upstream_count - upstream_and_curated,
        total_printings=session.scalar(select(func.count()).select_from(CardVariant)) or 0,
    )


def printing_origin(session: Session, printing_id: Any) -> str:
    """Derive controlled origin from upstream provenance and curated references."""
    has_upstream = (
        session.scalar(
            select(SourceRecord.id).where(SourceRecord.printing_id == printing_id).limit(1)
        )
        is not None
    )
    has_reference = (
        session.scalar(
            select(PrintingReference.id)
            .where(PrintingReference.printing_id == printing_id)
            .limit(1)
        )
        is not None
    )
    if has_upstream and has_reference:
        return "UPSTREAM_AND_CURATED"
    if has_upstream:
        return "UPSTREAM"
    if has_reference:
        return "CURATED_REFERENCE"
    raise ReferenceReconciliationError("PRINTING_HAS_NO_PROVENANCE_ORIGIN")
