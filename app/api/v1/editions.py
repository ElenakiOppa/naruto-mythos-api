"""Set-scoped public Edition and verified collector catalogue endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.edition import EditionDetail, PaginatedEditionsResponse
from app.schemas.error import ErrorCode
from app.schemas.printing import PaginatedPrintingsResponse, PrintingResponse
from app.services import printing_service
from app.utils.error_docs import invalid_parameters_response, not_found_response
from app.utils.errors import APIError
from app.utils.pagination import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE,
    build_pagination_meta,
    validate_pagination,
)

router = APIRouter(prefix="/v1", tags=["Editions", "Collector Catalogue"])


def _edition_detail(db: Session, edition) -> EditionDetail:
    return EditionDetail.model_validate(
        {
            "public_id": edition.public_id,
            "set_id": edition.set.public_id,
            "set_name": edition.set.name,
            "name": edition.name,
            **printing_service.edition_counts(db, edition),
        }
    )


@router.get(
    "/sets/{set_id}/editions",
    response_model=PaginatedEditionsResponse,
    summary="List a Set's Editions",
    description="Editions are scoped to exactly one Set. Edition counts distinguish unique canonical Cards from collectible Printings.",
    responses={404: not_found_response("SET_NOT_FOUND", "Set not found.")},
)
def list_set_editions(
    set_id: str,
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(DEFAULT_PAGE, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
) -> PaginatedEditionsResponse:
    page, limit = validate_pagination(page, limit)
    editions, total = printing_service.list_editions_for_set(db, set_id, page=page, limit=limit)
    return PaginatedEditionsResponse(
        data=[_edition_detail(db, edition) for edition in editions],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )


@router.get(
    "/editions/{edition_id}",
    response_model=EditionDetail,
    summary="Get an Edition",
    description="An Edition is a Set-specific release scope. Collector status is VERIFIED only when a curated checklist is attached.",
    responses={404: not_found_response("EDITION_NOT_FOUND", "Edition not found.")},
)
def get_edition(edition_id: str, db: Annotated[Session, Depends(get_db)]) -> EditionDetail:
    return _edition_detail(db, printing_service.get_edition(db, edition_id))


@router.get(
    "/editions/{edition_id}/printings",
    response_model=PaginatedPrintingsResponse,
    summary="List an Edition's verified collector catalogue",
    description="Returns curated collector-reference identities when available. This intentionally differs from GET /v1/printings, which returns every persisted Printing including source-only rows.",
    responses={
        404: not_found_response("EDITION_NOT_FOUND", "Edition not found."),
        400: invalid_parameters_response(),
    },
)
def edition_printings(
    edition_id: str,
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(DEFAULT_PAGE, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
) -> PaginatedPrintingsResponse:
    page, limit = validate_pagination(page, limit)
    edition = printing_service.get_edition(db, edition_id)
    if not printing_service.edition_has_collector_reference(db, edition):
        raise APIError(
            ErrorCode.COLLECTOR_REFERENCE_NOT_FOUND,
            "No verified collector reference exists for this Edition.",
            404,
        )
    rows, total = printing_service.edition_printings(
        db, edition, collector_view=True, page=page, limit=limit
    )
    return PaginatedPrintingsResponse(
        data=[
            PrintingResponse.model_validate(
                printing_service.to_printing_data(printing, reference=reference)
            )
            for printing, reference in rows
        ],
        pagination=build_pagination_meta(page=page, limit=limit, total=total),
    )
