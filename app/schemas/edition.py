"""Public Set-scoped Edition schemas."""

from pydantic import ConfigDict

from app.schemas.base import PublicSchema
from app.schemas.pagination_meta import PaginationMeta
from app.schemas.set import EditionSummary


class EditionDetail(EditionSummary):
    set_id: str
    set_name: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedEditionsResponse(PublicSchema):
    data: list[EditionDetail]
    pagination: PaginationMeta
