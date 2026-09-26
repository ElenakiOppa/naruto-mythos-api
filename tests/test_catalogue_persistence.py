"""Fictional persistence tests for the Phase 15 disposable import executor."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Card, CardVariant, Edition
from importer.catalogue_design.models import SourceCardRecord
from importer.catalogue_importer import _build_plan
from importer.catalogue_persistence import CataloguePersistenceError, persist_catalogue_plan


def record(uid: int, **overrides) -> SourceCardRecord:
    values = {
        "Uid": uid,
        "SKU": f"FICTIONAL-{uid}",
        "ID": f"00{uid}/999",
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


def plan():
    return _build_plan(
        {
            "en": [
                record(1),
                record(2, ID="MSS 01", CardType="Mission", Power="", Chakra="", Points="2"),
            ],
            "fr": [
                record(1, Langs=["fr"], Title="Poids fictif"),
                record(
                    2,
                    ID="MSS 01",
                    Langs=["fr"],
                    CardType="Mission",
                    Power="",
                    Chakra="",
                    Points="2",
                ),
            ],
        }
    )


def test_transactional_import_persists_domain_and_is_idempotent(db_session):
    result = {"plan": plan()[0]}
    first = persist_catalogue_plan(db_session, result)
    second = persist_catalogue_plan(db_session, result)

    assert first == second
    assert first.sets == 1
    assert first.editions == 1
    assert first.cards == 2
    assert first.printings == 2
    assert first.translations == 4
    assert first.provenance == 4
    assert first.image_references == 4
    assert first.keywords == 2
    assert first.associations == 4
    assert all(printing.edition_id is not None for printing in db_session.query(CardVariant))
    assert db_session.query(Edition).count() == 1


def test_two_edition_printings_persist_under_one_card(db_session):
    source_records = [
        record(1, ID="001/999", Edition="1st edition"),
        record(2, ID="001/999", Edition="2nd edition"),
    ]
    result = {"plan": _build_plan({"en": source_records})[0]}

    counts = persist_catalogue_plan(db_session, result)
    card_rows = db_session.query(Card).all()
    printing_rows = db_session.query(CardVariant).all()

    assert counts.cards == 1
    assert counts.printings == 2
    assert counts.editions == 2
    assert {printing.card_id for printing in printing_rows} == {card_rows[0].id}
    assert len({printing.edition_id for printing in printing_rows}) == 2


def test_signed_power_and_mission_points_survive_persistence(db_session):
    persist_catalogue_plan(db_session, {"plan": plan()[0]})
    from app.models import Card

    attachment = db_session.scalar(select(Card).where(Card.card_type == "Attachment"))
    mission = db_session.scalar(select(Card).where(Card.card_type == "Mission"))
    assert attachment is not None and attachment.power == -1
    assert mission is not None and mission.points == 2


def test_conflicting_existing_public_id_rolls_back(db_session):
    first_plan = plan()[0]
    persist_catalogue_plan(db_session, {"plan": first_plan})
    conflicting = plan()[0]
    conflicting["cards"][0]["title"] = "Conflicting title"
    with pytest.raises(CataloguePersistenceError):
        persist_catalogue_plan(db_session, {"plan": conflicting})

    from app.models import Card

    assert db_session.scalar(select(func.count()).select_from(Card)) == 2
