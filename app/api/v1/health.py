"""
GET /health -- pure application liveness endpoint.

This intentionally does NOT touch the database. A liveness check answers
"is the process up and able to respond at all", which should never depend
on the availability of a downstream dependency like PostgreSQL -- that's
what /ready is for. Coupling /health to the database was a Phase 1 design
mistake (discovered when an unreachable Postgres made health checks take
up to several minutes on Windows); this fixes it by removing the DB call
entirely rather than just tuning its timeout.
"""

from fastapi import APIRouter

from app.config import API_VERSION
from app.schemas.health import HealthResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns basic service liveness. Performs no database or "
    "other external dependency checks, so it always responds immediately. "
    "Use /ready to check infrastructure readiness instead.",
)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", version=API_VERSION)
