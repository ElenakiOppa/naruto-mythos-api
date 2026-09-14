"""Read-only catalogue metadata."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.card import CardSummary
from app.schemas.metadata import KeywordCatalogItem, RarityCatalogItem
from app.schemas.pagination import PaginatedCardsResponse
from app.services import metadata_service
from app.utils.error_docs import invalid_parameters_response, not_found_response
from app.utils.pagination import build_pagination_meta, validate_pagination

_db_dependency = Depends(get_db)  # FastAPI resolves this once per request.

router = APIRouter(prefix="/v1", tags=["Metadata"])


@router.get("/rarities", response_model=list[RarityCatalogItem], summary="List rarity counts")
def rarities(db: Session = _db_dependency):
    return metadata_service.list_rarities(db)


@router.get("/keywords", response_model=list[KeywordCatalogItem], summary="List keyword counts")
def keywords(db: Session = _db_dependency):
    return metadata_service.list_keywords(db)


@router.get(
    "/keywords/{slug}/cards",
    response_model=PaginatedCardsResponse,
    summary="List a keyword's cards",
    responses={
        400: invalid_parameters_response(),
        404: not_found_response("KEYWORD_NOT_FOUND", "Keyword not found."),
    },
)
def keyword_cards(
    slug: str,
    page: int = Query(1, description="Page number, >= 1."),
    limit: int = Query(50, description="Items per page, 1 through 100."),
    sort: str = Query("number", description="number, name, rarity, set, release_date."),
    order: str = Query("asc", description="asc or desc; nulls last."),
    db: Session = _db_dependency,
):
    page, limit = validate_pagination(page, limit)
    cards, total = metadata_service.list_keyword_cards(
        db, slug, page=page, limit=limit, sort=sort, order=order
    )
    return PaginatedCardsResponse(
        data=[CardSummary.model_validate(c) for c in cards],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )
