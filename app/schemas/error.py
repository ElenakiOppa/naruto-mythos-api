"""
Public error contract.

Every error response, from every future endpoint, must use this exact
shape:

{
  "error": {
    "code": "CARD_NOT_FOUND",
    "message": "Card not found."
  }
}

`ErrorCode` is implemented as a string enum rather than a bare `str` field.
This is a deliberate trade-off, documented here since it affects backward
compatibility:

- Pro: it gives Swagger/OpenAPI an exact, enumerated list of every possible
  error code up front -- exactly the kind of documentation quality a
  RapidAPI-published developer API should have, and a bare `str` field
  would document nothing.
- Con: adding a brand-new error code later means adding a new member to
  this enum. That is an *additive*, backward-compatible schema change
  (existing values keep working; nothing is renamed or removed), so it
  does not break existing clients -- but it does mean the enum, not just
  the response shape, is part of the versioned `/v1` contract. Genuinely
  new error categories should still go through the same "no breaking
  changes without /v2" policy as any other field.

Route-level exception handling that actually raises these errors is not
implemented yet -- Phase 3 is schemas only, per the brief.
"""

from enum import Enum

from app.schemas.base import PublicSchema


class ErrorCode(str, Enum):
    """Known/expected error codes for the /v1 API.

    This list is expected to grow in later phases as route handlers are
    implemented (e.g. Phase 5+ will need to actually raise CARD_NOT_FOUND
    when a lookup misses) -- growing it is an additive change.
    """

    CARD_NOT_FOUND = "CARD_NOT_FOUND"
    SET_NOT_FOUND = "SET_NOT_FOUND"
    KEYWORD_NOT_FOUND = "KEYWORD_NOT_FOUND"
    INVALID_FILTER = "INVALID_FILTER"
    INVALID_PAGINATION = "INVALID_PAGINATION"
    INVALID_SORT = "INVALID_SORT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(PublicSchema):
    code: ErrorCode
    message: str


class ErrorResponse(PublicSchema):
    error: ErrorDetail
