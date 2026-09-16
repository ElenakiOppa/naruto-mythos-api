"""
Model-level tests against an isolated in-memory SQLite database (see
tests/conftest.py's `db_session` fixture).

All fixtures used here are obviously fictional (TEST-*, "Test Character
Alpha", "Test Set Alpha", ...) -- no real Naruto Mythos data is used or
required for these tests to be meaningful.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Card, CardImage, CardSet, CardVariant, Keyword, SourceRecord, card_keywords


def make_set(db_session, public_id="TEST-SET-1", name="Test Set Alpha"):
    card_set = CardSet(public_id=public_id, name=name)
    db_session.add(card_set)
    db_session.commit()
    return card_set


def make_card(
    db_session, card_set, public_id="TEST-001", card_number="001", name="Test Character Alpha"
):
    card = Card(public_id=public_id, set_id=card_set.id, card_number=card_number, name=name)
    db_session.add(card)
    db_session.commit()
    return card


# ---------------------------------------------------------------------------
# CardSet
# ---------------------------------------------------------------------------


def test_set_can_be_created(db_session):
    card_set = make_set(db_session)

    assert card_set.id is not None
    assert card_set.public_id == "TEST-SET-1"
    assert card_set.language == "EN"


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------


def test_card_can_belong_to_set(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    assert card.set_id == card_set.id
    assert card.set.public_id == card_set.public_id


def test_card_public_id_uniqueness(db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set, public_id="DUP-001", card_number="001")

    duplicate = Card(public_id="DUP-001", set_id=card_set.id, card_number="002", name="Other")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_card_number_may_repeat_across_different_sets(db_session):
    set_a = make_set(db_session, public_id="SET-A", name="Test Set A")
    set_b = make_set(db_session, public_id="SET-B", name="Test Set B")
    make_card(db_session, set_a, public_id="A-001", card_number="001")

    card_in_other_set = Card(
        public_id="B-001", set_id=set_b.id, card_number="001", name="Test Character Beta"
    )
    db_session.add(card_in_other_set)
    db_session.commit()  # must succeed -- same number, different set

    assert card_in_other_set.id is not None


def test_duplicate_card_number_within_same_set_is_rejected(db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set, public_id="X-001", card_number="001")

    duplicate_number = Card(
        public_id="X-002", set_id=card_set.id, card_number="001", name="Duplicate Number"
    )
    db_session.add(duplicate_number)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_card_number_accepts_non_numeric_strings(db_session):
    card_set = make_set(db_session)
    card = Card(
        public_id="NN-001", set_id=card_set.id, card_number="SP-01a", name="Non Numeric Number"
    )
    db_session.add(card)
    db_session.commit()

    assert card.card_number == "SP-01a"


def test_negative_chakra_rejected(db_session):
    card_set = make_set(db_session)
    card = Card(
        public_id="NEG-CHAKRA", set_id=card_set.id, card_number="001", name="Bad Chakra", chakra=-1
    )
    db_session.add(card)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_negative_power_accepted(db_session):
    card_set = make_set(db_session)
    card = Card(
        public_id="NEG-POWER",
        set_id=card_set.id,
        card_number="001",
        name="Fictional Modifier",
        power=-5,
    )
    db_session.add(card)
    db_session.commit()
    assert db_session.get(Card, card.id).power == -5


# ---------------------------------------------------------------------------
# CardVariant
# ---------------------------------------------------------------------------


def test_variant_can_belong_to_card(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    variant = CardVariant(public_id="TEST-001-V1", card_id=card.id, variant_type="holographic")
    db_session.add(variant)
    db_session.commit()

    assert variant.card_id == card.id
    assert variant.card.public_id == card.public_id


def test_variant_public_id_uniqueness(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    db_session.add(CardVariant(public_id="DUPV-1", card_id=card.id, variant_type="normal"))
    db_session.commit()

    duplicate = CardVariant(public_id="DUPV-1", card_id=card.id, variant_type="gold")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_serial_total_rejected(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    variant = CardVariant(
        public_id="BADSERIAL-1",
        card_id=card.id,
        variant_type="numbered",
        serial_numbered=True,
        serial_total=0,
    )
    db_session.add(variant)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_serial_numbered_false_does_not_require_serial_total(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    variant = CardVariant(
        public_id="NOSERIAL-1", card_id=card.id, variant_type="normal", serial_numbered=False
    )
    db_session.add(variant)
    db_session.commit()

    assert variant.serial_total is None


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


def test_keyword_many_to_many_relationship_works(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    keyword = Keyword(slug="team-7", name="Team 7")

    card.keywords.append(keyword)
    db_session.add(card)
    db_session.commit()

    assert keyword in card.keywords
    assert card in keyword.cards


def test_duplicate_card_keyword_association_is_rejected(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    keyword = Keyword(slug="sharingan", name="Sharingan")
    db_session.add_all([card, keyword])
    db_session.commit()

    db_session.execute(card_keywords.insert().values(card_id=card.id, keyword_id=keyword.id))
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(card_keywords.insert().values(card_id=card.id, keyword_id=keyword.id))
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Card images
# ---------------------------------------------------------------------------


def test_card_image_without_variant_works(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    image = CardImage(card_id=card.id, url="https://example.invalid/fake.png")
    db_session.add(image)
    db_session.commit()

    assert image.variant_id is None
    assert image.card_id == card.id


def test_card_image_with_variant_works(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    variant = CardVariant(public_id="IMGVAR-1", card_id=card.id, variant_type="holographic")
    db_session.add(variant)
    db_session.commit()

    image = CardImage(
        card_id=card.id, variant_id=variant.id, url="https://example.invalid/holo.png"
    )
    db_session.add(image)
    db_session.commit()

    assert image.variant_id == variant.id


def test_invalid_negative_image_dimensions_rejected(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    bad_width = CardImage(card_id=card.id, url="https://example.invalid/a.png", width=-100)
    db_session.add(bad_width)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    bad_height = CardImage(card_id=card.id, url="https://example.invalid/b.png", height=-1)
    db_session.add(bad_height)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Source records
# ---------------------------------------------------------------------------


def test_source_record_can_reference_an_entity_uuid(db_session):
    card_set = make_set(db_session)

    record = SourceRecord(entity_type="set", entity_id=card_set.id, source_name="test-fixture")
    db_session.add(record)
    db_session.commit()

    assert record.entity_id == card_set.id
    assert record.entity_type == "set"


# ---------------------------------------------------------------------------
# Cascade / delete behavior
# ---------------------------------------------------------------------------


def test_deleting_card_cascades_to_variants_images_and_keywords(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    variant = CardVariant(public_id="CASC-V1", card_id=card.id, variant_type="normal")
    image = CardImage(card_id=card.id, url="https://example.invalid/fake.png")
    keyword = Keyword(slug="cascade-test", name="Cascade Test")
    card.keywords.append(keyword)
    db_session.add_all([variant, image])
    db_session.commit()

    variant_id, image_id, card_id, keyword_id = variant.id, image.id, card.id, keyword.id

    db_session.delete(card)
    db_session.commit()

    assert db_session.get(CardVariant, variant_id) is None
    assert db_session.get(CardImage, image_id) is None
    # The keyword itself is independent, reusable catalogue data -- only the
    # association row should be removed, never the keyword.
    assert db_session.get(Keyword, keyword_id) is not None
    remaining_links = db_session.execute(
        card_keywords.select().where(card_keywords.c.card_id == card_id)
    ).fetchall()
    assert remaining_links == []


def test_deleting_variant_nulls_image_variant_id_instead_of_deleting_image(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    variant = CardVariant(public_id="CASC-V2", card_id=card.id, variant_type="normal")
    db_session.add(variant)
    db_session.commit()

    image = CardImage(
        card_id=card.id, variant_id=variant.id, url="https://example.invalid/fake.png"
    )
    db_session.add(image)
    db_session.commit()
    image_id = image.id

    db_session.delete(variant)
    db_session.commit()

    refreshed_image = db_session.get(CardImage, image_id)
    assert refreshed_image is not None
    assert refreshed_image.variant_id is None


def test_deleting_variant_does_not_delete_parent_card(db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    variant = CardVariant(public_id="CASC-V3", card_id=card.id, variant_type="normal")
    db_session.add(variant)
    db_session.commit()
    card_id = card.id

    db_session.delete(variant)
    db_session.commit()

    assert db_session.get(Card, card_id) is not None


def test_set_with_existing_cards_cannot_be_deleted(db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    db_session.delete(card_set)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
