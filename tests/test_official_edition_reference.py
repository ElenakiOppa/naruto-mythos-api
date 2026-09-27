"""Deterministic official Edition-to-existing-Printing verification tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.models import (
    CardImage,
    CardVariant,
    Edition,
    EditionCollectorSnapshot,
    PrintingReference,
    SourceRecord,
)
from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.catalogue_design.identity import CanonicalPrintingKey
from importer.official_edition_reference import (
    EXPECTED_OFFICIAL_EDITIONS,
    OfficialEditionReconciliationError,
    build_official_edition_reconciliation,
    persist_official_edition_reconciliation,
    verify_edition_collector_snapshot,
)
from importer.reference_catalogue import build_reference_reconciliation
from importer.reference_persistence import persist_reference_reconciliation
from tests.test_reference_catalogue import _seed_upstream_catalogue

SNAPSHOT_HASH = "a" * 64
RETRIEVED_AT = datetime(2026, 9, 27, tzinfo=UTC)
TARGETS = (
    ("Set 1: Konoha Shidō", "2nd edition", 187),
    ("Set 2: Shinobi Shiren", "1st edition", 242),
)


def _records_by_language():
    return load_records_from_acquisition()


def _seed_official_catalogue(db_session):
    _seed_upstream_catalogue(db_session)
    records = _records_by_language()["en"]
    for record in records:
        if (record.set, record.edition) not in {
            ("Set 1: Konoha Shidō", "2nd edition"),
            ("Set 2: Shinobi Shiren", "1st edition"),
        }:
            continue
        public_id = CanonicalPrintingKey.from_record(record).analysis_public_id()
        printing = db_session.scalar(select(CardVariant).where(CardVariant.public_id == public_id))
        assert printing is not None
        db_session.add(
            CardImage(
                card_id=printing.card_id,
                variant_id=printing.id,
                image_type="front-en",
                url=record.image,
                source_name="naruto_mythos_phase14_snapshot",
                hosted_by_us=False,
            )
        )
    db_session.commit()


def _build(db_session, set_name: str, edition_name: str, records=None):
    return build_official_edition_reconciliation(
        db_session,
        records or _records_by_language(),
        set_name=set_name,
        edition_name=edition_name,
        source_snapshot_sha256=SNAPSHOT_HASH,
        retrieved_at=RETRIEVED_AT,
    )


@pytest.fixture
def seeded_official_database(db_session):
    _seed_official_catalogue(db_session)
    return db_session


@pytest.mark.parametrize(("set_name", "edition_name", "expected"), TARGETS)
def test_official_edition_matches_every_existing_printing(
    seeded_official_database, set_name, edition_name, expected
):
    before_cards = seeded_official_database.scalar(select(func.count()).select_from(CardVariant))
    result = _build(seeded_official_database, set_name, edition_name)

    assert result["counts"] == {
        "official_source_rows": expected,
        "matched_existing_printings": expected,
        "official_only": 0,
        "database_only": 0,
        "identity_conflicts": 0,
        "duplicate_semantic_identities": 0,
    }
    assert (
        seeded_official_database.scalar(select(func.count()).select_from(CardVariant))
        == before_cards
    )
    assert len({row["printing"].public_id for row in result["references"]}) == expected


@pytest.mark.parametrize(("set_name", "edition_name", "expected"), TARGETS)
def test_official_snapshot_persistence_is_idempotent_and_verifiable(
    seeded_official_database, set_name, edition_name, expected
):
    result = _build(seeded_official_database, set_name, edition_name)
    first = persist_official_edition_reconciliation(seeded_official_database, result)
    second = persist_official_edition_reconciliation(seeded_official_database, result)
    edition = result["edition"]

    assert first.verified and second.verified
    assert first.reference_count == second.reference_count == expected
    assert (
        seeded_official_database.scalar(
            select(func.count())
            .select_from(PrintingReference)
            .where(PrintingReference.snapshot_id == first.snapshot_id)
        )
        == expected
    )
    assert (
        seeded_official_database.scalar(select(func.count()).select_from(EditionCollectorSnapshot))
        == 1
    )
    assert verify_edition_collector_snapshot(seeded_official_database, edition).verified


def test_konoha_first_remains_396_and_gets_complete_workbook_snapshot(db_session):
    _seed_official_catalogue(db_session)
    reconciliation = build_reference_reconciliation()
    persist_reference_reconciliation(db_session, reconciliation)
    first = next(
        edition
        for edition in db_session.scalars(select(Edition)).all()
        if edition.set.name == "Set 1: Konoha Shidō" and edition.normalized_name == "1st edition"
    )

    verification = verify_edition_collector_snapshot(db_session, first)
    assert verification.verified
    assert verification.reference_count == verification.expected_count == 396
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PrintingReference)
            .where(PrintingReference.snapshot_id == verification.snapshot_id)
        )
        == 396
    )


def test_order_only_source_drift_does_not_change_printing_identity(seeded_official_database):
    printing_count = seeded_official_database.scalar(select(func.count()).select_from(CardVariant))
    records = _records_by_language()
    base = records["en"]
    chosen = next(
        record
        for record in base
        if record.set == "Set 2: Shinobi Shiren"
        and record.edition == "1st edition"
        and record.uid == 865
    )
    changed = {language: list(rows) for language, rows in records.items()}
    for language, rows in changed.items():
        changed[language] = [
            replace(record, order=record.order + 1) if record.uid == chosen.uid else record
            for record in rows
        ]
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition", changed)
    assert result["counts"]["matched_existing_printings"] == 242
    assert result["counts"]["identity_conflicts"] == 0
    assert (
        seeded_official_database.scalar(select(func.count()).select_from(CardVariant))
        == printing_count
    )


def test_identity_affecting_source_drift_is_reported_as_conflict(seeded_official_database):
    records = _records_by_language()
    chosen = next(
        record
        for record in records["en"]
        if record.set == "Set 2: Shinobi Shiren"
        and record.edition == "1st edition"
        and not record.variant
    )
    changed = {language: list(items) for language, items in records.items()}
    for language, items in changed.items():
        changed[language] = [
            replace(record, variant="Unreviewed Variant") if record.uid == chosen.uid else record
            for record in items
        ]
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition", changed)

    assert result["counts"]["official_source_rows"] == 242
    assert result["counts"]["matched_existing_printings"] == 241
    assert result["counts"]["official_only"] == 0
    assert result["counts"]["database_only"] == 0
    assert result["counts"]["identity_conflicts"] == 1


def test_edition_verification_fails_when_one_reference_is_missing(seeded_official_database):
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition")
    verification = persist_official_edition_reconciliation(seeded_official_database, result)
    row = result["references"][0]
    printing = row["printing"]
    seeded_official_database.execute(
        delete(SourceRecord).where(SourceRecord.printing_id == printing.id)
    )
    seeded_official_database.execute(delete(CardImage).where(CardImage.variant_id == printing.id))
    seeded_official_database.delete(printing)
    seeded_official_database.commit()

    current = verify_edition_collector_snapshot(seeded_official_database, result["edition"])
    assert not current.verified
    assert current.reason == "REFERENCE_COUNT_MISMATCH"
    assert current.reference_count == verification.reference_count - 1


def test_edition_verification_fails_when_extra_reference_is_added(seeded_official_database):
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition")
    verification = persist_official_edition_reconciliation(seeded_official_database, result)
    original = seeded_official_database.scalar(
        select(PrintingReference).where(PrintingReference.snapshot_id == verification.snapshot_id)
    )
    seeded_official_database.add(
        PrintingReference(
            printing_id=original.printing_id,
            snapshot_id=verification.snapshot_id,
            source_name=original.source_name,
            reference_key=original.reference_key + "-extra",
            source_sha256=original.source_sha256,
            source_uid=original.source_uid,
            source_sku=original.source_sku,
            semantic_fingerprint=original.semantic_fingerprint,
            collector_number=original.collector_number,
            card_name=original.card_name,
            rarity_raw=original.rarity_raw,
            variant_raw=original.variant_raw,
            normalized_rarity=original.normalized_rarity,
            collector_class=original.collector_class,
            normalized_treatment=original.normalized_treatment,
            image_url=original.image_url,
        )
    )
    seeded_official_database.commit()

    current = verify_edition_collector_snapshot(seeded_official_database, result["edition"])
    assert not current.verified
    assert current.reason == "REFERENCE_COUNT_MISMATCH"


def test_edition_verification_fails_after_persisted_identity_drift(seeded_official_database):
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition")
    verification = persist_official_edition_reconciliation(seeded_official_database, result)
    printing = result["references"][0]["printing"]
    printing.source_variant = "unreviewed identity change"
    seeded_official_database.commit()

    current = verify_edition_collector_snapshot(seeded_official_database, result["edition"])
    assert not current.verified
    assert current.reason == "PERSISTED_IDENTITY_DRIFT"
    assert verification.reference_count == 242


def test_edition_verification_fails_when_persisted_expected_count_changes(
    seeded_official_database,
):
    result = _build(seeded_official_database, "Set 1: Konoha Shidō", "2nd edition")
    verification = persist_official_edition_reconciliation(seeded_official_database, result)
    snapshot = seeded_official_database.get(EditionCollectorSnapshot, verification.snapshot_id)
    snapshot.expected_printing_count = 186
    seeded_official_database.commit()

    current = verify_edition_collector_snapshot(seeded_official_database, result["edition"])
    assert not current.verified
    assert current.reason == "REFERENCE_COUNT_MISMATCH"


def test_edition_verification_fails_on_duplicate_persisted_semantic_fingerprint(
    seeded_official_database,
):
    result = _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition")
    verification = persist_official_edition_reconciliation(seeded_official_database, result)
    references = seeded_official_database.scalars(
        select(PrintingReference)
        .where(PrintingReference.snapshot_id == verification.snapshot_id)
        .order_by(PrintingReference.reference_key)
        .limit(2)
    ).all()
    references[1].semantic_fingerprint = references[0].semantic_fingerprint
    seeded_official_database.commit()

    current = verify_edition_collector_snapshot(seeded_official_database, result["edition"])
    assert not current.verified
    assert current.reason in {"DUPLICATE_OFFICIAL_SOURCE_ID", "PERSISTED_IDENTITY_DRIFT"}


def test_expected_official_count_is_a_hard_gate(seeded_official_database, monkeypatch):
    monkeypatch.setitem(EXPECTED_OFFICIAL_EDITIONS, ("Set 1: Konoha Shidō", "2nd edition"), 186)
    with pytest.raises(
        OfficialEditionReconciliationError, match="OFFICIAL_PRINTING_COUNT_MISMATCH"
    ):
        _build(seeded_official_database, "Set 1: Konoha Shidō", "2nd edition")


def test_duplicate_official_semantic_identity_fails_closed(seeded_official_database):
    records = _records_by_language()
    rows = [
        row
        for row in records["en"]
        if row.set == "Set 2: Shinobi Shiren" and row.edition == "1st edition"
    ]
    first, second = rows[0], rows[1]
    changed = {language: list(items) for language, items in records.items()}
    for language, items in changed.items():
        changed[language] = [
            replace(
                row,
                id=first.id,
                rarity=first.rarity,
                variant=first.variant,
                card_version=first.card_version,
                stamp=first.stamp,
            )
            if row.uid == second.uid
            else row
            for row in items
        ]
    with pytest.raises(
        OfficialEditionReconciliationError, match="DUPLICATE_SEMANTIC_PRINTING_IDENTITY"
    ):
        _build(seeded_official_database, "Set 2: Shinobi Shiren", "1st edition", changed)


def test_api_exposes_complete_verified_views_for_all_three_editions(
    client, seeded_official_database
):
    persist_reference_reconciliation(seeded_official_database, build_reference_reconciliation())
    editions = {}
    for set_name, edition_name, expected in TARGETS:
        reconciliation = _build(seeded_official_database, set_name, edition_name)
        persist_official_edition_reconciliation(seeded_official_database, reconciliation)
        editions[(set_name, edition_name)] = (reconciliation["edition"], expected)

    first = next(
        edition
        for edition in seeded_official_database.scalars(select(Edition)).all()
        if edition.set.name == "Set 1: Konoha Shidō" and edition.normalized_name == "1st edition"
    )
    editions[("Set 1: Konoha Shidō", "1st edition")] = (first, 396)

    assert client.get("/v1/cards?limit=100").json()["pagination"]["total"] == 318
    assert client.get("/v1/printings?limit=1").json()["pagination"]["total"] == 848
    for (set_name, edition_name), (edition, expected) in editions.items():
        metadata = client.get(f"/v1/editions/{edition.public_id}").json()
        assert metadata["collector_reference_status"] == "VERIFIED"
        assert metadata["collector_reference_count"] == expected
        first_page = client.get(
            f"/v1/editions/{edition.public_id}/printings?limit=100&page=1"
        ).json()
        assert first_page["pagination"]["total"] == expected
        pages = [first_page["data"]]
        for page in range(2, first_page["pagination"]["pages"] + 1):
            pages.append(
                client.get(
                    f"/v1/editions/{edition.public_id}/printings?limit=100&page={page}"
                ).json()["data"]
            )
        printing_ids = [item["id"] for page in pages for item in page]
        assert len(printing_ids) == expected
        assert len(set(printing_ids)) == expected
        assert all(item["edition_name"] == edition_name for page in pages for item in page)
