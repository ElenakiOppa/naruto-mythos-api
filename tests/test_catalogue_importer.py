"""Focused fictional tests for the Phase 14 read-only catalogue importer."""

from __future__ import annotations

from pathlib import Path

import pytest

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
        match="DUPLICATE_SEMANTIC_PRINTING_AFTER_EDITION_NORMALIZATION",
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
