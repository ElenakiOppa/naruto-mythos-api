"""Public collectible Printing schemas and paginated response."""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema
from app.schemas.image import CardImageResponse
from app.schemas.pagination_meta import PaginationMeta


class PrintingResponse(PublicSchema):
    id: str = Field(validation_alias="public_id")
    card_id: str
    card_name: str
    card_type: str | None = None
    set_id: str
    set_name: str
    edition_id: str | None = None
    edition_name: str | None = None
    collector_number: str | None = None
    printed_number: str
    rarity: str | None = None
    collector_class: str | None = None
    treatment: str | None = None
    finish: str | None = None
    language: str
    serial_numbered: bool
    serial_total: int | None = None
    origin: str = Field(pattern="^(UPSTREAM|UPSTREAM_AND_CURATED|CURATED_REFERENCE)$")
    source_rarity: str | None = None
    source_variant: str | None = None
    collector_reference_number: str | None = None
    collector_reference_card_name: str | None = None
    collector_reference_rarity: str | None = None
    collector_reference_variant: str | None = None
    images: list[CardImageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedPrintingsResponse(PublicSchema):
    data: list[PrintingResponse]
    pagination: PaginationMeta
