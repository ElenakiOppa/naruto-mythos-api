"""Public Printing API for persisted collectible identities."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.printing import PaginatedPrintingsResponse, PrintingResponse
from app.services import printing_service
from app.utils.pagination import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE,
    build_pagination_meta,
    validate_pagination,
)

router = APIRouter(prefix="/v1/printings", tags=["Printings"])


@router.get(
    "",
    response_model=PaginatedPrintingsResponse,
    summary="List persisted Printings",
    description="Returns every persisted collectible Printing, including source-only Printings not included in a verified collector reference. Card is the canonical identity; Printing is the collectible identity.",
)
def list_printings(
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(DEFAULT_PAGE, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
    set_id: str | None = Query(None, alias="set", description="Set public ID."),
    edition_id: str | None = Query(None, alias="edition", description="Edition public ID."),
    rarity: str | None = Query(None, description="Normalized rarity, case-insensitive."),
    treatment: str | None = Query(
        None, description="Normalized Printing treatment, case-insensitive."
    ),
    collector_class: str | None = Query(None, description="Normalized collector class."),
    card_id: str | None = Query(None, alias="card", description="Canonical Card public ID."),
    origin: str | None = Query(
        None,
        description="UPSTREAM, UPSTREAM_AND_CURATED, or CURATED_REFERENCE.",
    ),
) -> PaginatedPrintingsResponse:
    page, limit = validate_pagination(page, limit)
    printings, total = printing_service.list_printings(
        db,
        page=page,
        limit=limit,
        set_id=set_id,
        edition_id=edition_id,
        rarity=rarity,
        treatment=treatment,
        collector_class=collector_class,
        card_id=card_id,
        origin=origin,
    )
    return PaginatedPrintingsResponse(
        data=[
            PrintingResponse.model_validate(printing_service.to_printing_data(item))
            for item in printings
        ],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )


@router.get(
    "/{printing_id}",
    response_model=PrintingResponse,
    summary="Get a Printing",
    description="Returns one persisted collectible Printing and derives its origin from upstream and curated-reference relationships.",
)
def get_printing(printing_id: str, db: Annotated[Session, Depends(get_db)]) -> PrintingResponse:
    printing = printing_service.get_printing(db, printing_id)
    return PrintingResponse.model_validate(printing_service.to_printing_data(printing))
