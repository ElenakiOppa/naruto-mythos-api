"""Deterministic verification and persistence for official Edition references.

The reconciliation path is read-only. Persistence is an explicit second step
that only attaches official references to already-existing upstream Printings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Card,
    CardImage,
    CardSet,
    CardVariant,
    Edition,
    EditionCollectorSnapshot,
    PrintingReference,
    SourceRecord,
)
from app.utils.edition_identity import normalize_edition_name
from app.utils.printing_taxonomy import normalize_printing_taxonomy
from importer.catalogue_design.identity import CanonicalCardKey, CanonicalPrintingKey
from importer.catalogue_design.models import SourceCardRecord

OFFICIAL_REFERENCE_SOURCE = "naruto_mythos_official_gallery"
OFFICIAL_SOURCE_TYPE = "OFFICIAL_GALLERY_API"
OFFICIAL_API_BASE = "https://cards.narutotcgmythos.com/api/cards"
OFFICIAL_GALLERY_PROXY_BASE = "https://services.agenziamarketingcarpi.it/proxy/naruto/proxy.php"
IDENTITY_SCHEMA_VERSION = "semantic-printing-reference-v1"
SNAPSHOT_DIGEST_SCHEMA_VERSION = "printing-reference-set-v1"
WORKBOOK_REFERENCE_COUNT = 396
EXPECTED_OFFICIAL_EDITIONS = {
    ("Set 1: Konoha Shidō", "2nd edition"): 187,
    ("Set 2: Shinobi Shiren", "1st edition"): 242,
}


class OfficialEditionReconciliationError(ValueError):
    """Official Edition data does not match a complete persisted Printing set."""


@dataclass(frozen=True)
class EditionVerification:
    verified: bool
    reference_count: int
    expected_count: int | None
    reason: str | None
    snapshot_id: Any | None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _raw_identity(record: SourceCardRecord) -> CanonicalPrintingKey:
    return CanonicalPrintingKey.from_record(record)


def _database_identity(printing: CardVariant) -> CanonicalPrintingKey:
    if printing.card is None or printing.card.set is None:
        raise OfficialEditionReconciliationError("PRINTING_CARD_OR_SET_MISSING")
    edition_name = printing.edition_record.name if printing.edition_record else None
    if edition_name is None or printing.rarity_override is None:
        raise OfficialEditionReconciliationError("PRINTING_IDENTITY_FIELDS_MISSING")
    return CanonicalPrintingKey(
        expansion=printing.card.set.name,
        edition=normalize_edition_name(edition_name),
        printed_identifier=printing.card.card_number,
        rarity=printing.rarity_override,
        variant=printing.source_variant,
        card_version=printing.card_version,
        stamp=printing.stamp or None,
    )


def _edition_digest(
    edition_public_id: str,
    expected_count: int,
    identity_schema_version: str,
    identities: list[dict[str, str]],
) -> str:
    payload = {
        "edition_public_id": edition_public_id,
        "expected_printing_count": expected_count,
        "identity_schema_version": identity_schema_version,
        "identities": sorted(identities, key=lambda item: item["reference_key"]),
    }
    return _sha256(payload)


def _target_edition(session: Session, set_name: str, edition_name: str) -> Edition:
    edition = session.scalar(
        select(Edition)
        .options(joinedload(Edition.set))
        .join(CardSet, CardSet.id == Edition.set_id)
        .where(
            CardSet.name == set_name,
            Edition.normalized_name == normalize_edition_name(edition_name),
        )
    )
    if edition is None or edition.set.name != set_name:
        raise OfficialEditionReconciliationError("TARGET_EDITION_NOT_PERSISTED")
    return edition


def _validate_localizations(
    records_by_language: dict[str, list[SourceCardRecord]],
    target_rows: list[SourceCardRecord],
    set_name: str,
    edition_name: str,
) -> None:
    english_uids = {record.uid for record in target_rows}
    for language, records in records_by_language.items():
        target = [
            record
            for record in records
            if record.set == set_name and (record.edition or "").strip() == edition_name
        ]
        if {record.uid for record in target} != english_uids:
            raise OfficialEditionReconciliationError(
                f"LOCALIZATION_IDENTITY_SET_MISMATCH:{language}"
            )
        by_uid = {record.uid: record for record in target}
        for source in target_rows:
            localized = by_uid.get(source.uid)
            if localized is None:
                raise OfficialEditionReconciliationError(f"LOCALIZATION_UID_MISSING:{language}")
            fields = ("set", "edition", "id", "rarity", "variant", "card_version", "stamp", "sku")
            if any(getattr(source, field) != getattr(localized, field) for field in fields):
                raise OfficialEditionReconciliationError(
                    f"LOCALIZATION_PRINTING_IDENTITY_MISMATCH:{language}"
                )


def _source_provenance_matches(
    session: Session, printing: CardVariant, record: SourceCardRecord
) -> bool:
    return (
        session.scalar(
            select(SourceRecord.id).where(
                SourceRecord.printing_id == printing.id,
                SourceRecord.source_uid == str(record.uid),
                SourceRecord.source_sku == record.sku,
            )
        )
        is not None
    )


def _official_reference_data(
    record: SourceCardRecord,
    printing: CardVariant,
    snapshot_hash: str,
) -> dict[str, Any]:
    taxonomy = normalize_printing_taxonomy(record.rarity, record.variant, record.card_type)
    reference_key = f"{snapshot_hash[:16]}:{record.uid}"
    return {
        "printing": printing,
        "snapshot_id": None,
        "source_name": OFFICIAL_REFERENCE_SOURCE,
        "reference_key": reference_key,
        "source_sha256": snapshot_hash,
        "worksheet": None,
        "workbook_row": None,
        "source_uid": str(record.uid),
        "source_sku": record.sku,
        "semantic_fingerprint": _raw_identity(record).identity_hash(),
        "collector_number": record.id,
        "card_name": record.title or "Unnamed card",
        "rarity_raw": record.rarity or "",
        "variant_raw": record.variant or "",
        "normalized_rarity": taxonomy.normalized_rarity,
        "collector_class": taxonomy.collector_class,
        "normalized_treatment": taxonomy.normalized_treatment or "Unspecified",
        "image_url": record.image,
    }


def build_official_edition_reconciliation(
    session: Session,
    records_by_language: dict[str, list[SourceCardRecord]],
    *,
    set_name: str,
    edition_name: str,
    source_snapshot_sha256: str,
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Compare one official Edition snapshot against existing DB Printings; no writes."""
    expected_count = EXPECTED_OFFICIAL_EDITIONS.get((set_name, edition_name))
    if expected_count is None:
        raise OfficialEditionReconciliationError("UNAPPROVED_OFFICIAL_EDITION")
    if len(source_snapshot_sha256) != 64:
        raise OfficialEditionReconciliationError("INVALID_SOURCE_SNAPSHOT_HASH")
    if not records_by_language or "en" not in records_by_language:
        raise OfficialEditionReconciliationError("MISSING_ENGLISH_SOURCE_SNAPSHOT")

    records = records_by_language["en"]
    rows = [
        record
        for record in records
        if record.set == set_name and (record.edition or "").strip() == edition_name
    ]
    if len(rows) != expected_count:
        raise OfficialEditionReconciliationError("OFFICIAL_PRINTING_COUNT_MISMATCH")
    _validate_localizations(records_by_language, rows, set_name, edition_name)
    if any(record.uid is None or not record.sku for record in rows):
        raise OfficialEditionReconciliationError("OFFICIAL_UID_OR_SKU_MISSING")
    if len({record.uid for record in rows}) != len(rows):
        raise OfficialEditionReconciliationError("DUPLICATE_OFFICIAL_UID")
    if len({record.sku for record in rows}) != len(rows):
        raise OfficialEditionReconciliationError("DUPLICATE_OFFICIAL_SKU")

    identities = [_raw_identity(record) for record in rows]
    fingerprints = [identity.identity_hash() for identity in identities]
    if len(set(fingerprints)) != len(rows):
        raise OfficialEditionReconciliationError("DUPLICATE_SEMANTIC_PRINTING_IDENTITY")

    edition = _target_edition(session, set_name, edition_name)
    reconciliation_rows: list[dict[str, Any]] = []
    matched_public_ids: set[str] = set()
    matched_database_printing_ids: set[Any] = set()
    conflicts: list[dict[str, Any]] = []
    official_only: list[dict[str, Any]] = []
    provenance_rows = session.execute(
        select(SourceRecord.source_uid, SourceRecord.source_sku, CardVariant.id)
        .join(CardVariant, CardVariant.id == SourceRecord.printing_id)
        .where(CardVariant.edition_id == edition.id, SourceRecord.printing_id.is_not(None))
    ).all()
    database_by_uid: dict[str, set[tuple[Any, str | None]]] = {}
    for source_uid, source_sku, printing_id in provenance_rows:
        if source_uid is not None:
            database_by_uid.setdefault(source_uid, set()).add((printing_id, source_sku))
    for record, identity in zip(rows, identities, strict=True):
        public_id = identity.analysis_public_id()
        printing = session.scalar(
            select(CardVariant)
            .options(
                joinedload(CardVariant.card).joinedload(Card.set),
                joinedload(CardVariant.edition_record),
            )
            .where(CardVariant.public_id == public_id)
        )
        if printing is None:
            source_candidates = database_by_uid.get(str(record.uid), set())
            if source_candidates:
                candidate_ids = {printing_id for printing_id, _ in source_candidates}
                matched_database_printing_ids.update(candidate_ids)
                conflicts.append(
                    {
                        "uid": record.uid,
                        "sku": record.sku,
                        "expected_public_id": public_id,
                        "database_public_ids": sorted(
                            session.scalars(
                                select(CardVariant.public_id).where(
                                    CardVariant.id.in_(candidate_ids)
                                )
                            ).all()
                        ),
                        "identity_matches": False,
                    }
                )
            else:
                official_only.append({"uid": record.uid, "sku": record.sku, "public_id": public_id})
            continue
        matched_database_printing_ids.add(printing.id)
        try:
            db_identity = _database_identity(printing)
        except OfficialEditionReconciliationError:
            conflicts.append({"uid": record.uid, "sku": record.sku, "public_id": public_id})
            continue
        identity_matches = db_identity.payload() == identity.payload()
        owner_matches = (
            printing.edition_id == edition.id
            and printing.card.set_id == edition.set_id
            and printing.card.card_number == record.id
            and printing.card.public_id
            == CanonicalCardKey(set_name, record.id).analysis_public_id()
        )
        raw_fields_match = (
            printing.rarity_override == record.rarity
            and printing.source_variant == record.variant
            and printing.card_version == record.card_version
            and (printing.stamp or None) == (record.stamp or None)
        )
        provenance_matches = _source_provenance_matches(session, printing, record)
        image_matches = (
            bool(record.image)
            and session.scalar(
                select(CardImage.id).where(
                    CardImage.variant_id == printing.id,
                    CardImage.url == record.image,
                )
            )
            is not None
        )
        if not (
            identity_matches
            and owner_matches
            and raw_fields_match
            and provenance_matches
            and image_matches
        ):
            conflicts.append(
                {
                    "uid": record.uid,
                    "sku": record.sku,
                    "public_id": public_id,
                    "identity_matches": identity_matches,
                    "owner_matches": owner_matches,
                    "raw_fields_match": raw_fields_match,
                    "provenance_matches": provenance_matches,
                    "image_matches": image_matches,
                }
            )
            continue
        matched_public_ids.add(public_id)
        reconciliation_rows.append(
            _official_reference_data(record, printing, source_snapshot_sha256)
        )

    edition_printings = list(
        session.scalars(select(CardVariant.id).where(CardVariant.edition_id == edition.id)).all()
    )
    database_only_count = len(set(edition_printings) - matched_database_printing_ids)
    if database_only_count:
        conflicts.append({"code": "DATABASE_ONLY_PRINTINGS", "count": database_only_count})

    identities_for_digest = [
        {
            "reference_key": row["reference_key"],
            "semantic_fingerprint": row["semantic_fingerprint"],
            "source_uid": row["source_uid"],
            "source_sku": row["source_sku"],
            "printing_public_id": row["printing"].public_id,
        }
        for row in reconciliation_rows
    ]
    identity_digest = _edition_digest(
        edition.public_id,
        expected_count,
        IDENTITY_SCHEMA_VERSION,
        identities_for_digest,
    )
    return {
        "edition": edition,
        "set_name": set_name,
        "edition_name": edition_name,
        "source_snapshot_sha256": source_snapshot_sha256,
        "retrieved_at": retrieved_at,
        "expected_printing_count": expected_count,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "identity_digest": identity_digest,
        "references": reconciliation_rows,
        "counts": {
            "official_source_rows": len(rows),
            "matched_existing_printings": len(matched_public_ids),
            "official_only": len(official_only),
            "database_only": database_only_count,
            "identity_conflicts": len(conflicts),
            "duplicate_semantic_identities": len(rows) - len(set(fingerprints)),
        },
        "official_only_rows": official_only,
        "conflicts": conflicts,
    }


def _latest_snapshot(session: Session, edition: Edition) -> EditionCollectorSnapshot | None:
    return session.scalar(
        select(EditionCollectorSnapshot)
        .where(EditionCollectorSnapshot.edition_id == edition.id)
        .order_by(EditionCollectorSnapshot.created_at.desc(), EditionCollectorSnapshot.id.desc())
        .limit(1)
    )


def _snapshot_rows(session: Session, snapshot: EditionCollectorSnapshot) -> list[PrintingReference]:
    return list(
        session.scalars(
            select(PrintingReference)
            .options(
                joinedload(PrintingReference.printing)
                .joinedload(CardVariant.card)
                .joinedload(Card.set),
                joinedload(PrintingReference.printing).joinedload(CardVariant.edition_record),
                joinedload(PrintingReference.printing).selectinload(CardVariant.images),
                joinedload(PrintingReference.printing).selectinload(CardVariant.source_records),
            )
            .where(PrintingReference.snapshot_id == snapshot.id)
            .order_by(PrintingReference.reference_key)
        ).all()
    )


def verify_edition_collector_snapshot(session: Session, edition: Edition) -> EditionVerification:
    snapshot = _latest_snapshot(session, edition)
    if snapshot is None:
        return EditionVerification(False, 0, None, "SNAPSHOT_MISSING", None)
    references = _snapshot_rows(session, snapshot)
    expected = snapshot.expected_printing_count
    if expected <= 0 or len(snapshot.source_snapshot_sha256) != 64:
        return EditionVerification(
            False, len(references), expected, "SNAPSHOT_INVALID", snapshot.id
        )
    if len(references) != expected:
        return EditionVerification(
            False, len(references), expected, "REFERENCE_COUNT_MISMATCH", snapshot.id
        )
    if len({reference.reference_key for reference in references}) != expected:
        return EditionVerification(
            False, len(references), expected, "DUPLICATE_REFERENCE_KEY", snapshot.id
        )
    if len({reference.printing_id for reference in references}) != expected:
        return EditionVerification(
            False, len(references), expected, "DUPLICATE_PRINTING_REFERENCE", snapshot.id
        )
    if any(reference.source_sha256 != snapshot.source_snapshot_sha256 for reference in references):
        return EditionVerification(
            False, len(references), expected, "REFERENCE_SNAPSHOT_HASH_MISMATCH", snapshot.id
        )

    identities: list[dict[str, str]] = []
    if snapshot.source_type == OFFICIAL_SOURCE_TYPE:
        target_count = EXPECTED_OFFICIAL_EDITIONS.get((edition.set.name, edition.normalized_name))
        if (
            target_count is None
            or snapshot.expected_printing_count != target_count
            or snapshot.source_url != OFFICIAL_API_BASE
            or snapshot.transport_url != OFFICIAL_GALLERY_PROXY_BASE
            or snapshot.retrieved_at is None
            or snapshot.identity_schema_version != IDENTITY_SCHEMA_VERSION
        ):
            return EditionVerification(
                False, len(references), expected, "OFFICIAL_SNAPSHOT_INVALID", snapshot.id
            )
        if any(
            not ref.source_uid or not ref.source_sku or not ref.semantic_fingerprint
            for ref in references
        ):
            return EditionVerification(
                False, len(references), expected, "OFFICIAL_PROVENANCE_MISSING", snapshot.id
            )
        if (
            len({ref.source_uid for ref in references}) != expected
            or len({ref.source_sku for ref in references}) != expected
            or len({ref.semantic_fingerprint for ref in references}) != expected
        ):
            return EditionVerification(
                False, len(references), expected, "DUPLICATE_OFFICIAL_SOURCE_ID", snapshot.id
            )
        for reference in references:
            if (
                reference.source_uid is None
                or reference.source_sku is None
                or reference.semantic_fingerprint is None
            ):
                return EditionVerification(
                    False, len(references), expected, "OFFICIAL_PROVENANCE_MISSING", snapshot.id
                )
            printing = reference.printing
            try:
                current_fingerprint = _database_identity(printing).identity_hash()
            except OfficialEditionReconciliationError:
                return EditionVerification(
                    False, len(references), expected, "PERSISTED_IDENTITY_INVALID", snapshot.id
                )
            if current_fingerprint != reference.semantic_fingerprint:
                return EditionVerification(
                    False, len(references), expected, "PERSISTED_IDENTITY_DRIFT", snapshot.id
                )
            if printing.edition_id != edition.id:
                return EditionVerification(
                    False, len(references), expected, "REFERENCE_EDITION_MISMATCH", snapshot.id
                )
            if not any(
                item.source_uid == reference.source_uid and item.source_sku == reference.source_sku
                for item in printing.source_records
            ):
                return EditionVerification(
                    False, len(references), expected, "UPSTREAM_PROVENANCE_MISMATCH", snapshot.id
                )
            if not reference.image_url or not any(
                image.variant_id == printing.id and image.url == reference.image_url
                for image in printing.images
            ):
                return EditionVerification(
                    False, len(references), expected, "IMAGE_REFERENCE_MISMATCH", snapshot.id
                )
            identities.append(
                {
                    "reference_key": reference.reference_key,
                    "semantic_fingerprint": reference.semantic_fingerprint,
                    "source_uid": reference.source_uid,
                    "source_sku": reference.source_sku,
                    "printing_public_id": printing.public_id,
                }
            )
        if snapshot.exhaustive:
            edition_printing_count = (
                session.scalar(
                    select(func.count())
                    .select_from(CardVariant)
                    .where(CardVariant.edition_id == edition.id)
                )
                or 0
            )
            if edition_printing_count != expected:
                return EditionVerification(
                    False,
                    len(references),
                    expected,
                    "DATABASE_ONLY_OR_MISSING_PRINTINGS",
                    snapshot.id,
                )
    elif snapshot.source_type == "CURATED_WORKBOOK":
        if (
            expected != WORKBOOK_REFERENCE_COUNT
            or snapshot.identity_schema_version != SNAPSHOT_DIGEST_SCHEMA_VERSION
            or snapshot.exhaustive
        ):
            return EditionVerification(
                False, len(references), expected, "WORKBOOK_SNAPSHOT_INVALID", snapshot.id
            )
        for reference in references:
            if reference.workbook_row is None or reference.semantic_fingerprint is None:
                return EditionVerification(
                    False, len(references), expected, "WORKBOOK_PROVENANCE_MISSING", snapshot.id
                )
            printing = reference.printing
            fingerprint = hashlib.sha256(printing.public_id.encode("utf-8")).hexdigest()
            if fingerprint != reference.semantic_fingerprint or printing.edition_id != edition.id:
                return EditionVerification(
                    False, len(references), expected, "WORKBOOK_IDENTITY_MISMATCH", snapshot.id
                )
            identities.append(
                {
                    "reference_key": reference.reference_key,
                    "semantic_fingerprint": fingerprint,
                    "printing_public_id": printing.public_id,
                }
            )
    else:
        return EditionVerification(
            False, len(references), expected, "UNSUPPORTED_SNAPSHOT_SOURCE", snapshot.id
        )

    digest = _edition_digest(
        edition.public_id,
        expected,
        snapshot.identity_schema_version,
        identities,
    )
    if digest != snapshot.identity_digest:
        return EditionVerification(
            False, len(references), expected, "EDITION_IDENTITY_DIGEST_MISMATCH", snapshot.id
        )
    return EditionVerification(True, len(references), expected, None, snapshot.id)


def persist_official_edition_reconciliation(
    session: Session, reconciliation: dict[str, Any]
) -> EditionVerification:
    """Persist a validated official snapshot's links; never creates Cards/Printings."""
    counts = reconciliation["counts"]
    expected = reconciliation["expected_printing_count"]
    if (
        counts["official_source_rows"] != expected
        or counts["matched_existing_printings"] != expected
        or counts["official_only"]
        or counts["database_only"]
        or counts["identity_conflicts"]
        or counts["duplicate_semantic_identities"]
        or reconciliation["conflicts"]
        or reconciliation["official_only_rows"]
    ):
        raise OfficialEditionReconciliationError("OFFICIAL_EDITION_RECONCILIATION_INCOMPLETE")

    if session.in_transaction():
        session.rollback()
    try:
        with session.begin():
            edition = session.get(Edition, reconciliation["edition"].id)
            if edition is None:
                raise OfficialEditionReconciliationError("TARGET_EDITION_NOT_PERSISTED")
            snapshot = session.scalar(
                select(EditionCollectorSnapshot).where(
                    EditionCollectorSnapshot.edition_id == edition.id,
                    EditionCollectorSnapshot.source_type == OFFICIAL_SOURCE_TYPE,
                    EditionCollectorSnapshot.source_snapshot_sha256
                    == reconciliation["source_snapshot_sha256"],
                )
            )
            if snapshot is None:
                snapshot = EditionCollectorSnapshot(
                    edition_id=edition.id,
                    set_id=edition.set_id,
                    source_type=OFFICIAL_SOURCE_TYPE,
                    source_url=OFFICIAL_API_BASE,
                    transport_url=OFFICIAL_GALLERY_PROXY_BASE,
                    source_snapshot_sha256=reconciliation["source_snapshot_sha256"],
                    retrieved_at=reconciliation["retrieved_at"],
                    expected_printing_count=expected,
                    identity_digest=reconciliation["identity_digest"],
                    identity_schema_version=IDENTITY_SCHEMA_VERSION,
                    exhaustive=True,
                )
                session.add(snapshot)
                session.flush()
            elif (
                snapshot.identity_digest != reconciliation["identity_digest"]
                or snapshot.expected_printing_count != expected
            ):
                raise OfficialEditionReconciliationError(
                    "SNAPSHOT_HASH_ALREADY_BOUND_TO_OTHER_DIGEST"
                )

            for values in reconciliation["references"]:
                printing = values["printing"]
                current = session.scalar(
                    select(PrintingReference).where(
                        PrintingReference.snapshot_id == snapshot.id,
                        PrintingReference.reference_key == values["reference_key"],
                    )
                )
                expected_values = {key: value for key, value in values.items() if key != "printing"}
                expected_values.update({"snapshot_id": snapshot.id, "printing_id": printing.id})
                if current is None:
                    session.add(PrintingReference(**expected_values))
                    continue
                for field, expected_value in expected_values.items():
                    if getattr(current, field) != expected_value:
                        raise OfficialEditionReconciliationError(
                            "EXISTING_OFFICIAL_REFERENCE_CONFLICT"
                        )
            session.flush()
            verification = verify_edition_collector_snapshot(session, edition)
            if not verification.verified:
                raise OfficialEditionReconciliationError(
                    "PERSISTED_OFFICIAL_SNAPSHOT_FAILED_VERIFICATION:" + str(verification.reason)
                )
        return verification
    except Exception:
        session.rollback()
        raise
