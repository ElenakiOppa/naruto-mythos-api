"""
Public card schemas.

`CardSummary` and `CardDetail` are deliberately different sizes:

- `CardSummary` is what `GET /v1/cards` (a paginated list, potentially many
  cards per page) returns per item. It excludes `ability_text`,
  `flavor_text`, `keywords`, and `variants` on purpose -- a card list
  response should stay lightweight, since callers who need the full detail
  can always fetch `GET /v1/cards/{id}` for one card.
- `CardDetail` is the complete representation, returned only by
  `GET /v1/cards/{id}`.

Maps:
  database `public_id`   -> public "id"
  database `card_number` -> public "number"
  database `card_type`   -> public "type"

`set_id` (the raw database foreign key) is never exposed -- the related
set is always nested as a full `SetSummary` object instead, which is more
useful to a client than a bare UUID they'd have to look up separately.
"""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema
from app.schemas.image import CardImageResponse
from app.schemas.keyword import KeywordResponse
from app.schemas.set import SetSummary
from app.schemas.variant import CardVariantResponse


class CardSummary(PublicSchema):
    id: str = Field(validation_alias="public_id", examples=["TEST-001"])
    number: str = Field(validation_alias="card_number", examples=["001"])
    name: str = Field(examples=["Test Character Alpha"])
    subtitle: str | None = Field(default=None, examples=[None])
    type: str | None = Field(default=None, validation_alias="card_type", examples=["Character"])
    rarity: str | None = Field(default=None, examples=["Rare"])
    set: SetSummary
    images: list[CardImageResponse] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
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
            }
        },
    )


class CardDetail(PublicSchema):
    id: str = Field(validation_alias="public_id", examples=["TEST-001"])
    number: str = Field(validation_alias="card_number", examples=["001"])
    name: str = Field(examples=["Test Character Alpha"])
    subtitle: str | None = Field(default=None, examples=[None])
    type: str | None = Field(default=None, validation_alias="card_type", examples=["Character"])
    rarity: str | None = Field(default=None, examples=["Rare"])

    chakra: int | None = Field(default=None, examples=[4])
    power: int | None = Field(default=None, examples=[5])
    points: int | None = Field(default=None, examples=[None])

    faction: str | None = Field(default=None, examples=["Test Village"])

    ability_text: str | None = Field(default=None, examples=[None])
    flavor_text: str | None = Field(default=None, examples=[None])
    artist: str | None = Field(default=None, examples=[None])

    set: SetSummary
    keywords: list[KeywordResponse] = Field(default_factory=list)
    variants: list[CardVariantResponse] = Field(default_factory=list)
    images: list[CardImageResponse] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "TEST-001",
                "number": "001",
                "name": "Test Character Alpha",
                "subtitle": None,
                "type": "Character",
                "rarity": "Rare",
                "chakra": 4,
                "power": 5,
                "faction": "Test Village",
                "ability_text": None,
                "flavor_text": None,
                "artist": None,
                "set": {
                    "id": "test-set-1",
                    "code": "TST1",
                    "name": "Test Set Alpha",
                    "edition": "1st Edition",
                },
                "keywords": [
                    {"slug": "test-keyword", "name": "Test Keyword"},
                ],
                "variants": [],
                "images": [],
            }
        },
    )
