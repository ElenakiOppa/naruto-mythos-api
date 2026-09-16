"""
Public card variant schema.

Maps:
  database `public_id`       -> public "id"
  database `variant_type`    -> public "type"
  database `rarity_override` -> public "rarity"

`type` is a plain string, not a fixed enum -- matching the database's own
choice (CardVariant.variant_type is free text, not a Postgres ENUM) to
guarantee new variant types can appear in API responses without requiring
a schema change or a client update. `card_id` is never exposed -- a
variant is always accessed already nested under its parent card, so the
link is structural (the JSON nesting itself), not a field a client needs.
"""

from pydantic import ConfigDict, Field, model_validator

from app.schemas.base import PublicSchema
from app.schemas.image import CardImageResponse


class CardVariantResponse(PublicSchema):
    id: str = Field(validation_alias="public_id", examples=["TEST-001-holographic"])
    type: str = Field(validation_alias="variant_type", examples=["holographic"])
    finish: str | None = Field(default=None, examples=["holo"])
    rarity: str | None = Field(default=None, validation_alias="rarity_override", examples=[None])
    collector_number: str | None = Field(default=None, examples=[None])
    language: str = Field(examples=["EN"])
    edition: str | None = Field(default=None, examples=[None])
    source_variant: str | None = Field(
        default=None, description="Publisher-supplied variant label; null when unspecified."
    )
    card_version: str | None = Field(default=None, description="Publisher-supplied card version.")
    stamp: str | None = Field(default=None, description="Publisher-supplied stamp label.")
    serial_numbered: bool = Field(examples=[False])
    serial_total: int | None = Field(default=None, examples=[None])
    images: list[CardImageResponse] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def localized_image_references(cls, value):
        """Prefer the actual localized observation, without modifying database objects."""
        if isinstance(value, dict) or not hasattr(value, "translations"):
            return value
        localized = {
            f"front-{translation.language.lower()}": translation.image_url
            for translation in value.translations
        }
        if not localized:
            return value
        images = []
        seen = set()
        for image in value.images:
            response = CardImageResponse.model_validate(image)
            if response.type in localized:
                if response.type in seen:
                    continue
                seen.add(response.type)
                url = localized[response.type]
                if not url:
                    continue  # An explicitly missing localized reference is not an English fallback.
                if url != response.url:
                    response = response.model_copy(
                        update={"url": url, "width": None, "height": None}
                    )
            images.append(response)
        for image_type, url in sorted(localized.items()):
            if image_type not in seen and url:
                images.append(CardImageResponse(type=image_type, url=url))
        result = {}
        for name, field in cls.model_fields.items():
            attribute = field.validation_alias or name
            if name != "images" and hasattr(value, attribute):
                result[name] = getattr(value, attribute)
        result["images"] = images
        return result

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "TEST-001-holographic",
                "type": "holographic",
                "finish": "holo",
                "rarity": None,
                "collector_number": None,
                "language": "EN",
                "edition": None,
                "serial_numbered": False,
                "serial_total": None,
                "images": [],
            }
        },
    )
