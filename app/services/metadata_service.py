"""SQL-aggregated metadata and keyword-scoped cards."""

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import Card, Keyword
from app.models.keyword import card_keywords
from app.schemas.error import ErrorCode
from app.schemas.metadata import KeywordCatalogItem, RarityCatalogItem
from app.services.card_filters import CardFilters
from app.services.card_service import list_cards
from app.utils.errors import APIError
from app.utils.slugs import rarity_slug


def list_rarities(db: Session) -> list[RarityCatalogItem]:
    count = func.count(Card.id)
    rows = db.execute(
        select(Card.rarity, count)
        .where(Card.rarity.is_not(None))
        .group_by(Card.rarity)
        .order_by(count.desc(), Card.rarity.asc())
    )
    return [RarityCatalogItem(name=name, slug=rarity_slug(name), card_count=n) for name, n in rows]


def list_keywords(db: Session) -> list[KeywordCatalogItem]:
    count = func.count(distinct(card_keywords.c.card_id))
    rows = db.execute(
        select(Keyword.slug, Keyword.name, count)
        .outerjoin(card_keywords, Keyword.id == card_keywords.c.keyword_id)
        .group_by(Keyword.id, Keyword.slug, Keyword.name)
        .order_by(count.desc(), Keyword.name.asc(), Keyword.slug.asc())
    )
    return [KeywordCatalogItem(slug=slug, name=name, card_count=n) for slug, name, n in rows]


def list_keyword_cards(
    db: Session, slug: str, *, page: int, limit: int, sort: str = "number", order: str = "asc"
):
    exists = db.scalar(select(Keyword.id).where(func.lower(Keyword.slug) == slug.lower()).limit(1))
    if exists is None:
        raise APIError(ErrorCode.KEYWORD_NOT_FOUND, "Keyword not found.", 404)
    # Case-distinct slugs match as a union, consistent with the existing filter.
    return list_cards(
        db, page=page, limit=limit, sort=sort, order=order, filters=CardFilters(keyword=slug)
    )
