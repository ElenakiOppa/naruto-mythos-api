"""
Public metadata/catalogue schemas for the GET /v1/rarities and
GET /v1/keywords endpoints.

These are intentionally separate from `app.schemas.keyword.KeywordResponse`
(used when a keyword is nested inside `CardDetail`) rather than that schema
with an extra optional field bolted on: a keyword nested inside one card has
no meaningful "how many cards use this keyword catalogue-wide" figure to
report about itself, so the two use cases genuinely have different shapes,
not just different levels of completeness of the same shape.

No real rarity or keyword values are hard-coded here -- these are schemas
only; the actual set of rarities/keywords will always be whatever exists in
the database (per the brief: "derive available rarities from the database
rather than rely on a hard-coded Naruto-specific list").
"""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema


class RarityCatalogItem(PublicSchema):
    name: str = Field(examples=["Rare"])
    slug: str = Field(examples=["rare"])
    card_count: int = Field(ge=0, examples=[42])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={"example": {"name": "Rare", "slug": "rare", "card_count": 42}},
    )


class KeywordCatalogItem(PublicSchema):
    slug: str = Field(examples=["test-keyword"])
    name: str = Field(examples=["Test Keyword"])
    card_count: int = Field(ge=0, examples=[10])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {"slug": "test-keyword", "name": "Test Keyword", "card_count": 10}
        },
    )
