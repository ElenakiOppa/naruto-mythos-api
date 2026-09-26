"""Explicit advanced card filters; relationship predicates never multiply rows."""

from dataclasses import dataclass

from sqlalchemy import Select, func, or_

from app.models import Card, CardSet, CardVariant, Edition, Keyword
from app.schemas.error import ErrorCode
from app.utils.errors import APIError


@dataclass(frozen=True)
class CardFilters:
    rarity: str | None = None
    card_type: str | None = None
    keyword: str | None = None
    variant: str | None = None
    language: str | None = None
    edition: str | None = None
    chakra_min: int | None = None
    chakra_max: int | None = None
    power_min: int | None = None
    power_max: int | None = None


def apply_card_filters(statement: Select, filters: CardFilters) -> Select:
    # Validate before execution; keep business-rule errors in the public contract.
    for stat in ("chakra", "power"):
        lower, upper = getattr(filters, stat + "_min"), getattr(filters, stat + "_max")
        for suffix, value in (("min", lower), ("max", upper)):
            if value is not None and value < 0:
                raise APIError(
                    ErrorCode.INVALID_FILTER,
                    f"{stat}_{suffix} must be greater than or equal to 0.",
                    400,
                )
        if lower is not None and upper is not None and lower > upper:
            raise APIError(
                ErrorCode.INVALID_FILTER, f"{stat}_min cannot be greater than {stat}_max.", 400
            )
        stat_column = Card.chakra if stat == "chakra" else Card.power
        if lower is not None:
            statement = statement.where(stat_column >= lower)
        if upper is not None:
            statement = statement.where(stat_column <= upper)
    for column, value in (
        (Card.card_type, filters.card_type),
        (CardSet.language, filters.language),
    ):
        if value is not None:
            statement = statement.where(func.lower(column) == value.lower())
    if filters.rarity is not None:
        value = filters.rarity.casefold()
        statement = statement.where(
            Card.variants.any(
                or_(
                    func.lower(CardVariant.normalized_rarity) == value,
                    func.lower(CardVariant.collector_class) == value,
                    func.lower(CardVariant.rarity_override) == value,
                )
            )
        )
    if filters.edition is not None:
        statement = statement.where(
            Card.variants.any(
                CardVariant.edition_record.has(
                    func.lower(Edition.public_id) == filters.edition.casefold()
                )
            )
        )
    if filters.keyword is not None:
        statement = statement.where(
            Card.keywords.any(func.lower(Keyword.slug) == filters.keyword.lower())
        )
    if filters.variant is not None:
        statement = statement.where(
            Card.variants.any(
                or_(
                    func.lower(CardVariant.normalized_treatment) == filters.variant.casefold(),
                    func.lower(CardVariant.source_variant) == filters.variant.casefold(),
                    func.lower(CardVariant.variant_type) == filters.variant.casefold(),
                )
            )
        )
    return statement
