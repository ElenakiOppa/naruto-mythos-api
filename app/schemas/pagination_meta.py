"""Shared pagination metadata model."""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema


class PaginationMeta(PublicSchema):
    page: int = Field(ge=1, examples=[1])
    limit: int = Field(ge=1, examples=[50])
    total: int = Field(ge=0, examples=[630])
    pages: int = Field(ge=0, examples=[13])
    has_next: bool = Field(examples=[True])
    has_previous: bool = Field(examples=[False])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "page": 1,
                "limit": 50,
                "total": 630,
                "pages": 13,
                "has_next": True,
                "has_previous": False,
            }
        },
    )
