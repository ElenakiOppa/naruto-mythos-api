"""SQL queries for the public Cards API; no catalogue writes."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from app.models import Card, CardImage, CardSet, CardVariant
from app.schemas.error import ErrorCode
from app.services.card_filters import CardFilters, apply_card_filters
from app.utils.errors import APIError

SORT_FIELDS = {
    "number": Card.card_number,
    "name": Card.name,
    "rarity": Card.rarity,
    "set": CardSet.name,
    "release_date": CardSet.release_date,
}


def list_cards(
    db: Session,
    *,
    page: int,
    limit: int,
    name: str | None = None,
    set_id: str | None = None,
    number: str | None = None,
    filters: CardFilters | None = None,
    sort: str = "number",
    order: str = "asc",
) -> tuple[list[Card], int]:
    if sort not in SORT_FIELDS or order not in ("asc", "desc"):
        raise APIError(ErrorCode.INVALID_SORT, "Invalid sort field or order.", 400)
    stmt = select(Card).join(Card.set)
    if name is not None:
        # Treat LIKE metacharacters as literal user text, not wildcard syntax.
        stmt = stmt.where(Card.name.icontains(name, autoescape=True))
    if set_id is not None:
        stmt = stmt.where(func.lower(CardSet.public_id) == set_id.lower())
    if number is not None:
        stmt = stmt.where(Card.card_number == number)
    stmt = apply_card_filters(stmt, filters or CardFilters())
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    column = SORT_FIELDS[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    stmt = (
        stmt.order_by(ordering.nulls_last(), Card.public_id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .options(
            contains_eager(Card.set), selectinload(Card.images.and_(CardImage.variant_id.is_(None)))
        )
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(stmt).all()), total


def card_summary_options():
    """Shared summary loading for search; list uses its existing explicit set join."""
    return (joinedload(Card.set), selectinload(Card.images.and_(CardImage.variant_id.is_(None))))


def card_detail_statement():
    return (
        select(Card)
        .options(
            *card_summary_options(),
            selectinload(Card.keywords),
            selectinload(Card.variants).selectinload(CardVariant.images),
            selectinload(Card.variants).joinedload(CardVariant.translations),
        )
        .execution_options(populate_existing=True)
    )


def get_card_by_public_id(db: Session, public_id: str) -> Card:
    card = db.scalar(card_detail_statement().where(Card.public_id == public_id))
    if card is None:
        raise APIError(ErrorCode.CARD_NOT_FOUND, "Card not found.", 404)
    return card


def get_random_card(db: Session) -> Card:
    # ORDER BY random() is suitable for the initial catalogue. Keep it isolated
    # here so large-catalogue optimization can preserve the response contract.
    card = db.scalar(card_detail_statement().order_by(func.random()).limit(1))
    if card is None:
        raise APIError(ErrorCode.CARD_NOT_FOUND, "No cards available.", 404)
    return card
