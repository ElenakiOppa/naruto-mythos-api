"""Curated Konoha checklist gate, reconciliation, and persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    Card,
    CardImage,
    CardSet,
    CardVariant,
    Edition,
    PrintingReference,
    SourceRecord,
)
from app.models.edition import normalize_edition_name
from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.catalogue_design.identity import (
    CanonicalCardKey,
    CanonicalEditionKey,
    CanonicalExpansionKey,
    CanonicalPrintingKey,
)
from importer.catalogue_importer import _observed_integer
from importer.catalogue_persistence import SOURCE_NAME
from importer.reference_catalogue import build_reference_reconciliation
from importer.reference_persistence import (
    persist_reference_reconciliation,
    printing_origin,
)
from scripts.build_konoha_reference import OUTPUT, WORKBOOK, build_reference

HAS_LOCAL_SOURCE = any(Path("data/acquisition/raw").glob("*.json"))


def test_workbook_gate_and_generated_artifact_are_deterministic():
    first = build_reference(WORKBOOK)
    second = build_reference(WORKBOOK)
    checked_in = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert first["entry_count"] == 396
    assert first == second == checked_in
    assert first["worksheet"] == "Checklist"
    assert first["headers_used"] == ["No.", "Card", "Rarity", "Variant"]
    assert len({entry["reference_key"] for entry in first["entries"]}) == 396
    assert "Low Value" not in first["entries"][0]
    assert "Qty" not in first["entries"][0]


@pytest.mark.skipif(not HAS_LOCAL_SOURCE, reason="upstream raw acquisition is local and untracked")
def test_reconciliation_is_complete_deterministic_and_identity_safe():
    first = build_reference_reconciliation()
    second = build_reference_reconciliation()

    assert first == second
    assert first["counts"] == {
        "canonical_card_count": 318,
        "upstream_printing_count": 636,
        "curated_reference_entry_count": 396,
        "curated_reference_only_printing_count": 212,
        "total_collectible_printing_count": 848,
        "konoha_1e_checklist_count": 396,
        "konoha_1e_canonical_card_count": 158,
        "konoha_1e_upstream_overlap_count": 184,
        "konoha_1e_source_only_count": 2,
        "konoha_1e_new_curated_count": 212,
    }
    assert len(first["matches"]) + len(first["curated_printings"]) == 396
    assert first["ambiguities"] == []
    assert len(first["conflicts"]) == 2
    assert {item["collector_number"] for item in first["conflicts"]} == {"063", "075"}
    assert len(first["source_only"]) == 2
    assert {item["collector_number"] for item in first["source_only"]} == {
        "063/130",
        "075/130",
    }
    assert len({item["printing_public_id"] for item in first["curated_printings"]}) == 212
    assert all(
        item["source_uid"] is None and item["source_sku"] is None
        for item in first["curated_printings"]
    )
    assert all(item["edition_public_id"] for item in first["matches"] + first["curated_printings"])
    assert all(
        item["edition_public_id"] == first["matches"][0]["edition_public_id"]
        for item in first["matches"] + first["curated_printings"]
    )
    assert all(
        not any(key in item for key in ("image_url", "price", "serial_numbered", "serial_total"))
        for item in first["curated_printings"]
    )

    source = load_records_from_acquisition()["en"]
    assert (
        len({CanonicalCardKey(record.set, record.id).analysis_public_id() for record in source})
        == 318
    )
    assert (
        len({CanonicalPrintingKey.from_record(record).analysis_public_id() for record in source})
        == 636
    )

    rare_art = next(
        item
        for item in first["matches"] + first["curated_printings"]
        if item["collector_number"] == "104A"
    )
    assert rare_art["canonical_printed_identifier"] == "104/130"
    serialized_label = next(
        item for item in first["matches"] if item["collector_number"] == "n/2000"
    )
    assert serialized_label["canonical_printed_identifier"] == "133/130"
    assert serialized_label["source_uid"] == 203
    assert serialized_label["taxonomy"]["normalized_rarity"] == "Legendary"
    assert (
        len({item["reference_key"] for item in first["matches"] + first["curated_printings"]})
        == 396
    )


def _seed_upstream_catalogue(db_session):
    records = load_records_from_acquisition()["en"]
    set_objects = {}
    for expansion in sorted({record.set for record in records}):
        public_id = CanonicalExpansionKey(expansion).analysis_public_id()
        set_objects[expansion] = CardSet(public_id=public_id, name=expansion, language="EN")
    db_session.add_all(set_objects.values())
    db_session.flush()

    edition_objects = {}
    for record in records:
        if not record.edition:
            continue
        normalized = normalize_edition_name(record.edition)
        key = (record.set, normalized)
        if key not in edition_objects:
            edition_public_id = CanonicalEditionKey(
                set_public_id=CanonicalExpansionKey(record.set).analysis_public_id(),
                normalized_name=normalized,
            ).analysis_public_id()
            edition_objects[key] = Edition(
                public_id=edition_public_id,
                set=set_objects[record.set],
                name=record.edition,
                normalized_name=normalized,
            )
    db_session.add_all(edition_objects.values())
    db_session.flush()

    card_records = {}
    for record in records:
        key = (record.set, record.id)
        card_records.setdefault(key, record)
    cards_by_key = {}
    for key, record in card_records.items():
        public_id = CanonicalCardKey(*key).analysis_public_id()
        card = Card(
            public_id=public_id,
            set=set_objects[record.set],
            card_number=record.id,
            name=record.title or "Unnamed card",
            card_type=record.card_type,
            rarity=record.rarity,
            chakra=_observed_integer(record.chakra),
            power=_observed_integer(record.power),
            points=_observed_integer(record.points),
        )
        cards_by_key[key] = card
    db_session.add_all(cards_by_key.values())
    db_session.flush()

    printings = []
    provenance = []
    for record in records:
        printing_id = CanonicalPrintingKey.from_record(record).analysis_public_id()
        edition = (
            edition_objects[(record.set, normalize_edition_name(record.edition))]
            if record.edition
            else None
        )
        printing = CardVariant(
            public_id=printing_id,
            card=cards_by_key[(record.set, record.id)],
            edition_record=edition,
            edition=record.edition,
            collector_number=record.id,
            variant_type=record.variant or "standard",
            finish=record.variant,
            rarity_override=record.rarity,
            source_variant=record.variant,
            card_version=record.card_version,
            stamp=record.stamp or None,
            serial_numbered=None,
        )
        printings.append((record, printing))
    db_session.add_all(printing for _, printing in printings)
    db_session.flush()
    for record, printing in printings:
        provenance.append(
            SourceRecord(
                entity_type="card_variants",
                entity_id=printing.id,
                printing_id=printing.id,
                source_name=SOURCE_NAME,
                external_id=f"{record.uid}:en",
                source_uid=str(record.uid),
                source_sku=record.sku,
                observation=record.raw,
            )
        )
    db_session.add_all(provenance)
    db_session.commit()


@pytest.mark.skipif(not HAS_LOCAL_SOURCE, reason="upstream raw acquisition is local and untracked")
def test_reference_persistence_is_idempotent_and_keeps_origins_separate(db_session):
    _seed_upstream_catalogue(db_session)
    reconciliation = build_reference_reconciliation()

    first = persist_reference_reconciliation(db_session, reconciliation)
    second = persist_reference_reconciliation(db_session, reconciliation)

    assert first == second
    assert first.canonical_cards == 318
    assert first.upstream_printings == 636
    assert first.curated_reference_entries == 396
    assert first.curated_reference_only_printings == 212
    assert first.upstream_and_curated_printings == 184
    assert first.upstream_only_printings == 452
    assert first.total_printings == 848
    assert db_session.scalar(select(func.count()).select_from(PrintingReference)) == 396
    assert db_session.scalar(select(func.count()).select_from(CardImage)) == 0
    assert db_session.scalar(select(func.count()).select_from(SourceRecord)) == 636

    curated = db_session.scalars(
        select(CardVariant).where(CardVariant.reference_identity.is_not(None))
    ).all()
    assert len(curated) == 212
    assert all(printing.edition_record is not None for printing in curated)
    assert all(printing.source_variant is None for printing in curated)
    assert all(printing.rarity_override is None for printing in curated)
    assert all(
        printing.serial_numbered is None and printing.serial_total is None for printing in curated
    )
    assert all(not printing.images and not printing.translations for printing in curated)
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.printing_id.in_([printing.id for printing in curated]))
        )
        == 0
    )

    reference_count_by_printing = dict(
        db_session.execute(
            select(PrintingReference.printing_id, func.count()).group_by(
                PrintingReference.printing_id
            )
        ).all()
    )
    assert len(reference_count_by_printing) == 396
    assert sum(count == 1 for count in reference_count_by_printing.values()) == 396
    referenced_editions = set(
        db_session.scalars(
            select(CardVariant.edition_id)
            .join(PrintingReference, PrintingReference.printing_id == CardVariant.id)
            .distinct()
        ).all()
    )
    target_edition_id = db_session.scalar(
        select(Edition.id).where(
            Edition.public_id == reconciliation["matches"][0]["edition_public_id"]
        )
    )
    assert referenced_editions == {target_edition_id}

    upstream_reference_count = db_session.scalar(
        select(func.count(func.distinct(PrintingReference.printing_id))).where(
            PrintingReference.printing_id.in_(
                select(SourceRecord.printing_id).where(SourceRecord.printing_id.is_not(None))
            )
        )
    )
    assert upstream_reference_count == 184
    assert len(reference_count_by_printing) - upstream_reference_count == 212
    assert printing_origin(db_session, curated[0].id) == "CURATED_REFERENCE"
    upstream_only = db_session.scalar(
        select(CardVariant)
        .join(SourceRecord, SourceRecord.printing_id == CardVariant.id)
        .where(SourceRecord.source_uid == "266")
    )
    assert upstream_only is not None
    assert printing_origin(db_session, upstream_only.id) == "UPSTREAM"
    shared_reference = db_session.scalar(
        select(PrintingReference).where(PrintingReference.collector_number == "001")
    )
    assert shared_reference is not None
    assert printing_origin(db_session, shared_reference.printing_id) == "UPSTREAM_AND_CURATED"

    reference_terms = {
        (reference.collector_number, reference.rarity_raw, reference.variant_raw)
        for reference in db_session.scalars(select(PrintingReference))
    }
    assert ("104A", "Rare ART", "Holographic / Micro-engraved") in reference_terms
    assert ("n/2000", "Legendary", "22K Gold / Individually Numbered") in reference_terms

    editionless_uids = {
        str(record.uid)
        for record in load_records_from_acquisition()["en"]
        if record.set == "Set 1: Konoha Shidō" and not record.edition
    }
    editionless_printing_ids = set(
        db_session.scalars(
            select(SourceRecord.printing_id).where(SourceRecord.source_uid.in_(editionless_uids))
        ).all()
    )
    assert len(editionless_printing_ids) == 21
    assert all(
        db_session.get(CardVariant, printing_id).edition_id is None
        for printing_id in editionless_printing_ids
    )
    assert not editionless_printing_ids.intersection(reference_count_by_printing)


@pytest.mark.skipif(not HAS_LOCAL_SOURCE, reason="upstream raw acquisition is local and untracked")
def test_collector_treatments_and_rarities_remain_distinct():
    result = build_reference_reconciliation()
    entries = result["matches"] + result["curated_printings"]

    normal_family = [
        item
        for item in entries
        if item["collector_number"] == "001" and item["rarity_raw"] == "Common"
    ]
    assert {item["variant_raw"] for item in normal_family} == {"Normal", "FullArt", "Holographic"}
    assert len({item["printing_public_id"] for item in normal_family}) == 3
    assert len({item["card_public_id"] for item in normal_family}) == 1

    tsunade_rare = [
        item
        for item in entries
        if item["card_name"] == "TSUNADE" and item["collector_number"] in {"104", "104A"}
    ]
    assert {(item["collector_number"], item["rarity_raw"]) for item in tsunade_rare} == {
        ("104", "Rare"),
        ("104A", "Rare ART"),
    }
    assert len({item["card_public_id"] for item in tsunade_rare}) == 1
    assert len({item["printing_public_id"] for item in tsunade_rare}) == 2

    tsunade_secret = [
        item
        for item in entries
        if item["collector_number"] == "131" and item["card_name"] == "TSUNADE - Fifth Hokage"
    ]
    assert {item["rarity_raw"] for item in tsunade_secret} == {"Secret", "Secret Variant"}
    assert len({item["printing_public_id"] for item in tsunade_secret}) == 2

    curated_mythos = next(
        item
        for item in result["curated_printings"]
        if item["rarity_raw"] == "Mythos" and item["collector_number"] == "145"
    )
    assert curated_mythos["canonical_printed_identifier"] == "145/130"
    assert curated_mythos["variant_raw"] == "Holographic / Micro-engraved"
    assert curated_mythos["source_uid"] is None


@pytest.mark.skipif(not HAS_LOCAL_SOURCE, reason="upstream raw acquisition is local and untracked")
def test_special_collector_numbers_never_create_canonical_cards():
    reconciliation = build_reference_reconciliation()
    canonical_ids = {
        item["card_public_id"]
        for item in reconciliation["matches"] + reconciliation["curated_printings"]
    }
    assert len(canonical_ids) == 158
    rare_art = next(
        item
        for item in reconciliation["matches"] + reconciliation["curated_printings"]
        if item["collector_number"] == "104A"
    )
    serialized_label = next(
        item
        for item in reconciliation["matches"] + reconciliation["curated_printings"]
        if item["collector_number"] == "n/2000"
    )
    assert rare_art["canonical_printed_identifier"] == "104/130"
    assert serialized_label["canonical_printed_identifier"] == "133/130"
