"""
Top-level API router.

/health is intentionally mounted unversioned (per spec) while all catalogue
endpoints live under /v1. Future catalogue routers (the global cards list,
rarities, keywords, search) are added here in later phases.
"""

from fastapi import APIRouter

from app.api.v1.cards import router as cards_router
from app.api.v1.health import router as health_router
from app.api.v1.metadata import router as metadata_router
from app.api.v1.ready import router as ready_router
from app.api.v1.search import router as search_router
from app.api.v1.sets import router as sets_router
from app.schemas.error import ErrorResponse

api_router = APIRouter(
    responses={500: {"model": ErrorResponse, "description": "An unexpected error occurred."}}
)

# Unversioned system endpoints.
api_router.include_router(health_router)
api_router.include_router(ready_router)

# Versioned catalogue endpoints. sets_router already declares its own
# "/v1/sets" prefix (see app/api/v1/sets.py), so no additional prefix is
# added here.
api_router.include_router(sets_router)

api_router.include_router(cards_router)

api_router.include_router(metadata_router)
api_router.include_router(search_router)
