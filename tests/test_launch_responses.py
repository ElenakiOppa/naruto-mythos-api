"""Focused Phase 17 response regressions, fictional persisted data only."""

import pytest
from sqlalchemy import select

from app.models import Card, CardImage, CardSet, CardVariant, PrintingTranslation
from app.schemas.card import CardDetail, CardSummary
from app.services.card_service import get_card_by_public_id
from importer.catalogue_importer import _build_plan
from importer.catalogue_persistence import persist_catalogue_plan
from tests.test_catalogue_persistence import record


@pytest.mark.parametrize(
    "kind,power,points", [("Mission", None, 3), ("Character", 4, None), ("Attachment", -1, None)]
)
def test_detail_points_signed_power_and_summary(db_session, client, kind, power, points):
    card = Card(
        public_id="fictional-launch",
        card_number="001",
        name="Fictional Launch",
        card_type=kind,
        power=power,
        points=points,
        set=CardSet(public_id="fictional-set", name="Fictional Set"),
    )
    db_session.add(card)
    db_session.commit()
    response = client.get("/v1/cards/fictional-launch")
    assert response.status_code == 200
    assert response.json()["points"] == points
    assert response.json()["power"] == power
    assert "points" not in CardSummary.model_validate(card).model_dump()


def test_localized_urls_override_stale_images_without_writes(db_session, client):
    card = Card(
        public_id="fictional-images",
        card_number="01",
        name="Fictional Images",
        set=CardSet(public_id="fictional-set", name="Fictional Set"),
    )
    printing = CardVariant(
        public_id="prn_fictional",
        card=card,
        variant_type="legacy-type",
        source_variant="Publisher Foil",
        card_version="V2",
        stamp="Fictional Event",
        edition=None,
        rarity_override="Publisher Rare",
    )
    urls = {
        "EN": "https://example.invalid/en.png",
        "FR": "https://example.invalid/fr.png",
        "IT": "https://example.invalid/en.png",
        "ES": None,
    }
    for language, url in urls.items():
        printing.translations.append(PrintingTranslation(language=language, image_url=url))
        db_session.add(
            CardImage(
                card=card,
                variant=printing,
                image_type=f"front-{language.lower()}",
                url=urls["EN"],
                width=100,
                height=200,
            )
        )
    db_session.commit()
    response = client.get("/v1/cards/fictional-images")
    assert response.status_code == 200
    variant = response.json()["variants"][0]
    images = {image["type"]: image for image in variant["images"]}
    assert {k: v["url"] for k, v in images.items()} == {
        "front-en": urls["EN"],
        "front-fr": urls["FR"],
        "front-it": urls["IT"],
    }
    assert images["front-fr"]["width"] is None  # English dimensions don't describe a new URL.
    assert images["front-en"]["width"] == 100
    assert variant["id"] == "prn_fictional"
    assert variant["source_variant"] == "Publisher Foil"
    assert variant["card_version"] == "V2"
    assert variant["stamp"] == "Fictional Event"
    assert variant["edition"] is None and variant["rarity"] == "Publisher Rare"
    assert variant["type"] == "legacy-type" and variant["finish"] is None
    assert not db_session.dirty
    assert all(image.url == urls["EN"] for image in db_session.scalars(select(CardImage)))


def test_acquisition_plan_and_persistence_keep_each_language_url(db_session):
    urls = {
        "en": "https://example.invalid/en.webp",
        "fr": "https://example.invalid/fr.webp",
        "it": "https://example.invalid/en.webp",
        "es": "https://example.invalid/es.webp",
    }
    plan, _ = _build_plan({language: [record(1, Image=url)] for language, url in urls.items()})
    persist_catalogue_plan(db_session, {"plan": plan})
    stored = {image.image_type: image.url for image in db_session.scalars(select(CardImage))}
    assert stored == {f"front-{lang}": url for lang, url in urls.items()}
    card = get_card_by_public_id(db_session, plan["cards"][0]["public_id"])
    payload = CardDetail.model_validate(card).model_dump()
    assert {i["type"]: i["url"] for i in payload["variants"][0]["images"]} == stored
    assert payload["power"] == -1


def test_translation_only_reference_and_legacy_fallback(db_session):
    card = Card(
        public_id="fictional",
        card_number="01",
        name="Fictional",
        set=CardSet(public_id="set", name="Set"),
    )
    variant = CardVariant(card=card, public_id="legacy-id", variant_type="unchanged")
    variant.translations.append(
        PrintingTranslation(language="FR", image_url="https://example.invalid/fr.png")
    )
    db_session.add(
        CardImage(
            card=card, variant=variant, image_type="front", url="https://example.invalid/legacy.png"
        )
    )
    db_session.commit()
    payload = CardDetail.model_validate(
        get_card_by_public_id(db_session, card.public_id)
    ).model_dump()
    images = payload["variants"][0]["images"]
    assert {i["type"] for i in images} == {"front", "front-fr"}
    assert payload["variants"][0]["source_variant"] is None
