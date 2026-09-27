"""Fictional and source-label taxonomy mapping tests."""

import pytest
from sqlalchemy import func, select

from app.models import Card, CardSet, CardVariant, Edition
from app.utils.printing_taxonomy import normalize_printing_taxonomy


@pytest.mark.parametrize(
    ("raw_rarity", "normalized_rarity"),
    [
        ("C", "Common"),
        ("UC", "Uncommon"),
        ("R", "Rare"),
        ("RA", "Rare ART"),
        ("S", "Secret"),
        ("SV", "Secret Variant"),
        ("L", "Legendary"),
        ("M", "Mythos"),
        ("CHIBI", "Chibi"),
        ("POP", "POP"),
        ("SP", "SP"),
        ("Shinobi", "Shinobi"),
    ],
)
def test_reviewed_rarity_codes_map_exactly(raw_rarity, normalized_rarity):
    result = normalize_printing_taxonomy(raw_rarity, None, "Character")

    assert result.normalized_rarity == normalized_rarity
    assert result.collector_class is None
    assert result.rarity_resolution_status == "MAPPED"


@pytest.mark.parametrize(
    ("raw_variant", "normalized_treatment"),
    [
        ("Normal", "Normal"),
        ("Full Art", "FullArt"),
        ("Holo", "Holographic"),
        ("Gold", "Gold"),
        ("Normale", "Normal"),
    ],
)
def test_reviewed_treatments_map_exactly(raw_variant, normalized_treatment):
    result = normalize_printing_taxonomy("C", raw_variant, "Character")

    assert result.normalized_treatment == normalized_treatment
    assert result.variant_resolution_status == "MAPPED"


def test_mission_requires_matching_source_card_type():
    matched = normalize_printing_taxonomy("Mission", None, "Mission")
    mismatched = normalize_printing_taxonomy("Mission", None, "Character")

    assert matched.normalized_rarity is None
    assert matched.collector_class == "Mission"
    assert matched.rarity_resolution_status == "MAPPED"
    assert mismatched.collector_class is None
    assert mismatched.rarity_resolution_status == "UNRESOLVED"


def test_blank_variant_is_unspecified_not_normal():
    result = normalize_printing_taxonomy("C", "", "Character")

    assert result.normalized_treatment is None
    assert result.variant_resolution_status == "UNSPECIFIED"


@pytest.mark.parametrize("raw_variant", ["Foil-X"])
def test_unknown_variant_labels_remain_unresolved(raw_variant):
    result = normalize_printing_taxonomy("C", raw_variant, "Character")

    assert result.normalized_treatment is None
    assert result.variant_resolution_status == "UNRESOLVED"


@pytest.mark.parametrize("raw_rarity", ["RX"])
def test_ambiguous_and_unknown_rarity_values_remain_unresolved(raw_rarity):
    result = normalize_printing_taxonomy(raw_rarity, None, "Character")

    assert result.normalized_rarity is None
    assert result.collector_class is None
    assert result.rarity_resolution_status == "UNRESOLVED"


def test_normalization_is_deterministic_and_idempotent():
    original = normalize_printing_taxonomy("C", "Full Art", "Character")
    repeated = normalize_printing_taxonomy("C", "Full Art", "Character")
    normalized_input = normalize_printing_taxonomy(
        original.normalized_rarity, original.normalized_treatment, "Character"
    )

    assert original == repeated
    assert normalized_input == original


def test_three_treatments_are_printings_of_one_canonical_card(db_session):
    card_set = CardSet(public_id="TAXONOMY-SET", name="Fictional Set")
    edition = Edition(
        public_id="TAXONOMY-EDITION",
        set=card_set,
        name="1st Edition",
        normalized_name="1st edition",
    )
    card = Card(
        public_id="TAXONOMY-CARD-001",
        set=card_set,
        card_number="001",
        name="Fictional Character",
    )
    raw_variants = (None, "Full Art", "Holo")
    db_session.add_all([card_set, edition, card])
    db_session.flush()
    db_session.add_all(
        [
            CardVariant(
                public_id=f"TAXONOMY-PRINTING-{index}",
                card=card,
                edition_id=edition.id,
                edition="1st edition",
                variant_type=raw_variant or "unspecified",
                rarity_override="C",
                source_variant=raw_variant,
            )
            for index, raw_variant in enumerate(raw_variants)
        ]
    )
    db_session.flush()

    printings = db_session.scalars(select(CardVariant).order_by(CardVariant.public_id)).all()
    assert db_session.scalar(select(func.count()).select_from(Card)) == 1
    assert {printing.card_id for printing in printings} == {card.id}
    assert {printing.source_variant for printing in printings} == set(raw_variants)
    assert {printing.normalized_rarity for printing in printings} == {"Common"}
    assert {printing.normalized_treatment for printing in printings} == {
        None,
        "FullArt",
        "Holographic",
    }
    assert all(printing.serial_numbered is None for printing in printings)
    assert all(printing.serial_total is None for printing in printings)


def test_rarity_differences_remain_printings_under_one_card(db_session):
    card_set = CardSet(public_id="RARITY-SET", name="Fictional Set")
    card = Card(
        public_id="RARITY-CARD-001",
        set=card_set,
        card_number="104/999",
        name="Fictional Character",
    )
    db_session.add_all(
        [
            CardVariant(
                public_id="RARITY-PRINTING-R",
                card=card,
                variant_type="base",
                rarity_override="R",
            ),
            CardVariant(
                public_id="RARITY-PRINTING-RA",
                card=card,
                variant_type="base",
                rarity_override="RA",
            ),
        ]
    )
    db_session.flush()

    printings = db_session.scalars(select(CardVariant)).all()
    assert db_session.scalar(select(func.count()).select_from(Card)) == 1
    assert {printing.normalized_rarity for printing in printings} == {"Rare", "Rare ART"}
