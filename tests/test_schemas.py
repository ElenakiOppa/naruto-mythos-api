"""
Tests for the Phase 3 public schema layer.

Builds fictional SQLAlchemy ORM instances (via the isolated in-memory
SQLite `db_session` fixture from conftest.py) and validates that Pydantic
schemas convert them into the exact public JSON contract: internal UUIDs
never leak, field names/aliases map correctly, list vs detail
representations are sized appropriately, and pagination/error/search
schemas behave as specified.

All fixture data is obviously fictional (TEST-*, "Test Character Alpha",
"Test Set Alpha", "test-keyword") -- no real Naruto Mythos data appears
anywhere in this file.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models import Card, CardImage, CardSet, CardVariant, Keyword
from app.schemas.card import CardDetail, CardSummary
from app.schemas.error import ErrorCode, ErrorDetail, ErrorResponse
from app.schemas.keyword import KeywordResponse
from app.schemas.pagination import PaginationMeta
from app.schemas.search import (
    CardSearchResult,
    KeywordSearchResult,
    SearchResponse,
    SearchResult,
    SetSearchResult,
)
from app.schemas.set import SetDetail, SetSummary
from app.schemas.variant import CardVariantResponse


@pytest.fixture()
def fictional_card(db_session):
    """A fictional card with a set, one variant, one image, and one keyword."""
    card_set = CardSet(
        public_id="test-set-1",
        code="TST1",
        name="Test Set Alpha",
        edition="1st Edition",
        language="EN",
    )
    db_session.add(card_set)
    db_session.commit()

    card = Card(
        public_id="TEST-001",
        set_id=card_set.id,
        card_number="001",
        name="Test Character Alpha",
        card_type="Character",
        rarity="Rare",
        chakra=4,
        power=5,
        faction="Test Village",
    )
    db_session.add(card)
    db_session.commit()

    variant = CardVariant(
        public_id="TEST-001-holographic",
        card_id=card.id,
        variant_type="holographic",
        finish="holo",
        language="EN",
        serial_numbered=False,
    )
    db_session.add(variant)

    image = CardImage(
        card_id=card.id,
        image_type="front",
        url="https://example.invalid/test-card.jpg",
        width=734,
        height=1024,
        hosted_by_us=False,
        source_name="test-fixture-source",
        source_url="https://example.invalid/source",
    )
    db_session.add(image)

    keyword = Keyword(slug="test-keyword", name="Test Keyword")
    card.keywords.append(keyword)
    db_session.add(card)
    db_session.commit()

    db_session.refresh(card)
    return card


# ---------------------------------------------------------------------------
# SetSummary / SetDetail
# ---------------------------------------------------------------------------


def test_set_summary_maps_fields_and_excludes_internal_uuid(fictional_card):
    schema = SetSummary.model_validate(fictional_card.set)
    dumped = schema.model_dump(mode="json")

    assert dumped == {
        "id": "test-set-1",
        "code": "TST1",
        "name": "Test Set Alpha",
        "edition": "1st Edition",
    }
    assert str(fictional_card.set.id) not in schema.model_dump_json()


def test_set_detail_maps_fields_and_excludes_internal_uuid(fictional_card):
    card_set = fictional_card.set
    schema = SetDetail.model_validate(card_set)
    dumped = schema.model_dump(mode="json")

    assert dumped["id"] == "test-set-1"
    assert dumped["code"] == "TST1"
    assert dumped["name"] == "Test Set Alpha"
    assert dumped["edition"] == "1st Edition"
    assert dumped["language"] == "EN"
    assert dumped["release_date"] is None
    assert dumped["printed_total"] is None
    assert dumped["logo_url"] is None
    assert str(card_set.id) not in schema.model_dump_json()


# ---------------------------------------------------------------------------
# CardSummary
# ---------------------------------------------------------------------------


def test_card_summary_maps_fields(fictional_card):
    schema = CardSummary.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert dumped["id"] == "TEST-001"  # public_id -> id
    assert dumped["number"] == "001"  # card_number -> number
    assert dumped["type"] == "Character"  # card_type -> type
    assert dumped["rarity"] == "Rare"
    assert dumped["set"]["id"] == "test-set-1"
    assert "images" in dumped


def test_card_summary_excludes_detail_only_fields(fictional_card):
    schema = CardSummary.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert "ability_text" not in dumped
    assert "flavor_text" not in dumped
    assert "variants" not in dumped
    assert "keywords" not in dumped


def test_card_summary_never_exposes_internal_uuids(fictional_card):
    schema = CardSummary.model_validate(fictional_card)
    payload = schema.model_dump_json()

    assert str(fictional_card.id) not in payload
    assert str(fictional_card.set_id) not in payload
    assert str(fictional_card.set.id) not in payload


# ---------------------------------------------------------------------------
# CardDetail
# ---------------------------------------------------------------------------


def test_card_detail_includes_full_and_nullable_fields(fictional_card):
    schema = CardDetail.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert dumped["id"] == "TEST-001"
    assert dumped["number"] == "001"
    assert dumped["type"] == "Character"
    assert dumped["rarity"] == "Rare"
    assert dumped["chakra"] == 4
    assert dumped["power"] == 5
    assert dumped["faction"] == "Test Village"
    # Nullable fields are present with an explicit null, never omitted --
    # this is the "stable response shape" the brief asked for.
    assert dumped["ability_text"] is None
    assert dumped["flavor_text"] is None
    assert dumped["artist"] is None
    assert dumped["set"]["id"] == "test-set-1"


def test_card_detail_serializes_keywords(fictional_card):
    schema = CardDetail.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert dumped["keywords"] == [{"slug": "test-keyword", "name": "Test Keyword"}]


def test_card_detail_serializes_variants(fictional_card):
    schema = CardDetail.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert len(dumped["variants"]) == 1
    variant = dumped["variants"][0]
    assert variant["id"] == "TEST-001-holographic"  # public_id -> id
    assert variant["type"] == "holographic"  # variant_type -> type
    assert variant["finish"] == "holo"
    assert variant["rarity"] is None  # rarity_override -> rarity (unset here)
    assert variant["serial_numbered"] is False


def test_card_detail_serializes_images(fictional_card):
    schema = CardDetail.model_validate(fictional_card)
    dumped = schema.model_dump(mode="json")

    assert len(dumped["images"]) == 1
    assert dumped["images"][0] == {
        "type": "front",
        "url": "https://example.invalid/test-card.jpg",
        "width": 734,
        "height": 1024,
    }


def test_card_detail_never_exposes_internal_uuids(fictional_card):
    schema = CardDetail.model_validate(fictional_card)
    payload = schema.model_dump_json()

    assert str(fictional_card.id) not in payload
    assert str(fictional_card.set_id) not in payload
    for variant in fictional_card.variants:
        assert str(variant.id) not in payload
        assert str(variant.card_id) not in payload
    for image in fictional_card.images:
        assert str(image.id) not in payload
        assert str(image.card_id) not in payload


def test_variant_rarity_override_maps_to_rarity_field(db_session, fictional_card):
    variant_with_override = CardVariant(
        public_id="TEST-001-secret",
        card_id=fictional_card.id,
        variant_type="secret",
        rarity_override="Secret Rare",
    )
    db_session.add(variant_with_override)
    db_session.commit()

    schema = CardVariantResponse.model_validate(variant_with_override)
    dumped = schema.model_dump(mode="json")

    assert dumped["type"] == "secret"
    assert dumped["rarity"] == "Secret Rare"


# ---------------------------------------------------------------------------
# CardImageResponse
# ---------------------------------------------------------------------------


def test_image_response_excludes_source_metadata(fictional_card):
    image = fictional_card.images[0]
    # Sanity check the ORM object really does carry provenance data that
    # the public schema must exclude.
    assert image.source_name == "test-fixture-source"
    assert image.hosted_by_us is False

    from app.schemas.image import CardImageResponse

    schema = CardImageResponse.model_validate(image)
    dumped = schema.model_dump(mode="json")

    assert dumped == {
        "type": "front",
        "url": "https://example.invalid/test-card.jpg",
        "width": 734,
        "height": 1024,
    }
    assert "source_name" not in dumped
    assert "source_url" not in dumped
    assert "hosted_by_us" not in dumped
    assert str(image.id) not in schema.model_dump_json()
    assert str(image.card_id) not in schema.model_dump_json()


# ---------------------------------------------------------------------------
# KeywordResponse
# ---------------------------------------------------------------------------


def test_keyword_response_excludes_uuid(db_session):
    keyword = Keyword(slug="team-7", name="Team 7")
    db_session.add(keyword)
    db_session.commit()

    schema = KeywordResponse.model_validate(keyword)
    dumped = schema.model_dump(mode="json")

    assert dumped == {"slug": "team-7", "name": "Team 7"}
    assert str(keyword.id) not in schema.model_dump_json()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pagination_meta_accepts_valid_values():
    meta = PaginationMeta(page=1, limit=50, total=630, pages=13, has_next=True, has_previous=False)
    assert meta.model_dump() == {
        "page": 1,
        "limit": 50,
        "total": 630,
        "pages": 13,
        "has_next": True,
        "has_previous": False,
    }


@pytest.mark.parametrize(
    "field,value",
    [("page", 0), ("limit", 0), ("total", -1), ("pages", -1)],
)
def test_pagination_meta_rejects_invalid_values(field, value):
    kwargs = {
        "page": 1,
        "limit": 50,
        "total": 630,
        "pages": 13,
        "has_next": True,
        "has_previous": False,
    }
    kwargs[field] = value

    with pytest.raises(ValidationError):
        PaginationMeta(**kwargs)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_error_response_has_exact_expected_shape():
    error = ErrorResponse(
        error=ErrorDetail(code=ErrorCode.CARD_NOT_FOUND, message="Card not found.")
    )

    assert error.model_dump(mode="json") == {
        "error": {"code": "CARD_NOT_FOUND", "message": "Card not found."}
    }


# ---------------------------------------------------------------------------
# Search discriminated union
# ---------------------------------------------------------------------------


def test_search_result_card_variant_serializes(fictional_card):
    result = CardSearchResult(card=CardSummary.model_validate(fictional_card))
    dumped = result.model_dump(mode="json")

    assert dumped["type"] == "card"
    assert dumped["card"]["id"] == "TEST-001"


def test_search_result_discriminated_union_parses_each_type():
    adapter = TypeAdapter(SearchResult)

    card_payload = {
        "type": "card",
        "card": {
            "id": "TEST-001",
            "number": "001",
            "name": "Test Character Alpha",
            "subtitle": None,
            "type": "Character",
            "rarity": "Rare",
            "set": {
                "id": "test-set-1",
                "code": "TST1",
                "name": "Test Set Alpha",
                "edition": "1st Edition",
            },
            "images": [],
        },
    }
    assert isinstance(adapter.validate_python(card_payload), CardSearchResult)

    set_payload = {
        "type": "set",
        "set": {
            "id": "test-set-1",
            "code": "TST1",
            "name": "Test Set Alpha",
            "edition": "1st Edition",
        },
    }
    assert isinstance(adapter.validate_python(set_payload), SetSearchResult)

    keyword_payload = {
        "type": "keyword",
        "keyword": {"slug": "test-keyword", "name": "Test Keyword"},
    }
    assert isinstance(adapter.validate_python(keyword_payload), KeywordSearchResult)


def test_search_response_wrapper_serializes_mixed_result_types(fictional_card):
    response = SearchResponse(
        data=[
            CardSearchResult(card=CardSummary.model_validate(fictional_card)),
            SetSearchResult(set=SetSummary.model_validate(fictional_card.set)),
        ]
    )
    dumped = response.model_dump(mode="json")

    assert dumped["data"][0]["type"] == "card"
    assert dumped["data"][1]["type"] == "set"
