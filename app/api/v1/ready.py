"""
GET /ready -- infrastructure readiness endpoint.

Unlike /health, this endpoint does check PostgreSQL connectivity, because
its whole purpose is to answer "can this instance actually serve real
traffic right now" (e.g. for a load balancer or orchestrator deciding
whether to route requests to this instance). A failure here returns 503
rather than 200, and never leaks connection details, credentials, or raw
exception text -- only a generic status.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
from app.schemas.ready import ReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={
        200: {"description": "The service can reach its database and is ready for traffic."},
        503: {"description": "The service cannot currently reach its database."},
    },
    summary="Readiness check",
    description="Checks PostgreSQL connectivity. Returns 200 when ready, "
    "503 when not. Never exposes database host, credentials, or exception "
    "details in the response.",
)
def get_ready() -> JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - deliberately broad; never leak details
        logger.warning("Readiness check failed: database is unreachable")
        return JSONResponse(
            status_code=503,
            content=ReadyResponse(status="not_ready").model_dump(),
        )

    return JSONResponse(
        status_code=200,
        content=ReadyResponse(status="ready").model_dump(),
    )
