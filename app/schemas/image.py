"""
Public image schema.

Deliberately much narrower than the `card_images` database table: only the
fields a third-party developer actually needs to display or link to an
image are exposed. Provenance/storage-internal fields (`hosted_by_us`,
`source_name`, `source_url`) and identifiers (the image's own UUID,
`card_id`, `variant_id`) are internal infrastructure details, not part of
the public contract, and are never exposed here even though they exist in
the database.
"""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema


class CardImageResponse(PublicSchema):
    # Maps database `image_type` -> public "type". The field name IS the
    # public JSON key; `validation_alias` only tells from_attributes which
    # ORM attribute to read the value from.
    type: str = Field(validation_alias="image_type", examples=["front"])
    url: str = Field(examples=["https://example.invalid/test-card.jpg"])
    width: int | None = Field(default=None, examples=[734])
    height: int | None = Field(default=None, examples=[1024])

    # Explicit rather than relying on config inheriting/merging from
    # PublicSchema -- kept fully self-contained and unambiguous.
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "type": "front",
                "url": "https://example.invalid/test-card.jpg",
                "width": 734,
                "height": 1024,
            }
        },
    )
