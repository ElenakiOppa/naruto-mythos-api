"""Focused fictional tests for the Phase 14 read-only catalogue importer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.catalogue_design.identity import CanonicalPrintingKey
from importer.catalogue_design.models import SourceCardRecord
from importer.catalogue_importer import CatalogueImportError, _build_plan, build_dry_run


def record(uid: int, **overrides) -> SourceCardRecord:
    values = {
        "Uid": uid,
        "SKU": f"FICTIONAL-{uid}",
        "ID": "001/999",
        "Set": "Fictional Expansion",
        "Edition": "1st edition",
        "Langs": ["en"],
        "CardType": "Attachment",
        "Title": "Fictional Weight",
        "Rarity": "C",
        "Variant": "Holo",
        "Illustration": "Standard",
        "CardVersion": "V1",
        "Version": "",
        "Group": "Independent",
        "Chakra": 1,
        "Power": -1,
        "Points": "",
        "Keyword1": "Weapon",
        "Keyword2": "",
        "Text": "fictional rules",
        "Obtain": "",
        "Stamp": "",
        "Image": f"https://example.invalid/{uid}.webp",
        "Order": uid,
    }
    values.update(overrides)
    return SourceCardRecord.from_raw(values)


def test_dry_run_preserves_signed_power_localization_and_provenance():
    en = record(1)
    fr = record(
        1,
        Langs=["fr"],
        Title="Poids fictif",
        Text="regles fictives",
        Image="https://example.invalid/fr.webp",
    )
    plan, report = _build_plan({"en": [en], "fr": [fr]})

    assert report["source_records"] == 1
    assert report["unique_cards"] == 1
    assert report["unique_printings"] == 1
    assert report["negative_power_count"] == 1
    assert report["localization_count_by_language"] == {"en": 1, "fr": 1}
    printing = plan["printings"][0]
    assert printing["source_uid"] == "1"
    assert printing["source_sku"] == "FICTIONAL-1"
    assert printing["localizations"]["fr"]["image_url"].endswith("fr.webp")
    assert printing["identity"]["rarity"] == "C"
    assert printing["identity"]["variant"] == "Holo"
    assert printing["taxonomy"]["normalized_rarity"] == "Common"
    assert printing["taxonomy"]["normalized_treatment"] == "Holographic"
    assert printing["serial_numbered"] is None
    assert printing["serial_total"] is None


def test_card_version_and_stamp_are_printing_identity_fields():
    first = record(1, CardVersion="V1", Stamp="")
    second = record(2, CardVersion="V2", Stamp="Store Championship")
    first_plan, first_report = _build_plan({"en": [first]})
    second_plan, second_report = _build_plan({"en": [second]})
    assert first_report["unique_cards"] == second_report["unique_cards"] == 1
    assert first_plan["printings"][0]["public_id"] != second_plan["printings"][0]["public_id"]


def test_source_uid_change_does_not_change_printing_identity():
    first_plan, _ = _build_plan({"en": [record(1)]})
    second_plan, _ = _build_plan({"en": [record(99, SKU="FICTIONAL-CHANGED")]})
    assert first_plan["printings"][0]["public_id"] == second_plan["printings"][0]["public_id"]


def test_nullable_edition_is_preserved():
    plan, _ = _build_plan({"en": [record(1, Edition="", Rarity="M")]})
    assert plan["printings"][0]["identity"]["edition"] is None
    assert plan["printings"][0]["edition_public_id"] is None
    assert plan["editions"] == []


def test_official_shinobi_taxonomy_preserves_raw_labels_without_expanding_abbreviations():
    plan, _ = _build_plan(
        {
            "en": [
                record(1, Rarity="M", Variant="Normale"),
                record(2, ID="002/999", Rarity="CHIBI", Variant=""),
            ]
        }
    )

    by_id = {printing["identity"]["printed_identifier"]: printing for printing in plan["printings"]}
    normale = by_id["001/999"]
    chibi = by_id["002/999"]
    assert normale["identity"]["variant"] == "Normale"
    assert normale["taxonomy"]["normalized_treatment"] == "Normal"
    assert normale["taxonomy"]["variant_resolution_status"] == "MAPPED"
    assert chibi["identity"]["rarity"] == "CHIBI"
    assert chibi["taxonomy"]["normalized_rarity"] == "Chibi"
    assert chibi["taxonomy"]["rarity_resolution_status"] == "MAPPED"
    assert chibi["taxonomy"]["variant_resolution_status"] == "UNSPECIFIED"

    for raw_rarity in ("POP", "SP", "Shinobi"):
        item, _ = _build_plan({"en": [record(3, Rarity=raw_rarity, Variant="")]})
        assert item["printings"][0]["taxonomy"]["normalized_rarity"] == raw_rarity
        assert item["printings"][0]["taxonomy"]["rarity_resolution_status"] == "MAPPED"


def test_edition_reprints_share_one_canonical_card():
    plan, report = _build_plan(
        {
            "en": [
                record(1, ID="001/999", Edition="1st edition"),
                record(2, ID="001/999", Edition="2nd edition"),
            ]
        }
    )

    assert report["unique_cards"] == 1
    assert report["unique_printings"] == 2
    assert len(plan["cards"]) == 1
    assert len(plan["editions"]) == 2
    assert {printing["card_id"] for printing in plan["printings"]} == {
        plan["cards"][0]["public_id"]
    }


def test_rarity_and_treatment_differences_remain_printings_of_one_card():
    plan, report = _build_plan(
        {
            "en": [
                record(1, ID="001/999", Rarity="C", Variant="Normal"),
                record(2, ID="001/999", Rarity="C", Variant="Full Art"),
                record(3, ID="001/999", Rarity="C", Variant="Holo"),
                record(4, ID="104/999", Rarity="R", Variant=""),
                record(5, ID="104/999", Rarity="RA", Variant=""),
            ]
        }
    )

    assert report["unique_cards"] == 2
    assert report["unique_printings"] == 5
    treatment_printings = [
        p for p in plan["printings"] if p["identity"]["printed_identifier"] == "001/999"
    ]
    rarity_printings = [
        p for p in plan["printings"] if p["identity"]["printed_identifier"] == "104/999"
    ]
    assert len({printing["card_id"] for printing in treatment_printings}) == 1
    assert len({printing["card_id"] for printing in rarity_printings}) == 1
    treatments = {
        p["identity"]["variant"]: p["taxonomy"]["normalized_treatment"] for p in treatment_printings
    }
    assert treatments == {"Normal": "Normal", "Full Art": "FullArt", "Holo": "Holographic"}
    assert {p["identity"]["rarity"] for p in rarity_printings} == {"R", "RA"}


def test_case_and_locale_normalization_does_not_change_printing_fingerprint():
    lower_plan, _ = _build_plan({"en": [record(1, Edition="1st edition")]})
    upper_plan, _ = _build_plan({"en": [record(1, Edition="1st Edition")]})

    assert lower_plan["printings"][0]["public_id"] == upper_plan["printings"][0]["public_id"]
    assert lower_plan["printings"][0]["identity"]["edition"] == "1st edition"
    assert upper_plan["printings"][0]["identity"]["edition"] == "1st edition"
    assert upper_plan["printings"][0]["edition_text"] == "1st Edition"


def test_case_and_language_variants_resolve_same_set_edition():
    english_one = record(1, ID="001/999", Edition="1st edition")
    english_two = record(2, ID="002/999", Edition="1st Edition", Variant="Full Art")
    french_one = record(
        1,
        ID="001/999",
        Edition="1st Edition",
        Langs=["fr"],
        Title="Poids fictif",
    )
    french_two = record(
        2,
        ID="002/999",
        Edition="1st edition",
        Variant="Full Art",
        Langs=["fr"],
        Title="Autre poids fictif",
    )
    plan, report = _build_plan({"en": [english_one, english_two], "fr": [french_one, french_two]})

    assert report["unique_editions"] == 1
    assert report["localization_count_by_language"] == {"en": 2, "fr": 2}
    assert len(plan["editions"]) == 1
    assert {printing["edition_public_id"] for printing in plan["printings"]} == {
        plan["editions"][0]["public_id"]
    }


def test_case_normalization_collision_is_rejected_not_merged():
    with pytest.raises(
        CatalogueImportError,
        match="DUPLICATE_SEMANTIC_PRINTING",
    ):
        _build_plan(
            {
                "en": [
                    record(1, Edition="1st edition"),
                    record(2, Edition="1st Edition"),
                ]
            }
        )


def test_mission_points_are_counted():
    mission = record(1, CardType="Mission", Power="", Chakra="", Points="2")
    _, report = _build_plan({"en": [mission]})
    assert report["card_type_counts"] == {"Mission": 1}
    assert report["mission_points_count"] == 1


def test_duplicate_semantic_printing_is_rejected():
    with pytest.raises(CatalogueImportError, match="DUPLICATE_SEMANTIC_PRINTING"):
        _build_plan({"en": [record(1), record(2)]})


def test_conflicting_card_grouping_is_rejected():
    with pytest.raises(CatalogueImportError, match="CARD_GROUPING_CONFLICT"):
        _build_plan({"en": [record(1), record(2, Title="Different Concept")]})


@pytest.mark.skipif(
    not any(Path("data/acquisition/raw").glob("*")),
    reason="raw acquisition is intentionally local and untracked",
)
def test_audited_snapshot_counts_and_edition_inventory():
    result = build_dry_run()
    report = result["report"]

    assert report["unique_cards"] == 318
    assert report["unique_printings"] == 636
    assert report["edition_count_by_set"] == {
        "Set 1: Konoha Shidō": 2,
        "Set 2: Shinobi Shiren": 1,
    }
    assert report["normalized_identity_collision_count"] == 0
    printings = result["plan"]["printings"]
    assert len(printings) == 636
    assert dict(Counter(p["taxonomy"]["rarity_resolution_status"] for p in printings)) == {
        "MAPPED": 636,
    }
    assert dict(Counter(p["taxonomy"]["variant_resolution_status"] for p in printings)) == {
        "MAPPED": 319,
        "UNSPECIFIED": 317,
    }
    assert all(p["serial_numbered"] is None and p["serial_total"] is None for p in printings)

    source = load_records_from_acquisition()["en"]
    old_public_ids = {
        CanonicalPrintingKey(
            expansion=item.set,
            edition=item.edition,
            printed_identifier=item.id,
            rarity=item.rarity,
            variant=item.variant,
            card_version=item.card_version,
            stamp=item.stamp or None,
        ).analysis_public_id()
        for item in source
    }
    normalized_public_ids = {
        CanonicalPrintingKey.from_record(item).analysis_public_id() for item in source
    }
    assert len(old_public_ids) == len(normalized_public_ids) == 636
    assert old_public_ids == normalized_public_ids

    first_edition = [
        item
        for item in source
        if item.set == "Set 1: Konoha Shidō" and item.edition == "1st edition"
    ]
    first_card_counts = Counter(item.id for item in first_edition)
    assert len(first_edition) == 186
    assert len(first_card_counts) == 154
    assert sum(count > 1 for count in first_card_counts.values()) == 31
    assert sum(count == 1 for count in first_card_counts.values()) == 123
    assert dict(Counter(item.rarity for item in first_edition)) == {
        "C": 55,
        "L": 1,
        "M": 4,
        "Mission": 10,
        "R": 27,
        "RA": 27,
        "S": 10,
        "SV": 4,
        "UC": 48,
    }
    assert dict(Counter(item.variant or "<blank>" for item in first_edition)) == {
        "<blank>": 83,
        "Full Art": 103,
    }
    assert sum(not item.variant for item in first_edition) == 83

    editionless = [
        item for item in source if item.set == "Set 1: Konoha Shidō" and not item.edition
    ]
    assert len(editionless) == 21
    assert len({item.id for item in editionless}) == 15
    assert {item.id for item in editionless} <= {item.id for item in first_edition}
