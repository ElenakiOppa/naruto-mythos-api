"""
Reusable API error handling.

Route/service code raises `APIError` for any expected business-rule error
(not found, invalid sort, invalid pagination, ...) instead of manually
constructing an error response dict inline. A single exception handler,
registered in `app.main`, converts every `APIError` into the public
`ErrorResponse` contract -- so every current and future endpoint produces
the exact same error shape, never a bespoke one per route.
"""

from app.schemas.error import ErrorCode


class APIError(Exception):
    def __init__(self, code: ErrorCode, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
