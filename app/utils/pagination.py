"""
Shared pagination helpers used by every paginated route.

Centralizing the default/max values and the metadata-calculation logic here
means every future paginated endpoint (the global cards list, search, ...)
gets identical behavior, not a subtly different reimplementation per route.
"""

from app.schemas.error import ErrorCode
from app.schemas.pagination import PaginationMeta
from app.utils.errors import APIError

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def validate_pagination(page: int, limit: int) -> tuple[int, int]:
    """Validate page/limit against the public pagination contract.

    Raises APIError(INVALID_PAGINATION, ..., 400) for any in-range-type but
    out-of-range-value input. Malformed *types* (e.g. `page=abc`) never
    reach this function -- FastAPI/Pydantic's own query-parameter parsing
    catches those earlier and returns its default 422 response, which is
    acceptable per the project's error-contract policy (only explicit
    business-rule violations need to use the public ErrorResponse shape).
    """
    if page < 1:
        raise APIError(ErrorCode.INVALID_PAGINATION, "page must be >= 1.", 400)
    if limit < 1:
        raise APIError(ErrorCode.INVALID_PAGINATION, "limit must be >= 1.", 400)
    if limit > MAX_LIMIT:
        raise APIError(ErrorCode.INVALID_PAGINATION, f"limit must be <= {MAX_LIMIT}.", 400)
    return page, limit


def build_pagination_meta(*, page: int, limit: int, total: int) -> PaginationMeta:
    """Compute the PaginationMeta for a page of `total` items.

    `has_previous` reflects whether a previous page *number* exists
    (page > 1), not whether that previous page happens to contain data --
    this matches ordinary REST pagination semantics and stays correct even
    when the requested page is beyond the last page with results.
    """
    pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginationMeta(
        page=page,
        limit=limit,
        total=total,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1,
    )
