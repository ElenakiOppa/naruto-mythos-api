"""
Public search result schemas for the GET /v1/search endpoint.

A search can match different kinds of catalogue entities (cards, sets,
keywords), and the response must let a developer tell them apart
unambiguously -- never an untyped, ambiguous mixed object. This uses a
Pydantic v2 discriminated union on a literal "type" field:

{"type": "card", "card": {...}}
{"type": "set", "set": {...}}
{"type": "keyword", "keyword": {...}}

Each result wraps a *compact* representation of the matched entity
(CardSummary / SetSummary / KeywordResponse), not the full detail shape --
consistent with cards' own list/detail split, since search results are
themselves a list.

The search endpoint returns this bounded, discriminated collection.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema
from app.schemas.card import CardSummary
from app.schemas.keyword import KeywordResponse
from app.schemas.set import SetSummary


class CardSearchResult(PublicSchema):
    type: Literal["card"] = "card"
    card: CardSummary

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SetSearchResult(PublicSchema):
    type: Literal["set"] = "set"
    set: SetSummary

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class KeywordSearchResult(PublicSchema):
    type: Literal["keyword"] = "keyword"
    keyword: KeywordResponse

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


SearchResult = Annotated[
    CardSearchResult | SetSearchResult | KeywordSearchResult,
    Field(discriminator="type"),
]


class SearchResponse(PublicSchema):
    """Bounded mixed results returned by GET /v1/search."""

    data: list[SearchResult]

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "data": [
                    {
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
                    },
                    {
                        "type": "set",
                        "set": {
                            "id": "test-set-1",
                            "code": "TST1",
                            "name": "Test Set Alpha",
                            "edition": "1st Edition",
                        },
                    },
                    {
                        "type": "keyword",
                        "keyword": {"slug": "test-keyword", "name": "Test Keyword"},
                    },
                ]
            }
        },
    )
