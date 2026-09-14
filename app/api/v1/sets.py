"""
Public Sets API.

GET /v1/sets
GET /v1/sets/{public_id}
GET /v1/sets/{public_id}/cards

Route handlers are intentionally thin: parse/validate request parameters,
delegate to app.services.set_service for the actual query, then convert the
result into a public schema. No SQLAlchemy query construction happens here.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.card import CardSummary
from app.schemas.pagination import PaginatedCardsResponse, PaginatedSetsResponse
from app.schemas.set import SetDetail
from app.services import set_service
from app.utils.error_docs import invalid_parameters_response, not_found_response
from app.utils.pagination import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE,
    MAX_LIMIT,
    build_pagination_meta,
    validate_pagination,
)

_db_dependency = Depends(get_db)  # FastAPI resolves this once per request.

router = APIRouter(prefix="/v1/sets", tags=["Sets"])

# Route-ordering note (no action needed, documented for future maintainers):
# "" (list), "/{public_id}", and "/{public_id}/cards" cannot shadow one
# another -- they have structurally different path shapes (zero, one, and
# two path segments after the router's own /v1/sets prefix respectively),
# so there is no ambiguity for FastAPI/Starlette to resolve regardless of
# declaration order. This would only become a concern if a future phase
# adds a *static* segment at the same depth as {public_id} (e.g. a
# hypothetical "/v1/sets/random"), which this phase deliberately does not.


@router.get(
    "",
    response_model=PaginatedSetsResponse,
    summary="List sets",
    description="Paginated list of sets. Supports filtering by language, "
    "edition, and code, and sorting by name, release_date, or code.",
    responses={
        400: invalid_parameters_response(),
    },
)
def list_sets(
    page: int = Query(DEFAULT_PAGE, description="Page number, starting at 1."),
    limit: int = Query(DEFAULT_LIMIT, description=f"Items per page, up to {MAX_LIMIT}."),
    language: str | None = Query(
        None, description="Filter by language code (e.g. EN). Case-insensitive."
    ),
    edition: str | None = Query(None, description="Filter by edition. Case-insensitive."),
    code: str | None = Query(None, description="Filter by set code. Case-insensitive."),
    sort: str = Query("release_date", description="Sort field: name, release_date, or code."),
    order: str = Query("desc", description="Sort order: asc or desc."),
    db: Session = _db_dependency,
) -> PaginatedSetsResponse:
    page, limit = validate_pagination(page, limit)

    sets, total = set_service.list_sets(
        db,
        page=page,
        limit=limit,
        language=language,
        edition=edition,
        code=code,
        sort=sort,
        order=order,
    )

    return PaginatedSetsResponse(
        data=[SetDetail.model_validate(s) for s in sets],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )


@router.get(
    "/{public_id}",
    response_model=SetDetail,
    summary="Get a single set",
    description="Look up a set by its public ID.",
    responses={
        404: not_found_response("SET_NOT_FOUND", "Set not found."),
    },
)
def get_set(public_id: str, db: Session = _db_dependency) -> SetDetail:
    card_set = set_service.get_set_by_public_id(db, public_id)
    return SetDetail.model_validate(card_set)


@router.get(
    "/{public_id}/cards",
    response_model=PaginatedCardsResponse,
    summary="List a set's cards",
    description="Paginated list of cards belonging to one set. Supports "
    "sorting by number, name, or rarity. card_number is sorted lexically "
    "(as a string), never as a number.",
    responses={
        400: invalid_parameters_response(),
        404: not_found_response("SET_NOT_FOUND", "Set not found."),
    },
)
def list_set_cards(
    public_id: str,
    page: int = Query(DEFAULT_PAGE, description="Page number, starting at 1."),
    limit: int = Query(DEFAULT_LIMIT, description=f"Items per page, up to {MAX_LIMIT}."),
    sort: str = Query("number", description="Sort field: number, name, or rarity."),
    order: str = Query("asc", description="Sort order: asc or desc."),
    db: Session = _db_dependency,
) -> PaginatedCardsResponse:
    page, limit = validate_pagination(page, limit)

    cards, total = set_service.list_cards_for_set(
        db, public_id=public_id, page=page, limit=limit, sort=sort, order=order
    )

    return PaginatedCardsResponse(
        data=[CardSummary.model_validate(c) for c in cards],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )
