"""
Public set schemas.

Two representations, matching the list/detail split used for cards:

- `SetSummary`: compact, used when a set is nested inside a card
  (CardSummary.set / CardDetail.set). Deliberately excludes fields a
  client doesn't need just to identify/display which set a card belongs to.
- `SetDetail`: the full representation, used by the
  `GET /v1/sets/{id}` endpoint and the paginated sets list (see
  app/schemas/pagination.py for why the *list* endpoint also uses the full
  detail shape rather than a further-trimmed-down summary).
"""

from datetime import date

from pydantic import ConfigDict, Field

from app.schemas.base import PublicSchema


class SetSummary(PublicSchema):
    id: str = Field(validation_alias="public_id", examples=["test-set-1"])
    code: str | None = Field(default=None, examples=["TST1"])
    name: str = Field(examples=["Test Set Alpha"])
    edition: str | None = Field(default=None, examples=["1st Edition"])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "test-set-1",
                "code": "TST1",
                "name": "Test Set Alpha",
                "edition": "1st Edition",
            }
        },
    )


class SetDetail(PublicSchema):
    id: str = Field(validation_alias="public_id", examples=["test-set-1"])
    code: str | None = Field(default=None, examples=["TST1"])
    name: str = Field(examples=["Test Set Alpha"])
    edition: str | None = Field(default=None, examples=["1st Edition"])
    language: str = Field(examples=["EN"])
    release_date: date | None = Field(default=None, examples=["2026-01-01"])
    printed_total: int | None = Field(default=None, examples=[100])
    total_with_variants: int | None = Field(default=None, examples=[150])
    logo_url: str | None = Field(default=None, examples=[None])
    symbol_url: str | None = Field(default=None, examples=[None])

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "test-set-1",
                "code": "TST1",
                "name": "Test Set Alpha",
                "edition": "1st Edition",
                "language": "EN",
                "release_date": "2026-01-01",
                "printed_total": 100,
                "total_with_variants": 150,
                "logo_url": None,
                "symbol_url": None,
            }
        },
    )
