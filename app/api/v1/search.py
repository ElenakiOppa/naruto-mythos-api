"""Bounded read-only discovery across cards, sets, and keywords."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.error import ErrorResponse
from app.schemas.search import SearchResponse
from app.services import search_service

_db_dependency = Depends(get_db)  # FastAPI resolves this once per request.

router = APIRouter(prefix="/v1", tags=["Search"])
search_error: dict = {
    "model": ErrorResponse,
    "description": "Invalid query or search limit.",
    "content": {},
}
search_error["content"]["application/json"] = {
    "examples": {
        "query": {
            "value": {
                "error": {
                    "code": "INVALID_FILTER",
                    "message": "Search query must contain at least 2 characters.",
                }
            }
        },
        "limit": {
            "value": {
                "error": {
                    "code": "INVALID_PAGINATION",
                    "message": "Search limit must be between 1 and 50.",
                }
            }
        },
    }
}


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search catalogue",
    responses={400: search_error},
)
def search(
    q: str = Query(..., description="Literal case-insensitive substring; trimmed length >= 2."),
    limit: int = Query(20, description="Final combined result limit, 1 through 50; default 20."),
    db: Session = _db_dependency,
):
    return SearchResponse(data=search_service.search(db, q, limit))
