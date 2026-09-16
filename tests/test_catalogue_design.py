"""Phase 13B catalogue-design analysis tests.

Uses small invented fixtures only -- never the real 636-record catalogue and
never bulk copyrighted card text. Exercises the pure analysis functions in
`importer.catalogue_design`.
"""

from __future__ import annotations

import pytest

from importer.catalogue_design.analyzer import (
    audit_sku,
    audit_uid,
    card_grouping_report,
    collision_key_progression,
    language_invariance_check,
    map_all_records,
    round_trip_ok,
)
from importer.catalogue_design.identity import (
    CanonicalCardKey,
    CanonicalPrintingKey,
    nfc_canonical_json,
)
from importer.catalogue_design.models import MappingState, SourceCardRecord


def make_record(**overrides) -> SourceCardRecord:
    base = {
        "Uid": 1,
        "SKU": "TEST-C001V1",
        "ID": "001/999",
        "Set": "Test Set",
        "Edition": "1st edition",
        "Langs": ["en"],
        "CardType": "Character",
        "Title": "Test Character",
        "Rarity": "C",
        "Variant": None,
        "Illustration": "Standard",
        "CardVersion": "V1",
        "Version": "",
        "Group": "Test Village",
        "Chakra": 1,
        "Power": 1,
        "Points": "",
        "Keyword1": "",
        "Keyword2": "",
        "Text": "",
        "Obtain": "",
        "Stamp": "",
        "Image": "https://cards.narutotcgmythos.com/storage/cards/test-en-abc.webp",
        "Order": 1,
    }
    base.update(overrides)
    return SourceCardRecord.from_raw(base)


# --------------------------------------------------------------------------
# Canonical identity
# --------------------------------------------------------------------------


def test_canonical_printing_identity_deterministic():
    r = make_record()
    key = CanonicalPrintingKey.from_record(r)
    assert key.identity_hash() == CanonicalPrintingKey.from_record(r).identity_hash()
    assert key.analysis_public_id().startswith("prn_")


def test_canonical_identity_excludes_mutable_title():
    r1 = make_record(Title="Original Title")
    r2 = make_record(Title="Corrected Title")
    assert (
        CanonicalPrintingKey.from_record(r1).identity_hash()
        == CanonicalPrintingKey.from_record(r2).identity_hash()
    )


def test_canonical_identity_excludes_image_url():
    r1 = make_record(Image="https://cards.narutotcgmythos.com/storage/cards/a-en-1.webp")
    r2 = make_record(Image="https://cards.narutotcgmythos.com/storage/cards/a-en-2.webp")
    assert (
        CanonicalPrintingKey.from_record(r1).identity_hash()
        == CanonicalPrintingKey.from_record(r2).identity_hash()
    )


def test_canonical_identity_excludes_source_uid():
    # Human-review decision: source_uid must NOT participate in canonical
    # semantic identity. Two records identical in every semantic field but
    # differing only by Uid must produce the SAME identity hash.
    r1 = make_record(Uid=1)
    r2 = make_record(Uid=2)
    assert (
        CanonicalPrintingKey.from_record(r1).identity_hash()
        == CanonicalPrintingKey.from_record(r2).identity_hash()
    )


def test_canonical_identity_excludes_sku():
    r1 = make_record(SKU="NM-S1E1-C001V1")
    r2 = make_record(SKU="NM-S1E1-C001V1-REPRINT")
    assert (
        CanonicalPrintingKey.from_record(r1).identity_hash()
        == CanonicalPrintingKey.from_record(r2).identity_hash()
    )


def test_public_printing_id_stable_across_source_uid_change():
    # Simulates a source refresh: the vendor reassigns Uid but every semantic
    # field (including card_version/stamp) is unchanged -- the public
    # Printing ID must remain stable so the same real printing is recognized.
    before = make_record(Uid=100)
    after = make_record(Uid=999)
    assert (
        CanonicalPrintingKey.from_record(before).analysis_public_id()
        == CanonicalPrintingKey.from_record(after).analysis_public_id()
    )


def test_rarity_correction_changes_identity_hash():
    # Rarity IS identity-bearing (evidence: section 7/24 of the report), so a
    # rarity relabeling mechanically changes the hash -- this is the trigger
    # for a REQUIRE REVIEW reconciliation workflow, not a silent merge.
    original = make_record(Rarity="C")
    corrected = make_record(Rarity="UC")
    assert (
        CanonicalPrintingKey.from_record(original).identity_hash()
        != CanonicalPrintingKey.from_record(corrected).identity_hash()
    )


def test_edition_correction_changes_identity_hash():
    original = make_record(Edition="1st edition")
    corrected = make_record(Edition="2nd edition")
    assert (
        CanonicalPrintingKey.from_record(original).identity_hash()
        != CanonicalPrintingKey.from_record(corrected).identity_hash()
    )


def test_card_version_and_stamp_resolve_real_world_collision_pattern():
    # Mirrors the real Mythos residual-collision pattern (Phase 13B
    # identity-closure review): two records share expansion/edition/id/
    # rarity/variant but differ by card_version -- distinguished without uid.
    v1 = make_record(Uid=1, CardVersion="V1", Stamp="")
    v2 = make_record(Uid=2, CardVersion="V2", Stamp="Weekly Tournaments")
    assert (
        CanonicalPrintingKey.from_record(v1).identity_hash()
        != CanonicalPrintingKey.from_record(v2).identity_hash()
    )


def test_stamp_resolves_collision_when_card_version_also_matches():
    # The one real residual case (126/140): same card_version, distinguished
    # only by Stamp (a small controlled vocabulary, not freeform Obtain text).
    a = make_record(Uid=1, CardVersion="V2", Stamp="Release Event")
    b = make_record(Uid=2, CardVersion="V2", Stamp="Regional Championship")
    assert (
        CanonicalPrintingKey.from_record(a).identity_hash()
        != CanonicalPrintingKey.from_record(b).identity_hash()
    )


def test_canonical_printing_identity_requires_core_fields():
    incomplete = make_record(Rarity=None)
    with pytest.raises(ValueError):
        CanonicalPrintingKey.from_record(incomplete)


def test_canonical_card_identity_ignores_rarity_edition_variant():
    key_a = CanonicalCardKey(expansion="Test Set", printed_identifier="001/999")
    key_b = CanonicalCardKey(expansion="Test Set", printed_identifier="001/999")
    assert key_a.identity_hash() == key_b.identity_hash()
    assert key_a.analysis_public_id().startswith("crd_")


def test_unicode_nfc_normalization_makes_equivalent_forms_identical():
    decomposed = "Shido\u0304"  # "o" + combining macron
    precomposed = "Shid\u014d"  # precomposed o-macron
    assert nfc_canonical_json({"name": decomposed}) == nfc_canonical_json({"name": precomposed})


# --------------------------------------------------------------------------
# Uid / SKU audits
# --------------------------------------------------------------------------


def test_uid_audit_detects_duplicates_and_nulls():
    records = [make_record(Uid=1), make_record(Uid=1), make_record(Uid=None)]
    result = audit_uid(records)
    assert result.total == 3
    assert result.null_count == 1
    assert result.duplicate_uids == (1,)


def test_sku_audit_flags_non_conforming_pattern():
    records = [make_record(SKU="NM-S1E1-C001V1"), make_record(SKU="WEIRD-FORMAT")]
    result = audit_sku(records)
    assert result.total == 2
    assert result.strict_pattern_matches == 1
    assert "WEIRD-FORMAT" in result.unmatched_sample


# --------------------------------------------------------------------------
# Collision-key progression
# --------------------------------------------------------------------------


def test_collision_key_progression_resolves_with_rarity():
    # Two records sharing (set,id) but different rarity: collides at set+id,
    # resolves once rarity is added.
    records = [
        make_record(Uid=1, ID="050/999", Rarity="C"),
        make_record(Uid=2, ID="050/999", Rarity="R"),
    ]
    results = {r.key_name: r for r in collision_key_progression(records)}
    assert results["set+id"].colliding_keys == 1
    assert results["set+edition+id+rarity"].colliding_keys == 0


def test_repeated_printed_number_across_editions_resolves_with_edition():
    records = [
        make_record(Uid=1, ID="MSS 01", Edition="1st edition", Rarity="Mission"),
        make_record(Uid=2, ID="MSS 01", Edition="2nd edition", Rarity="Mission"),
    ]
    results = {r.key_name: r for r in collision_key_progression(records)}
    assert results["set+id"].colliding_keys == 1
    assert results["set+edition+id"].colliding_keys == 0


# --------------------------------------------------------------------------
# Card grouping validation
# --------------------------------------------------------------------------


def test_normal_and_full_art_group_under_one_card():
    normal = make_record(Uid=1, ID="001/999", Variant=None)
    full_art = make_record(Uid=2, ID="001/999", Variant="Full Art")
    report = card_grouping_report([normal, full_art])
    assert report.group_count == 1
    assert report.groups_with_multiple_printings == 1
    assert report.title_cardtype_invariant_groups == 1
    assert report.mismatched_groups == ()


def test_card_grouping_flags_title_mismatch_without_silent_grouping():
    a = make_record(Uid=1, ID="001/999", Title="Character A")
    b = make_record(Uid=2, ID="001/999", Title="Character B")
    report = card_grouping_report([a, b])
    assert report.groups_with_multiple_printings == 1
    assert report.title_cardtype_invariant_groups == 0
    assert len(report.mismatched_groups) == 1


# --------------------------------------------------------------------------
# All-record mapping: MAPPED / AMBIGUOUS / REJECTED, never silently dropped
# --------------------------------------------------------------------------


def test_mapping_classifies_every_record_and_never_drops_one():
    records = [
        make_record(Uid=1, ID="001/999"),
        make_record(Uid=None, ID="002/999"),  # REJECTED: missing uid
        make_record(Uid=2, Set=""),  # REJECTED: missing set
    ]
    summary = map_all_records(records)
    assert summary.total == len(records)
    assert summary.mapped == 1
    assert summary.rejected == 2
    assert summary.ambiguous == 0


def test_mapping_detects_reused_uid_as_ambiguous_not_merged():
    a = make_record(Uid=1, ID="001/999", Title="First printing")
    # Same Uid reused with identical identity-bearing fields (title is mutable
    # and intentionally excluded from identity) -- must not be silently merged.
    b = make_record(Uid=1, ID="001/999", Title="Reused uid conflict")
    summary = map_all_records([a, b])
    assert summary.total == 2
    assert summary.mapped == 1
    assert summary.ambiguous == 1
    ambiguous_result = next(r for r in summary.results if r.state == MappingState.AMBIGUOUS)
    assert ambiguous_result.record_uid == 1


def test_mapping_detects_fingerprint_collision_across_different_uids():
    # The general case behind the identity-closure review: two DIFFERENT
    # source_uids sharing an identical semantic fingerprint must still be
    # flagged AMBIGUOUS -- collision detection never depends on source_uid.
    a = make_record(Uid=101, ID="001/999")
    b = make_record(Uid=202, ID="001/999")
    summary = map_all_records([a, b])
    assert summary.total == 2
    assert summary.mapped == 1
    assert summary.ambiguous == 1


def test_editionless_promo_is_mapped_not_rejected():
    promo = make_record(Uid=9, ID="050/999", Edition=None, Rarity="M")
    summary = map_all_records([promo])
    assert summary.mapped == 1
    assert summary.results[0].preserved_fields["edition"] is None


def test_unknown_rarity_value_preserved_verbatim():
    record = make_record(Uid=42, Rarity="FUTURE_RARITY_NOT_YET_SEEN")
    summary = map_all_records([record])
    assert summary.mapped == 1
    assert summary.results[0].preserved_fields["rarity"] == "FUTURE_RARITY_NOT_YET_SEEN"


def test_mapping_is_deterministic_across_runs():
    records = [make_record(Uid=1, ID="001/999"), make_record(Uid=2, ID="002/999")]
    first = map_all_records(records)
    second = map_all_records(records)
    assert [r.canonical_public_id for r in first.results] == [
        r.canonical_public_id for r in second.results
    ]


# --------------------------------------------------------------------------
# Round-trip and language-invariance
# --------------------------------------------------------------------------


def test_round_trip_preserves_source_fields():
    record = make_record(Uid=7, SKU="TEST-C007V1", ID="007/999")
    summary = map_all_records([record])
    result = summary.results[0]
    assert round_trip_ok(record, result)


def test_round_trip_fails_for_rejected_records():
    record = make_record(Uid=None)
    summary = map_all_records([record])
    result = summary.results[0]
    assert round_trip_ok(record, result) is False


def test_language_invariance_ignores_mutable_title_but_checks_identity_fields():
    en = make_record(Uid=1, Langs=["en"], Title="English Title")
    fr = make_record(Uid=1, Langs=["fr"], Title="Titre Francais")
    checked, mismatches = language_invariance_check({"en": [en], "fr": [fr]})
    assert checked == 1
    assert mismatches == []


def test_language_invariance_detects_real_identity_drift():
    en = make_record(Uid=1, Rarity="C")
    fr = make_record(Uid=1, Rarity="UC")  # identity-bearing field diverges
    checked, mismatches = language_invariance_check({"en": [en], "fr": [fr]})
    assert checked == 1
    assert len(mismatches) == 1
    assert mismatches[0]["field"] == "rarity"
