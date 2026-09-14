"""
Pagination schemas.

`PaginationMeta` is the single reusable pagination metadata shape every
paginated endpoint must use -- never a bespoke shape per endpoint.

`PaginatedCardsResponse` and `PaginatedSetsResponse` compose it with the
appropriate item schema for each list endpoint.
"""

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema
from app.schemas.card import CardSummary
from app.schemas.set import SetDetail


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


class PaginatedCardsResponse(PublicSchema):
    data: list[CardSummary]
    pagination: PaginationMeta

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "data": [],
                "pagination": {
                    "page": 1,
                    "limit": 50,
                    "total": 0,
                    "pages": 0,
                    "has_next": False,
                    "has_previous": False,
                },
            }
        },
    )


class PaginatedSetsResponse(PublicSchema):
    """Paginated GET /v1/sets response.

    Uses `SetDetail` (the full representation), not a further-trimmed-down
    summary, as the list item shape. Decision, documented per the brief:
    unlike cards -- which can number in the thousands and are paginated
    specifically to keep list responses lightweight -- the number of sets
    in a TCG catalogue is small (tens, not thousands), so there is no
    meaningful payload-size concern with returning full detail per set even
    in a list response. Giving developers the complete set record (release
    date, printed totals, etc.) directly from the list endpoint avoids an
    extra round trip to `GET /v1/sets/{id}` for data they'll almost always
    want anyway when browsing sets.
    """

    data: list[SetDetail]
    pagination: PaginationMeta

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "data": [],
                "pagination": {
                    "page": 1,
                    "limit": 50,
                    "total": 0,
                    "pages": 0,
                    "has_next": False,
                    "has_previous": False,
                },
            }
        },
    )
