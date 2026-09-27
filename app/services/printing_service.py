"""Read-only Edition, Printing, origin, and collector-catalogue queries."""

from __future__ import annotations

import re
from typing import Any, cast

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Card,
    CardSet,
    CardVariant,
    Edition,
    EditionCollectorSnapshot,
    PrintingReference,
    SourceRecord,
)
from app.schemas.error import ErrorCode
from app.utils.errors import APIError
from importer.official_edition_reference import verify_edition_collector_snapshot

REFERENCE_SOURCE_NAME = "konoha_shido_1st_edition_master"


def _origin_expression():
    has_upstream = exists(select(SourceRecord.id).where(SourceRecord.printing_id == CardVariant.id))
    has_reference = exists(
        select(PrintingReference.id).where(PrintingReference.printing_id == CardVariant.id)
    )
    return has_upstream, has_reference


def printing_origin_for(printing: CardVariant) -> str:
    has_upstream = any(record.printing_id == printing.id for record in printing.source_records)
    has_reference = bool(printing.references)
    if has_upstream and has_reference:
        return "UPSTREAM_AND_CURATED"
    if has_upstream:
        return "UPSTREAM"
    if has_reference:
        return "CURATED_REFERENCE"
    # Legacy rows predate typed SourceRecord.printing_id provenance. They are
    # retained as upstream-compatible catalogue records, never curated rows.
    return "UPSTREAM"


def _collector_sort_key(number: str, rarity: str | None, treatment: str | None, public_id: str):
    value = number.casefold().strip()
    mission = re.fullmatch(r"mss\s*0*(\d+)", value)
    if mission:
        number_key = (1, int(mission.group(1)), "")
    else:
        numeric = re.fullmatch(r"0*(\d+)([a-z]?)(?:/\d+)?", value)
        if numeric:
            number_key = (0, int(numeric.group(1)), numeric.group(2))
        else:
            number_key = (2, 0, value)
    return (
        *number_key,
        (rarity or "").casefold(),
        (treatment or "").casefold(),
        public_id,
    )


def _printing_options():
    return (
        joinedload(CardVariant.card).joinedload(Card.set),
        joinedload(CardVariant.edition_record),
        selectinload(CardVariant.images),
        selectinload(CardVariant.references).joinedload(PrintingReference.snapshot),
        selectinload(CardVariant.source_records),
    )


def _reference_for(printing: CardVariant, source_name: str = REFERENCE_SOURCE_NAME):
    workbook_reference = next(
        (item for item in printing.references if item.source_name == source_name), None
    )
    if workbook_reference is not None:
        return workbook_reference
    official_references = [item for item in printing.references if item.snapshot is not None]
    return (
        max(official_references, key=lambda item: item.snapshot.created_at)
        if official_references
        else None
    )


def _display_number(printing: CardVariant, reference: PrintingReference | None) -> str:
    if reference is not None:
        return reference.collector_number
    return printing.collector_number or printing.card.card_number


def to_printing_data(printing: CardVariant, *, reference: PrintingReference | None = None) -> dict:
    reference = reference or _reference_for(printing)
    raw_rarity = printing.rarity_override
    raw_variant = printing.source_variant
    images = [image for image in printing.images if image.variant_id == printing.id]
    origin = printing_origin_for(printing)
    return {
        "public_id": printing.public_id,
        "card_id": printing.card.public_id,
        "card_name": reference.card_name if reference else printing.card.name,
        "card_type": printing.card.card_type,
        "set_id": printing.card.set.public_id,
        "set_name": printing.card.set.name,
        "edition_id": printing.edition_record.public_id if printing.edition_record else None,
        "edition_name": printing.edition_record.name if printing.edition_record else None,
        "collector_number": _display_number(printing, reference),
        "printed_number": printing.card.card_number,
        "rarity": reference.normalized_rarity if reference else printing.normalized_rarity,
        "collector_class": reference.collector_class if reference else printing.collector_class,
        "treatment": reference.normalized_treatment if reference else printing.normalized_treatment,
        "finish": printing.finish,
        "language": printing.language,
        "serial_numbered": False if printing.serial_numbered is None else printing.serial_numbered,
        "serial_total": printing.serial_total,
        "origin": origin,
        "source_rarity": raw_rarity,
        "source_variant": raw_variant,
        "collector_reference_number": reference.collector_number if reference else None,
        "collector_reference_card_name": reference.card_name if reference else None,
        "collector_reference_rarity": reference.rarity_raw if reference else None,
        "collector_reference_variant": reference.variant_raw if reference else None,
        "images": images,
    }


def get_edition(db: Session, public_id: str) -> Edition:
    edition = db.scalar(
        select(Edition).options(joinedload(Edition.set)).where(Edition.public_id == public_id)
    )
    if edition is None:
        raise APIError(ErrorCode.EDITION_NOT_FOUND, "Edition not found.", 404)
    return edition


def get_printing(db: Session, public_id: str) -> CardVariant:
    printing = db.scalar(
        select(CardVariant).options(*_printing_options()).where(CardVariant.public_id == public_id)
    )
    if printing is None:
        raise APIError(ErrorCode.PRINTING_NOT_FOUND, "Printing not found.", 404)
    return printing


def edition_counts(db: Session, edition: Edition) -> dict[str, int | str]:
    canonical_count = (
        db.scalar(
            select(func.count(distinct(CardVariant.card_id))).where(
                CardVariant.edition_id == edition.id
            )
        )
        or 0
    )
    persisted_count = (
        db.scalar(
            select(func.count())
            .select_from(CardVariant)
            .where(CardVariant.edition_id == edition.id)
        )
        or 0
    )
    verification = verify_edition_collector_snapshot(db, edition)
    reference_count = verification.reference_count
    verified = verification.verified
    return {
        "canonical_card_count": canonical_count,
        "collectible_printing_count": reference_count if verified else persisted_count,
        "collector_reference_status": "VERIFIED" if verified else "NONE",
        "collector_reference_count": reference_count,
    }


def set_counts(db: Session, card_set: CardSet) -> dict[str, int]:
    canonical_count = (
        db.scalar(select(func.count()).select_from(Card).where(Card.set_id == card_set.id)) or 0
    )
    printing_count = (
        db.scalar(
            select(func.count())
            .select_from(CardVariant)
            .join(Card, Card.id == CardVariant.card_id)
            .where(Card.set_id == card_set.id)
        )
        or 0
    )
    return {
        "canonical_card_count": canonical_count,
        "collectible_printing_count": printing_count,
    }


def set_detail_payload(db: Session, card_set: CardSet) -> dict:
    """Build additive collector counts and Edition availability for Set responses."""
    from app.schemas.set import EditionSummary

    payload: dict[str, Any] = {
        "id": card_set.public_id,
        "code": card_set.code,
        "name": card_set.name,
        "edition": card_set.edition,
        "language": card_set.language,
        "release_date": card_set.release_date,
        "printed_total": card_set.printed_total,
        "total_with_variants": card_set.total_with_variants,
        "logo_url": card_set.logo_url,
        "symbol_url": card_set.symbol_url,
    }
    payload.update(set_counts(db, card_set))
    edition_summaries = []
    for edition in editions_for_set(db, card_set):
        counts = edition_counts(db, edition)
        edition_summaries.append(
            EditionSummary(
                id=edition.public_id,
                name=edition.name,
                canonical_card_count=int(counts["canonical_card_count"]),
                collectible_printing_count=int(counts["collectible_printing_count"]),
                collector_reference_status=str(counts["collector_reference_status"]),
                collector_reference_count=int(counts["collector_reference_count"]),
            ).model_dump(mode="python")
        )
    payload["editions"] = edition_summaries
    return payload


def editions_for_set(db: Session, card_set: CardSet) -> list[Edition]:
    return list(
        db.scalars(
            select(Edition)
            .where(Edition.set_id == card_set.id)
            .order_by(Edition.normalized_name, Edition.public_id)
        ).all()
    )


def list_editions_for_set(
    db: Session, public_set_id: str, *, page: int, limit: int
) -> tuple[list[Edition], int]:
    card_set = db.scalar(select(CardSet).where(CardSet.public_id == public_set_id))
    if card_set is None:
        raise APIError(ErrorCode.SET_NOT_FOUND, "Set not found.", 404)
    total = (
        db.scalar(select(func.count()).select_from(Edition).where(Edition.set_id == card_set.id))
        or 0
    )
    results = db.scalars(
        select(Edition)
        .options(joinedload(Edition.set))
        .where(Edition.set_id == card_set.id)
        .order_by(Edition.normalized_name, Edition.public_id)
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(results), total


def edition_printings(
    db: Session,
    edition: Edition,
    *,
    collector_view: bool,
    page: int,
    limit: int,
) -> tuple[list[tuple[CardVariant, PrintingReference | None]], int]:
    statement: Any
    if collector_view:
        snapshot = _latest_collector_snapshot(db, edition)
        if snapshot is None:
            return [], 0
        statement = (
            select(CardVariant, PrintingReference)
            .join(PrintingReference, PrintingReference.printing_id == CardVariant.id)
            .where(
                CardVariant.edition_id == edition.id,
                PrintingReference.snapshot_id == snapshot.id,
            )
        )
        count_statement = (
            select(func.count())
            .select_from(PrintingReference)
            .join(CardVariant, CardVariant.id == PrintingReference.printing_id)
            .where(
                CardVariant.edition_id == edition.id,
                PrintingReference.snapshot_id == snapshot.id,
            )
        )
    else:
        statement = select(CardVariant).where(CardVariant.edition_id == edition.id)
        count_statement = (
            select(func.count())
            .select_from(CardVariant)
            .where(CardVariant.edition_id == edition.id)
        )
    total = db.scalar(count_statement) or 0
    results: list[tuple[CardVariant, PrintingReference | None]] = []
    if collector_view:
        rows = db.execute(statement.options(*_printing_options())).all()
        results = [(cast(CardVariant, row[0]), cast(PrintingReference, row[1])) for row in rows]
    else:
        rows = db.scalars(statement.options(*_printing_options())).all()
        results = [
            (cast(CardVariant, printing), _reference_for(cast(CardVariant, printing)))
            for printing in rows
        ]
    results.sort(
        key=lambda pair: _collector_sort_key(
            _display_number(pair[0], pair[1]),
            pair[1].normalized_rarity if pair[1] else pair[0].normalized_rarity,
            pair[1].normalized_treatment if pair[1] else pair[0].normalized_treatment,
            pair[0].public_id,
        )
    )
    start = (page - 1) * limit
    return results[start : start + limit], total


def list_printings(
    db: Session,
    *,
    page: int,
    limit: int,
    set_id: str | None = None,
    edition_id: str | None = None,
    rarity: str | None = None,
    treatment: str | None = None,
    collector_class: str | None = None,
    card_id: str | None = None,
    origin: str | None = None,
) -> tuple[list[CardVariant], int]:
    statement = select(CardVariant).join(CardVariant.card).join(Card.set)
    if set_id:
        statement = statement.where(func.lower(CardSet.public_id) == set_id.casefold())
    if edition_id:
        statement = statement.join(CardVariant.edition_record).where(
            func.lower(Edition.public_id) == edition_id.casefold()
        )
    if rarity:
        statement = statement.where(func.lower(CardVariant.normalized_rarity) == rarity.casefold())
    if treatment:
        statement = statement.where(
            func.lower(CardVariant.normalized_treatment) == treatment.casefold()
        )
    if collector_class:
        statement = statement.where(
            func.lower(CardVariant.collector_class) == collector_class.casefold()
        )
    if card_id:
        statement = statement.where(func.lower(Card.public_id) == card_id.casefold())
    has_upstream, has_reference = _origin_expression()
    if origin == "UPSTREAM":
        statement = statement.where(has_upstream, ~has_reference)
    elif origin == "UPSTREAM_AND_CURATED":
        statement = statement.where(has_upstream, has_reference)
    elif origin == "CURATED_REFERENCE":
        statement = statement.where(~has_upstream, has_reference)
    elif origin is not None:
        raise APIError(ErrorCode.INVALID_FILTER, "Invalid Printing origin.", 400)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(db.scalars(statement.options(*_printing_options())).all())
    rows.sort(
        key=lambda printing: _collector_sort_key(
            _display_number(printing, _reference_for(printing)),
            printing.normalized_rarity or printing.collector_class,
            printing.normalized_treatment,
            printing.public_id,
        )
    )
    start = (page - 1) * limit
    return rows[start : start + limit], total


def list_rarity_counts(db: Session) -> list[dict[str, int | str]]:
    rows = db.execute(
        select(CardVariant.normalized_rarity, func.count())
        .where(CardVariant.normalized_rarity.is_not(None))
        .group_by(CardVariant.normalized_rarity)
        .order_by(CardVariant.normalized_rarity)
    )
    return [{"rarity": rarity, "printing_count": count} for rarity, count in rows]


def edition_has_collector_reference(db: Session, edition: Edition) -> bool:
    return verify_edition_collector_snapshot(db, edition).verified


def _latest_collector_snapshot(db: Session, edition: Edition) -> EditionCollectorSnapshot | None:
    return db.scalar(
        select(EditionCollectorSnapshot)
        .where(EditionCollectorSnapshot.edition_id == edition.id)
        .order_by(EditionCollectorSnapshot.created_at.desc(), EditionCollectorSnapshot.id.desc())
        .limit(1)
    )


def card_collector_counts(db: Session, card: Card) -> dict[str, int]:
    count = (
        db.scalar(
            select(func.count()).select_from(CardVariant).where(CardVariant.card_id == card.id)
        )
        or 0
    )
    return {"collectible_printing_count": count}
