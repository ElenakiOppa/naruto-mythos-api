"""Analysis-only data model for the Phase 13B catalogue identity design.

Pure Python: no SQLAlchemy, no database engine, no FastAPI imports. Nothing
here is wired into the production importer/staging/API code. It exists to
reason about the real Phase 13A acquisition and propose (not implement) a
domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Fields the Phase 13A acquisition observed on every/most source records.
# This list is NOT assumed exhaustive -- anything else lands in `extra`.
KNOWN_FIELDS = (
    "Uid",
    "SKU",
    "ID",
    "Set",
    "Edition",
    "Langs",
    "CardType",
    "Title",
    "Rarity",
    "Variant",
    "Illustration",
    "CardVersion",
    "Version",
    "Group",
    "Chakra",
    "Power",
    "Points",
    "Keyword1",
    "Keyword2",
    "Text",
    "Obtain",
    "Stamp",
    "Image",
    "Order",
)


@dataclass(frozen=True)
class SourceCardRecord:
    """One raw print-record exactly as returned by the source API, plus overflow."""

    uid: int | None
    sku: str | None
    id: str | None
    set: str | None
    edition: str | None
    langs: tuple[str, ...]
    card_type: str | None
    title: str | None
    rarity: str | None
    variant: str | None
    illustration: str | None
    card_version: str | None
    version: str | None
    group: str | None
    chakra: Any
    power: Any
    points: Any
    keyword1: str | None
    keyword2: str | None
    text: str | None
    obtain: str | None
    stamp: str | None
    image: str | None
    order: Any
    extra: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SourceCardRecord:
        extra = {k: v for k, v in raw.items() if k and k not in KNOWN_FIELDS}
        langs = tuple(raw.get("Langs") or ())
        return cls(
            uid=raw.get("Uid"),
            sku=raw.get("SKU"),
            id=raw.get("ID"),
            set=raw.get("Set"),
            edition=raw.get("Edition") or None,
            langs=langs,
            card_type=raw.get("CardType"),
            title=raw.get("Title"),
            rarity=raw.get("Rarity"),
            variant=raw.get("Variant") or None,
            illustration=raw.get("Illustration"),
            card_version=raw.get("CardVersion"),
            version=raw.get("Version"),
            group=raw.get("Group"),
            chakra=raw.get("Chakra"),
            power=raw.get("Power"),
            points=raw.get("Points"),
            keyword1=raw.get("Keyword1"),
            keyword2=raw.get("Keyword2"),
            text=raw.get("Text"),
            obtain=raw.get("Obtain"),
            stamp=raw.get("Stamp"),
            image=raw.get("Image"),
            order=raw.get("Order"),
            extra=extra,
            raw=dict(raw),
        )


class MappingState(StrEnum):
    MAPPED = "MAPPED"
    AMBIGUOUS = "AMBIGUOUS"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class MappingResult:
    record_uid: int | None
    state: MappingState
    reason: str | None
    canonical_public_id: str | None
    preserved_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UidAuditResult:
    total: int
    unique: int
    null_count: int
    duplicate_uids: tuple[int, ...]
    min_uid: int | None
    max_uid: int | None
    is_contiguous: bool
    gap_count: int


@dataclass(frozen=True)
class SkuAuditResult:
    total: int
    unique: int
    null_count: int
    strict_pattern_matches: int
    unmatched_sample: tuple[str, ...]


@dataclass(frozen=True)
class CollisionKeyResult:
    key_name: str
    unique_keys: int
    colliding_keys: int
    max_group_size: int
    example_colliding_keys: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class CardGroupingReport:
    group_count: int
    groups_with_multiple_printings: int
    title_cardtype_invariant_groups: int
    mismatched_groups: tuple[dict[str, Any], ...]
    max_printings_per_card: int


@dataclass(frozen=True)
class MappingSummary:
    total: int
    mapped: int
    ambiguous: int
    rejected: int
    results: tuple[MappingResult, ...]
