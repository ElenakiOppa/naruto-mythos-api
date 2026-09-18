import hmac
import ipaddress
import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import API_VERSION, get_settings
from app.schemas.error import ErrorCode, ErrorDetail, ErrorResponse
from app.utils.errors import APIError

settings = get_settings()

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Naruto Mythos TCG Developer API",
    description="A developer-friendly REST API for querying Naruto Mythos TCG catalogue data.",
    version=API_VERSION,
    debug=False,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    swagger_ui_oauth2_redirect_url=None,
)

# CORS is intentionally configuration-driven: no origins are allowed by
# default, and "*" is never combined with allow_credentials=True.
cors_origins = settings.cors_origins_list
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
else:
    logger.info("CORS_ORIGINS not configured; no browser origins are allowed by default.")

app.include_router(api_router)


@app.exception_handler(APIError)
async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
    """Converts any raised APIError into the public ErrorResponse shape.

    This is the single place that maps a service/route-level business error
    (SET_NOT_FOUND, INVALID_SORT, INVALID_PAGINATION, ...) to an HTTP
    response -- no route handler builds an error dict by hand.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=ErrorDetail(code=exc.code, message=exc.message)).model_dump(
            mode="json"
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all safety net for anything not raised as an APIError.

    Logs the exception type and frame locations (without exception text) and
    returns a generic INTERNAL_ERROR -- no stack trace, SQL, or exception
    text is ever exposed to the client. FastAPI's own handlers for
    HTTPException and RequestValidationError are more specific and are
    resolved before this catch-all, so this does not affect FastAPI's
    default 422 validation responses for malformed query parameter types.
    """
    # Exception text/args and source lines can contain credentials or SQL values.
    frames = [
        f"{Path(f.filename).name}:{f.lineno}:{f.name}"
        for f in traceback.extract_tb(exc.__traceback__)
    ]
    logger.error("Unhandled exception type=%s frames=%s", type(exc).__name__, frames)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR, message="An unexpected error occurred."
            )
        ).model_dump(mode="json"),
    )


def _get_client_ip(request: Request) -> str | None:
    """Return the client IP as resolved by Uvicorn's --proxy-headers handling.

    Uvicorn only trusts X-Forwarded-For from its configured trusted proxy
    boundary, so request.client.host here is not an arbitrary spoofable
    header value from an untrusted direct client.
    """
    client = request.client
    return client.host if client else None


def _client_ip_is_allowlisted(request: Request) -> bool:
    allowlist = settings.tester_ip_allowlist_set
    if not allowlist:
        return False

    host = _get_client_ip(request)
    if not host:
        return False

    try:
        client_ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return client_ip in allowlist


@app.middleware("http")
async def rapidapi_proxy_secret_guard(request: Request, call_next):
    """Require the configured RapidAPI proxy secret only for /v1 traffic.

    A request may also be allowed without the header when its resolved
    client IP is present in the temporary TESTER_IP_ALLOWLIST. This is
    checked only after the secret check fails, so behavior when
    TESTER_IP_ALLOWLIST is unset/empty is identical to before.
    """
    if not settings.rapidapi_proxy_secret:
        return await call_next(request)

    if not request.url.path.startswith("/v1"):
        return await call_next(request)

    supplied = request.headers.get("X-RapidAPI-Proxy-Secret")
    if (
        supplied is not None
        and settings.rapidapi_proxy_secret is not None
        and hmac.compare_digest(supplied, settings.rapidapi_proxy_secret)
    ):
        return await call_next(request)

    if _client_ip_is_allowlisted(request):
        return await call_next(request)

    return JSONResponse(
        status_code=403,
        content=ErrorResponse(
            error=ErrorDetail(code=ErrorCode.FORBIDDEN, message="Forbidden.")
        ).model_dump(mode="json"),
    )


@app.middleware("http")
async def sanitize_unexpected_failures(request: Request, call_next):
    # Handle before Starlette's outer ServerErrorMiddleware can re-raise the
    # original exception to the ASGI server's unredacted exception logger.
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 -- safe execution boundary
        return await handle_unexpected_error(request, exc)
