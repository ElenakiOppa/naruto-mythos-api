"""Analysis-only canonical identity derivation (Phase 13B design, not implementation).

Follows the project's existing canonicalization convention (NFC-normalized,
sort-keyed, compact-separator JSON, SHA-256 -- see `importer/staging/identity.py`
and `importer/hashing.py`) so a future real implementation can adopt this
directly. Nothing here writes to a database or generates production IDs.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass

from .models import SourceCardRecord


def nfc_canonical_json(value: dict) -> str:
    return unicodedata.normalize(
        "NFC", json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalExpansionKey:
    """Proposed canonical Expansion identity (analysis only)."""

    name: str

    def payload(self) -> dict:
        return {"version": 1, "kind": "EXPANSION_ANALYSIS", "name": self.name}

    def identity_hash(self) -> str:
        return sha256_hex(nfc_canonical_json(self.payload()))

    def analysis_public_id(self) -> str:
        return "exp_" + self.identity_hash()[:56]


@dataclass(frozen=True)
class CanonicalCardKey:
    """Proposed canonical Card (gameplay-design) identity (analysis only).

    Deliberately excludes edition/rarity/variant/title: evidence (see
    `analyzer.card_grouping_report`) shows (expansion, printed_identifier)
    groups are 100% title/card-type invariant across all 636 real records.
    """

    expansion: str
    printed_identifier: str

    def payload(self) -> dict:
        return {
            "version": 1,
            "kind": "CARD_ANALYSIS",
            "expansion": self.expansion,
            "printed_identifier": self.printed_identifier,
        }

    def identity_hash(self) -> str:
        return sha256_hex(nfc_canonical_json(self.payload()))

    def analysis_public_id(self) -> str:
        return "crd_" + self.identity_hash()[:56]


@dataclass(frozen=True)
class CanonicalPrintingKey:
    """Semantic Printing fingerprint (analysis only) -- deliberately excludes
    any opaque source identifier.

    Human review (Phase 13B identity-closure round) rejected `source_uid` as
    part of canonical semantic identity. Re-analysis of the 7 residual
    collisions found when `source_uid` is removed (15 records; see
    `analyzer.collision_key_progression`) showed every one is fully resolved
    by two additional *evidence-backed, publisher-assigned* fields already
    present on every record:

    - `card_version` (the source's own "V1"/"V2" reprint-version tag) resolves
      13 of 15 affected records (5 of 7 groups).
    - `stamp` (a small, controlled distribution-channel vocabulary -- NOT the
      freeform, typo-prone `obtain` text) resolves the final 2 records (the
      one remaining group, which shares an identical `card_version`).

    Adding both to the semantic fields below yields **zero** collisions
    across all 636 real records, with no dependency on `source_uid`, `SKU`,
    or any randomly-generated identifier.
    """

    expansion: str
    edition: str | None
    printed_identifier: str
    rarity: str
    variant: str | None
    card_version: str | None
    stamp: str | None

    def payload(self) -> dict:
        return {
            "version": 2,
            "kind": "PRINTING_SEMANTIC_FINGERPRINT",
            "expansion": self.expansion,
            "edition": self.edition,
            "printed_identifier": self.printed_identifier,
            "rarity": self.rarity,
            "variant": self.variant,
            "card_version": self.card_version,
            "stamp": self.stamp,
        }

    def identity_hash(self) -> str:
        return sha256_hex(nfc_canonical_json(self.payload()))

    def analysis_public_id(self) -> str:
        return "prn_" + self.identity_hash()[:56]

    @classmethod
    def from_record(cls, record: SourceCardRecord) -> CanonicalPrintingKey:
        if record.set is None or record.id is None or record.rarity is None:
            raise ValueError("Incomplete printing identity: set/id/rarity required")
        return cls(
            expansion=record.set,
            edition=record.edition,
            printed_identifier=record.id,
            rarity=record.rarity,
            variant=record.variant,
            card_version=record.card_version,
            stamp=record.stamp or None,
        )


@dataclass(frozen=True)
class SourceIdentity:
    """Publisher-assigned source record identity: provenance/audit evidence only.

    Never hashed into, and never a substitute for, canonical semantic
    identity. Used solely to reconcile a domain Printing against the
    vendor's own catalogue row across refreshes (e.g. detecting that a
    `source_uid` changed while the semantic fingerprint stayed the same).
    """

    source_uid: int | None
    source_sku: str | None

    @classmethod
    def from_record(cls, record: SourceCardRecord) -> SourceIdentity:
        return cls(source_uid=record.uid, source_sku=record.sku)
