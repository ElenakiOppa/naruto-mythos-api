"""
Public keyword schema, as nested inside CardDetail.

Never exposes the keyword's internal UUID. See app/schemas/metadata.py for
the separate, richer representation used by the GET /v1/keywords
catalogue endpoint (which additionally reports a card_count) -- that is a
deliberately different schema, not this one with an extra field bolted on,
since a keyword nested inside a card has no meaningful "how many cards use
this keyword" figure to report about itself.
"""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema


class KeywordResponse(PublicSchema):
    slug: str = Field(examples=["test-keyword"])
    name: str = Field(examples=["Test Keyword"])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "slug": "test-keyword",
                "name": "Test Keyword",
            }
        },
    )
