"""Read-only public card routes. Register future static paths before /{public_id}."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.card import CardDetail, CardSummary
from app.schemas.pagination import PaginatedCardsResponse
from app.services import card_service
from app.services.card_filters import CardFilters
from app.utils.error_docs import invalid_card_parameters_response, not_found_response
from app.utils.pagination import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE,
    build_pagination_meta,
    validate_pagination,
)

_db_dependency = Depends(get_db)  # FastAPI resolves this once per request.

router = APIRouter(prefix="/v1/cards", tags=["Cards"])


@router.get(
    "",
    response_model=PaginatedCardsResponse,
    summary="List cards",
    responses={400: invalid_card_parameters_response()},
)
def list_cards(
    page: int = Query(DEFAULT_PAGE, description="Page number, starting at 1."),
    limit: int = Query(DEFAULT_LIMIT, description="Items per page: 1 through 100."),
    name: str | None = Query(None, description="Case-insensitive partial name match."),
    set_id: str | None = Query(
        None, alias="set", description="Exact public set ID, case-insensitive."
    ),
    number: str | None = Query(None, description="Exact card number (a string)."),
    rarity: str | None = Query(None, description="Case-insensitive exact rarity."),
    card_type: str | None = Query(
        None, alias="type", description="Case-insensitive exact card type."
    ),
    keyword: str | None = Query(None, description="Case-insensitive exact keyword slug."),
    variant: str | None = Query(
        None, description="Case-insensitive exact variant type; at least one must match."
    ),
    language: str | None = Query(
        None, description="Case-insensitive exact parent set language, not variant language."
    ),
    edition: str | None = Query(None, description="Case-insensitive exact parent set edition."),
    chakra_min: int | None = Query(
        None, description="Inclusive minimum chakra, >= 0; excludes null chakra."
    ),
    chakra_max: int | None = Query(
        None, description="Inclusive maximum chakra, >= 0; excludes null chakra."
    ),
    power_min: int | None = Query(
        None, description="Inclusive minimum power, >= 0; excludes null power."
    ),
    power_max: int | None = Query(
        None, description="Inclusive maximum power, >= 0; excludes null power."
    ),
    sort: str = Query("number", description="number, name, rarity, set (name), or release_date."),
    order: str = Query("asc", description="asc or desc; null values always last."),
    db: Session = _db_dependency,
) -> PaginatedCardsResponse:
    page, limit = validate_pagination(page, limit)
    cards, total = card_service.list_cards(
        db,
        page=page,
        limit=limit,
        name=name,
        set_id=set_id,
        number=number,
        filters=CardFilters(
            rarity=rarity,
            card_type=card_type,
            keyword=keyword,
            variant=variant,
            language=language,
            edition=edition,
            chakra_min=chakra_min,
            chakra_max=chakra_max,
            power_min=power_min,
            power_max=power_max,
        ),
        sort=sort,
        order=order,
    )
    return PaginatedCardsResponse(
        data=[CardSummary.model_validate(card) for card in cards],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )


@router.get(
    "/random",
    response_model=CardDetail,
    summary="Get a random card",
    responses={404: not_found_response("CARD_NOT_FOUND", "No cards available.")},
)
def random_card(db: Session = _db_dependency) -> CardDetail:
    return CardDetail.model_validate(card_service.get_random_card(db))


# Keep static routes above this public-ID route.
@router.get(
    "/{public_id}",
    response_model=CardDetail,
    summary="Get a single card",
    responses={404: not_found_response("CARD_NOT_FOUND", "Card not found.")},
)
def get_card(public_id: str, db: Session = _db_dependency) -> CardDetail:
    return CardDetail.model_validate(card_service.get_card_by_public_id(db, public_id))
