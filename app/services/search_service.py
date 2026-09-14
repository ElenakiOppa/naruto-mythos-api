"""Bounded SQL search with exact identifier/name/prefix/substring ranking."""

from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Card, CardSet, Keyword
from app.schemas.card import CardSummary
from app.schemas.error import ErrorCode
from app.schemas.keyword import KeywordResponse
from app.schemas.search import CardSearchResult, KeywordSearchResult, SetSearchResult
from app.schemas.set import SetSummary
from app.services.card_service import card_summary_options
from app.utils.errors import APIError


def search(db: Session, q: str, limit: int = 20):
    q = q.strip()
    if len(q) < 2:
        raise APIError(
            ErrorCode.INVALID_FILTER, "Search query must contain at least 2 characters.", 400
        )
    if not 1 <= limit <= 50:
        raise APIError(ErrorCode.INVALID_PAGINATION, "Search limit must be between 1 and 50.", 400)
    candidates = []
    entities: tuple[tuple[Any, ...], ...] = (
        (
            Card,
            Card.public_id,
            (Card.name, Card.public_id, Card.card_number, Card.subtitle),
            CardSummary,
            CardSearchResult,
            "card",
        ),
        (
            CardSet,
            CardSet.public_id,
            (CardSet.name, CardSet.public_id, CardSet.code),
            SetSummary,
            SetSearchResult,
            "set",
        ),
        (
            Keyword,
            Keyword.slug,
            (Keyword.name, Keyword.slug),
            KeywordResponse,
            KeywordSearchResult,
            "keyword",
        ),
    )
    for priority, (model, identifier, fields, schema, wrapper, key) in enumerate(entities):
        rank = case(
            (func.lower(identifier) == q.lower(), 0),
            (func.lower(model.name) == q.lower(), 1),
            (model.name.istartswith(q, autoescape=True), 2),
            else_=3,
        )
        stmt = (
            select(model, rank.label("match_rank"))
            .where(or_(*(field.icontains(q, autoescape=True) for field in fields)))
            .order_by(rank, func.lower(model.name), model.name, identifier)
            .limit(limit)
        )
        if model is Card:
            stmt = stmt.options(*card_summary_options()).execution_options(populate_existing=True)
        for ordinal, (entity, score) in enumerate(db.execute(stmt)):
            # SQL ordinal retains the database's alphabetical collation when merging.
            candidates.append(
                (score, priority, ordinal, wrapper(**{key: schema.model_validate(entity)}))
            )
    # Top L per type is sufficient: a later item already has L predecessors of its
    # own type. Merge at most 3L candidates and return at most L across all types.
    candidates.sort(key=lambda item: item[:3])
    return [item[3] for item in candidates[:limit]]
