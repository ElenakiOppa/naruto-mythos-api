"""Transactional, idempotent persistence for an approved Phase 14 dry-run plan.

This is deliberately an execution helper, not a scraper or production runner.
The caller supplies an existing SQLAlchemy Session connected to a disposable
PostgreSQL database. The helper never creates an engine, reads configuration,
fetches sources, imports artwork, or commits partial work.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Card, CardImage, CardSet, CardVariant, Keyword, SourceRecord
from app.models.keyword import card_keywords
from app.models.translation import PrintingTranslation
from importer.catalogue_design.identity import CanonicalExpansionKey

SOURCE_NAME = "naruto_mythos_phase14_snapshot"


class CataloguePersistenceError(RuntimeError):
    """The approved plan conflicts with existing database state."""


@dataclass(frozen=True)
class PersistenceCounts:
    sets: int
    cards: int
    printings: int
    translations: int
    provenance: int
    image_references: int
    keywords: int
    associations: int


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    if not normalized:
        raise CataloguePersistenceError(f"keyword has no usable slug: {value!r}")
    return normalized[:64]


def _require_equal(entity: Any, field: str, expected: Any) -> None:
    actual = getattr(entity, field)
    if actual != expected:
        raise CataloguePersistenceError(
            f"existing {type(entity).__name__}.{field} conflicts: {actual!r} != {expected!r}"
        )


def _get_or_create_set(session: Session, expansion: str) -> CardSet:
    public_id = CanonicalExpansionKey(expansion).analysis_public_id()
    card_set = session.scalar(select(CardSet).where(CardSet.public_id == public_id))
    if card_set is None:
        card_set = CardSet(public_id=public_id, name=expansion, language="EN")
        session.add(card_set)
        session.flush()
    else:
        _require_equal(card_set, "name", expansion)
    return card_set


def _get_or_create_keyword(session: Session, value: str) -> Keyword:
    slug = _slug(value)
    keyword = session.scalar(select(Keyword).where(Keyword.slug == slug))
    if keyword is None:
        keyword = Keyword(slug=slug, name=value)
        session.add(keyword)
        session.flush()
    elif keyword.name != value:
        raise CataloguePersistenceError(
            f"existing Keyword.name conflicts for slug {slug!r}: {keyword.name!r} != {value!r}"
        )
    return keyword


def _get_or_create_card(
    session: Session,
    card_data: dict[str, Any],
    printing_data: dict[str, Any],
    card_set: CardSet,
) -> Card:
    public_id = card_data["public_id"]
    card = session.scalar(select(Card).where(Card.public_id == public_id))
    raw = _reference_raw(printing_data)
    localization = printing_data["localizations"]["en"]
    values = {
        "public_id": public_id,
        "set_id": card_set.id,
        "card_number": card_data["printed_identifier"],
        "name": card_data["title"] or "Unnamed card",
        "subtitle": localization.get("subtitle"),
        "card_type": raw.get("CardType"),
        "rarity": printing_data["identity"]["rarity"],
        "chakra": _observed_integer(raw.get("Chakra")),
        "power": _observed_integer(raw.get("Power")),
        "points": _observed_integer(raw.get("Points")),
        "faction": raw.get("Group"),
        "ability_text": localization.get("rules_text"),
    }
    if card is None:
        card = Card(**values)
        card_set.cards.append(card)
        session.flush()
    else:
        for field, expected in values.items():
            if field == "set_id":
                continue
            _require_equal(card, field, expected)
        _require_equal(card, "set_id", card_set.id)
    return card


def _get_or_create_printing(
    session: Session,
    printing_data: dict[str, Any],
    card: Card,
) -> CardVariant:
    public_id = printing_data["public_id"]
    identity = printing_data["identity"]
    values = {
        "public_id": public_id,
        "card_id": card.id,
        "variant_type": identity["variant"] or "standard",
        "finish": identity["variant"],
        "rarity_override": identity["rarity"],
        "collector_number": identity["printed_identifier"],
        "language": "EN",
        "edition": identity["edition"],
        "source_variant": identity["variant"],
        "card_version": identity["card_version"],
        "stamp": identity["stamp"],
        "serial_numbered": False,
    }
    printing = session.scalar(select(CardVariant).where(CardVariant.public_id == public_id))
    if printing is None:
        printing = CardVariant(**values)
        card.variants.append(printing)
        session.flush()
    else:
        for field, expected in values.items():
            if field == "public_id":
                continue
            _require_equal(printing, field, expected)
    return printing


def _persist_translation(
    session: Session, printing: CardVariant, language: str, values: dict[str, Any]
) -> None:
    translation = session.scalar(
        select(PrintingTranslation).where(
            PrintingTranslation.printing_id == printing.id,
            PrintingTranslation.language == language.upper(),
        )
    )
    expected = {
        "title": values.get("title"),
        "subtitle": values.get("subtitle"),
        "rules_text": values.get("rules_text"),
        "edition_label": values.get("edition_label"),
        "distribution_text": values.get("distribution_text"),
        "image_url": values.get("image_url"),
    }
    if translation is None:
        session.add(PrintingTranslation(printing=printing, language=language.upper(), **expected))
    else:
        for field, value in expected.items():
            _require_equal(translation, field, value)


def _persist_provenance(
    session: Session, printing: CardVariant, observation: dict[str, Any]
) -> None:
    source_uid = observation.get("source_uid")
    source_sku = observation.get("source_sku")
    language = observation["language"]
    external_id = f"{source_uid}:{language}"
    existing = session.scalar(
        select(SourceRecord).where(
            SourceRecord.printing_id == printing.id,
            SourceRecord.external_id == external_id,
            SourceRecord.source_name == SOURCE_NAME,
        )
    )
    if existing is None:
        session.add(
            SourceRecord(
                entity_type="card_variants",
                entity_id=printing.id,
                printing_id=printing.id,
                source_name=SOURCE_NAME,
                external_id=external_id,
                source_uid=str(source_uid) if source_uid is not None else None,
                source_sku=source_sku,
                observation=observation["observation"],
            )
        )
    else:
        _require_equal(existing, "source_uid", str(source_uid) if source_uid is not None else None)
        _require_equal(existing, "source_sku", source_sku)
        _require_equal(existing, "observation", observation["observation"])


def _persist_image(
    session: Session, printing: CardVariant, language: str, image_url: str | None
) -> None:
    if not image_url:
        return
    image_type = f"front-{language.lower()}"
    existing = session.scalar(
        select(CardImage).where(
            CardImage.card_id == printing.card_id,
            CardImage.variant_id == printing.id,
            CardImage.image_type == image_type,
            CardImage.url == image_url,
        )
    )
    if existing is None:
        session.add(
            CardImage(
                card_id=printing.card_id,
                variant_id=printing.id,
                image_type=image_type,
                url=image_url,
                source_name=SOURCE_NAME,
                hosted_by_us=False,
            )
        )


def _persist_keywords(session: Session, card: Card, values: list[str]) -> None:
    for value in sorted(set(values)):
        keyword = _get_or_create_keyword(session, value)
        if keyword not in card.keywords:
            card.keywords.append(keyword)


def _observed_integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise CataloguePersistenceError(f"unsupported numeric observation: {value!r}")


def _reference_raw(printing_data: dict[str, Any]) -> dict[str, Any]:
    for observation in printing_data["source_observations"]:
        if observation["language"] == "en":
            return observation["observation"]
    raise CataloguePersistenceError("missing English reference observation")


def persist_catalogue_plan(session: Session, result: dict[str, Any]) -> PersistenceCounts:
    """Persist one approved plan transactionally and idempotently.

    The session must be bound to a disposable/local database. Any exception
    rolls back the entire import; existing conflicting rows are never updated.
    """
    plan = result["plan"]
    # SQLAlchemy may autobegin a read-only transaction before this helper is
    # called. The executor owns the import boundary, so discard that empty
    # caller transaction before opening the atomic write transaction.
    if session.in_transaction():
        session.rollback()
    try:
        with session.begin():
            cards_by_id = {card["public_id"]: card for card in plan["cards"]}
            sets_by_expansion: dict[str, CardSet] = {}
            cards_by_public_id: dict[str, Card] = {}
            for printing_data in plan["printings"]:
                card_data = cards_by_id[printing_data["card_id"]]
                expansion = card_data["expansion"]
                card_set = sets_by_expansion.setdefault(
                    expansion, _get_or_create_set(session, expansion)
                )
                card = cards_by_public_id.get(card_data["public_id"])
                if card is None:
                    card = _get_or_create_card(session, card_data, printing_data, card_set)
                    cards_by_public_id[card.public_id] = card
                    raw = _reference_raw(printing_data)
                    _persist_keywords(
                        session,
                        card,
                        [
                            value
                            for value in (
                                raw.get("Keyword1"),
                                raw.get("Keyword2"),
                                raw.get("Group"),
                            )
                            if value
                        ],
                    )
                printing = _get_or_create_printing(session, printing_data, card)
                for language, localization in printing_data["localizations"].items():
                    _persist_translation(session, printing, language, localization)
                    _persist_image(session, printing, language, localization.get("image_url"))
                for observation in printing_data["source_observations"]:
                    _persist_provenance(session, printing, observation)

        return count_catalogue(session)
    except Exception:
        session.rollback()
        raise


def count_catalogue(session: Session) -> PersistenceCounts:
    """Return database counts used by first/second import verification."""
    return PersistenceCounts(
        sets=session.scalar(select(func.count()).select_from(CardSet)) or 0,
        cards=session.scalar(select(func.count()).select_from(Card)) or 0,
        printings=session.scalar(select(func.count()).select_from(CardVariant)) or 0,
        translations=session.scalar(select(func.count()).select_from(PrintingTranslation)) or 0,
        provenance=session.scalar(select(func.count()).select_from(SourceRecord)) or 0,
        image_references=session.scalar(select(func.count()).select_from(CardImage)) or 0,
        keywords=session.scalar(select(func.count()).select_from(Keyword)) or 0,
        associations=session.scalar(select(func.count()).select_from(card_keywords)) or 0,
    )
