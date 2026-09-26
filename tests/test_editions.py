"""Edition ownership and identity tests using fictional catalogue data."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Card, CardSet, CardVariant, Edition
from app.models.edition import normalize_edition_name
from importer.catalogue_design.identity import CanonicalEditionKey


def make_set(session, public_id: str, name: str) -> CardSet:
    card_set = CardSet(public_id=public_id, name=name)
    session.add(card_set)
    session.flush()
    return card_set


def make_edition(session, card_set: CardSet, label: str, public_id: str) -> Edition:
    edition = Edition(
        public_id=public_id,
        set=card_set,
        name=label,
        normalized_name=normalize_edition_name(label),
    )
    session.add(edition)
    session.flush()
    return edition


def test_edition_identity_is_normalized_and_scoped_to_set(db_session):
    first_set = make_set(db_session, "TEST-SET-A", "Test Set A")
    second_set = make_set(db_session, "TEST-SET-B", "Test Set B")

    first_edition = make_edition(db_session, first_set, "1st edition", "TEST-ED-A-1")
    second_edition = make_edition(db_session, second_set, "1st Edition", "TEST-ED-B-1")

    assert first_edition.normalized_name == second_edition.normalized_name == "1st edition"
    assert first_edition.set_id != second_edition.set_id


def test_edition_public_id_is_set_scoped_and_normalization_stable():
    first = CanonicalEditionKey("set-konoha", "1st edition").analysis_public_id()
    case_variant = CanonicalEditionKey("set-konoha", "1st edition").analysis_public_id()
    other_set = CanonicalEditionKey("set-shinobi", "1st edition").analysis_public_id()

    assert first == case_variant
    assert first != other_set


def test_duplicate_normalized_edition_in_one_set_is_rejected(db_session):
    card_set = make_set(db_session, "TEST-SET", "Test Set")
    make_edition(db_session, card_set, "1st edition", "TEST-ED-1")

    db_session.add(
        Edition(
            public_id="TEST-ED-DUP",
            set=card_set,
            name="1st Edition",
            normalized_name="ignored until flush",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_one_card_can_have_printings_in_two_editions(db_session):
    card_set = make_set(db_session, "TEST-SET", "Test Set")
    first = make_edition(db_session, card_set, "1st Edition", "TEST-ED-1")
    second = make_edition(db_session, card_set, "2nd Edition", "TEST-ED-2")
    card = Card(
        public_id="TEST-CARD-001",
        set=card_set,
        card_number="001",
        name="Fictional Character",
    )
    db_session.add(card)
    db_session.flush()
    db_session.add_all(
        [
            CardVariant(
                public_id="TEST-PRINTING-1",
                card=card,
                edition_record=first,
                variant_type="normal",
                edition="1st Edition",
            ),
            CardVariant(
                public_id="TEST-PRINTING-2",
                card=card,
                edition_record=second,
                variant_type="normal",
                edition="2nd Edition",
            ),
        ]
    )
    db_session.flush()

    assert db_session.scalar(select(func.count()).select_from(Card)) == 1
    assert {printing.card_id for printing in card.variants} == {card.id}
    assert {printing.edition_id for printing in card.variants} == {first.id, second.id}


def test_editionless_printing_is_valid_and_keeps_null_edition(db_session):
    card_set = make_set(db_session, "TEST-SET", "Test Set")
    card = Card(
        public_id="TEST-CARD-PROMO",
        set=card_set,
        card_number="PROMO-1",
        name="Fictional Promo",
    )
    printing = CardVariant(
        public_id="TEST-PRINTING-PROMO", card=card, variant_type="mythos", edition=None
    )
    db_session.add_all([card, printing])
    db_session.flush()

    assert printing.edition_id is None
    assert printing.edition_record is None


def test_printing_cannot_reference_an_edition_from_another_set(db_session):
    first_set = make_set(db_session, "TEST-SET-A", "Test Set A")
    second_set = make_set(db_session, "TEST-SET-B", "Test Set B")
    foreign_edition = make_edition(db_session, second_set, "1st Edition", "TEST-ED-B-1")
    card = Card(
        public_id="TEST-CARD-A-001",
        set=first_set,
        card_number="001",
        name="Fictional Character",
    )
    db_session.add(card)
    db_session.flush()
    db_session.add(
        CardVariant(
            public_id="TEST-PRINTING-CROSS-SET",
            card=card,
            edition_record=foreign_edition,
            variant_type="normal",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
