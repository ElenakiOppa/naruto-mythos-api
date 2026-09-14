"""
Set (and set-scoped card) query service.

Route handlers stay thin: they parse/validate request parameters, call one
of these functions, and convert the result into a public schema. All actual
SQLAlchemy query construction -- filtering, sorting, pagination, eager
loading -- lives here.
"""

from sqlalchemy import asc, desc, func, nulls_last, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import Card, CardSet
from app.schemas.error import ErrorCode
from app.services.card_service import card_summary_options
from app.utils.errors import APIError

# Explicit allowlists -- never let a caller-supplied string reach
# SQLAlchemy's `order_by` directly. Only names present as keys here are
# acceptable; anything else is rejected with INVALID_SORT before any query
# is built.
SET_SORT_FIELDS: dict[str, InstrumentedAttribute] = {
    "name": CardSet.name,
    "release_date": CardSet.release_date,
    "code": CardSet.code,
}

CARD_SORT_FIELDS: dict[str, InstrumentedAttribute] = {
    # Lexical (string) ordering, deliberately -- card_number is a string
    # and is never cast to a number. A card numbered "10" sorts before "2"
    # under this scheme, matching how the database itself stores and
    # compares the column; introducing "natural" numeric-aware sorting is
    # explicitly out of scope for this phase.
    "number": Card.card_number,
    "name": Card.name,
    "rarity": Card.rarity,
}

VALID_ORDERS = ("asc", "desc")


def _validate_sort(sort: str, order: str, allowed_fields: dict[str, InstrumentedAttribute]):
    if sort not in allowed_fields:
        raise APIError(ErrorCode.INVALID_SORT, "Invalid sort field.", 400)
    if order not in VALID_ORDERS:
        raise APIError(ErrorCode.INVALID_SORT, "Invalid sort order.", 400)
    return allowed_fields[sort]


def list_sets(
    db: Session,
    *,
    page: int,
    limit: int,
    language: str | None = None,
    edition: str | None = None,
    code: str | None = None,
    sort: str = "release_date",
    order: str = "desc",
) -> tuple[list[CardSet], int]:
    sort_column = _validate_sort(sort, order, SET_SORT_FIELDS)

    stmt = select(CardSet)

    # Case-insensitive equality filters, applied in SQL via lower() on both
    # sides -- never fetched into Python and filtered there.
    if language:
        stmt = stmt.where(func.lower(CardSet.language) == language.lower())
    if edition:
        stmt = stmt.where(func.lower(CardSet.edition) == edition.lower())
    if code:
        stmt = stmt.where(func.lower(CardSet.code) == code.lower())

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    order_fn = asc if order == "asc" else desc
    # release_date (and code) may be null; nulls_last keeps ordering
    # deterministic regardless of asc/desc, rather than nulls unpredictably
    # sorting first in one direction and last in the other.
    stmt = stmt.order_by(nulls_last(order_fn(sort_column)), CardSet.public_id.asc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    results = db.execute(stmt).scalars().all()
    return list(results), total


def get_set_by_public_id(db: Session, public_id: str) -> CardSet:
    """Look up a set by its stable public_id -- never by internal UUID."""
    card_set = db.execute(
        select(CardSet).where(CardSet.public_id == public_id)
    ).scalar_one_or_none()

    if card_set is None:
        raise APIError(ErrorCode.SET_NOT_FOUND, "Set not found.", 404)

    return card_set


def list_cards_for_set(
    db: Session,
    *,
    public_id: str,
    page: int,
    limit: int,
    sort: str = "number",
    order: str = "asc",
) -> tuple[list[Card], int]:
    # Confirms the set exists first, giving a clean 404 SET_NOT_FOUND for a
    # missing set rather than a misleadingly "successful" empty card list.
    card_set = get_set_by_public_id(db, public_id)

    sort_column = _validate_sort(sort, order, CARD_SORT_FIELDS)

    base_stmt = select(Card).where(Card.set_id == card_set.id)

    total = db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one()

    order_fn = asc if order == "asc" else desc
    stmt = (
        base_stmt.order_by(nulls_last(order_fn(sort_column)), Card.public_id.asc())
        # CardSummary needs `set` and `images`, never `variants` or
        # `keywords` (those aren't part of that schema). `set` is a to-one
        # relationship -- joinedload (single JOIN) is both correct and
        # efficient here, and safe to combine with LIMIT/OFFSET since a
        # to-one join never duplicates the parent (Card) rows. `images` is
        # a to-many collection -- selectinload (separate `WHERE card_id IN
        # (...)` query) is used instead specifically because joinedload on
        # a *to-many* relationship combined with LIMIT/OFFSET on the parent
        # would silently corrupt pagination (the JOIN duplicates parent
        # rows before LIMIT is applied).
        .options(*card_summary_options())
        .execution_options(populate_existing=True)
        .offset((page - 1) * limit)
        .limit(limit)
    )

    results = db.execute(stmt).unique().scalars().all()
    return list(results), total
