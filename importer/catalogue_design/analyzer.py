"""Phase 13B analysis functions over source card records.

All functions here are pure and deterministic given a list of
`SourceCardRecord`. The only I/O is `load_records_from_acquisition`, which
reads the already-acquired local Phase 13A files (never performs a live
fetch). Tests exercise the pure functions with small invented fixtures, not
the real 636-record catalogue.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from typing import Any

from .identity import CanonicalPrintingKey
from .models import (
    CardGroupingReport,
    CollisionKeyResult,
    MappingResult,
    MappingState,
    MappingSummary,
    SkuAuditResult,
    SourceCardRecord,
    UidAuditResult,
)

DEFAULT_ACQUISITION_ROOT = Path("data/acquisition")

_STRICT_SKU_PATTERN = re.compile(r"^NM-S\d+E\d+-[A-Z]+(\d{3}|MSS\d+)[A-Z]*V\d+$")


# --------------------------------------------------------------------------
# Loading (real local acquisition only -- no live fetch, no fan sources)
# --------------------------------------------------------------------------


def load_records_from_acquisition(
    root: Path = DEFAULT_ACQUISITION_ROOT,
) -> dict[str, list[SourceCardRecord]]:
    """Load per-language record lists from the already-acquired Phase 13A files.

    Raises FileNotFoundError if the manifest or a referenced raw file is
    missing locally -- callers must stop rather than fetch a replacement.
    """
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Phase 13A manifest not found at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    latest_by_lang: dict[str, dict[str, Any]] = {}
    for entry in manifest:
        url = entry.get("source_url", "")
        if "cards.narutotcgmythos.com/api/cards" not in url or not entry.get("sha256"):
            continue
        lang = url.rsplit("lang=", 1)[-1]
        latest_by_lang[lang] = entry  # manifest is append-only; last wins (most recent)

    result: dict[str, list[SourceCardRecord]] = {}
    for lang, entry in latest_by_lang.items():
        raw_path = Path(entry["raw_file"])
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Raw acquisition file for lang={lang} not found at {raw_path}; "
                "stop rather than re-fetching automatically"
            )
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        cards = payload[0]["Cards"] if payload and "Cards" in payload[0] else []
        result[lang] = [SourceCardRecord.from_raw(c) for c in cards]
    return result


# --------------------------------------------------------------------------
# Uid / SKU audits
# --------------------------------------------------------------------------


def audit_uid(records: list[SourceCardRecord]) -> UidAuditResult:
    uids = [r.uid for r in records]
    non_null = [u for u in uids if u is not None]
    null_count = len(uids) - len(non_null)
    counts = collections.Counter(non_null)
    duplicates = tuple(sorted(u for u, c in counts.items() if c > 1))
    sorted_uids = sorted(non_null)
    gaps = [sorted_uids[i + 1] - sorted_uids[i] for i in range(len(sorted_uids) - 1)]
    gap_count = sum(1 for g in gaps if g > 1)
    return UidAuditResult(
        total=len(uids),
        unique=len(counts),
        null_count=null_count,
        duplicate_uids=duplicates,
        min_uid=min(non_null) if non_null else None,
        max_uid=max(non_null) if non_null else None,
        is_contiguous=(gap_count == 0 and len(sorted_uids) > 1),
        gap_count=gap_count,
    )


def audit_sku(records: list[SourceCardRecord]) -> SkuAuditResult:
    skus = [r.sku for r in records]
    non_null = [s for s in skus if s]
    null_count = len(skus) - len(non_null)
    counts = collections.Counter(non_null)
    matched = sum(1 for s in non_null if _STRICT_SKU_PATTERN.match(s))
    unmatched = tuple(s for s in non_null if not _STRICT_SKU_PATTERN.match(s))[:20]
    return SkuAuditResult(
        total=len(skus),
        unique=len(counts),
        null_count=null_count,
        strict_pattern_matches=matched,
        unmatched_sample=unmatched,
    )


# --------------------------------------------------------------------------
# Progressive collision-key analysis
# --------------------------------------------------------------------------


def _key1(r: SourceCardRecord) -> tuple:
    return (r.set, r.id)


def _key2(r: SourceCardRecord) -> tuple:
    return (r.set, r.edition, r.id)


def _key3(r: SourceCardRecord) -> tuple:
    return (r.set, r.edition, r.id, r.rarity)


def _key4(r: SourceCardRecord) -> tuple:
    return (r.set, r.edition, r.id, r.rarity, r.variant)


CANDIDATE_KEYS = (
    ("set+id", _key1),
    ("set+edition+id", _key2),
    ("set+edition+id+rarity", _key3),
    ("set+edition+id+rarity+variant", _key4),
)


def collision_key_progression(records: list[SourceCardRecord]) -> list[CollisionKeyResult]:
    results = []
    for name, fn in CANDIDATE_KEYS:
        groups: dict[tuple, list[SourceCardRecord]] = collections.defaultdict(list)
        for r in records:
            groups[fn(r)].append(r)
        colliding = {k: v for k, v in groups.items() if len(v) > 1}
        results.append(
            CollisionKeyResult(
                key_name=name,
                unique_keys=len(groups),
                colliding_keys=len(colliding),
                max_group_size=max((len(v) for v in groups.values()), default=0),
                example_colliding_keys=tuple(sorted(colliding.keys(), key=str)[:10]),
            )
        )
    return results


# --------------------------------------------------------------------------
# Card grouping validation (evidence-based, no name-only heuristics)
# --------------------------------------------------------------------------


def card_grouping_report(records: list[SourceCardRecord]) -> CardGroupingReport:
    groups: dict[tuple, list[SourceCardRecord]] = collections.defaultdict(list)
    for r in records:
        groups[_key1(r)].append(r)

    multi = {k: v for k, v in groups.items() if len(v) > 1}
    mismatches = []
    invariant_count = 0
    for key, members in multi.items():
        titles = {m.title for m in members}
        types = {m.card_type for m in members}
        if len(titles) == 1 and len(types) == 1:
            invariant_count += 1
        else:
            mismatches.append(
                {
                    "key": key,
                    "titles": sorted(t for t in titles if t is not None),
                    "card_types": sorted(t for t in types if t is not None),
                    "uids": sorted(m.uid for m in members if m.uid is not None),
                }
            )

    return CardGroupingReport(
        group_count=len(groups),
        groups_with_multiple_printings=len(multi),
        title_cardtype_invariant_groups=invariant_count,
        mismatched_groups=tuple(mismatches),
        max_printings_per_card=max((len(v) for v in groups.values()), default=0),
    )


# --------------------------------------------------------------------------
# All-636 (or all-N) mapping classification -- the acceptance test
# --------------------------------------------------------------------------

_PRESERVED_FIELD_NAMES = (
    "uid",
    "sku",
    "id",
    "set",
    "edition",
    "card_type",
    "rarity",
    "variant",
    "card_version",
    "stamp",
    "langs",
)


def map_all_records(records: list[SourceCardRecord]) -> MappingSummary:
    """Classify every record as MAPPED / AMBIGUOUS / REJECTED.

    Identity collisions are detected purely from the semantic fingerprint
    (`CanonicalPrintingKey`, which excludes `source_uid`/`SKU` by design --
    see the Phase 13B identity-closure review). `source_uid` is still
    required on each record for provenance/reconciliation evidence, but it
    never participates in the collision check: two records with different
    Uids and an identical fingerprint are still correctly flagged AMBIGUOUS,
    and a single record whose Uid changes between refreshes (fingerprint
    otherwise unchanged) is unaffected because Uid isn't hashed at all.
    """
    results = []
    seen_public_ids: dict[str, int] = {}
    for r in records:
        if r.uid is None or not r.set or not r.id or not r.rarity:
            results.append(
                MappingResult(
                    record_uid=r.uid,
                    state=MappingState.REJECTED,
                    reason="missing required field (uid/set/id/rarity)",
                    canonical_public_id=None,
                )
            )
            continue
        try:
            key = CanonicalPrintingKey.from_record(r)
            public_id = key.analysis_public_id()
        except ValueError as exc:
            results.append(
                MappingResult(
                    record_uid=r.uid,
                    state=MappingState.REJECTED,
                    reason=str(exc),
                    canonical_public_id=None,
                )
            )
            continue

        if public_id in seen_public_ids:
            results.append(
                MappingResult(
                    record_uid=r.uid,
                    state=MappingState.AMBIGUOUS,
                    reason=(
                        "semantic fingerprint collides with uid="
                        f"{seen_public_ids[public_id]}; requires an approved additional "
                        "discriminator or human review, not a silent uid-based resolution"
                    ),
                    canonical_public_id=public_id,
                )
            )
            continue
        seen_public_ids[public_id] = r.uid

        preserved = {name: getattr(r, name) for name in _PRESERVED_FIELD_NAMES}
        results.append(
            MappingResult(
                record_uid=r.uid,
                state=MappingState.MAPPED,
                reason=None,
                canonical_public_id=public_id,
                preserved_fields=preserved,
            )
        )

    mapped = sum(1 for x in results if x.state == MappingState.MAPPED)
    ambiguous = sum(1 for x in results if x.state == MappingState.AMBIGUOUS)
    rejected = sum(1 for x in results if x.state == MappingState.REJECTED)
    return MappingSummary(
        total=len(results),
        mapped=mapped,
        ambiguous=ambiguous,
        rejected=rejected,
        results=tuple(results),
    )


# --------------------------------------------------------------------------
# Round-trip validation
# --------------------------------------------------------------------------


def round_trip_ok(record: SourceCardRecord, mapping: MappingResult) -> bool:
    """Verify the preserved fields on a MAPPED result equal the raw source record."""
    if mapping.state != MappingState.MAPPED:
        return False
    checks = {
        "uid": record.uid,
        "sku": record.sku,
        "id": record.id,
        "set": record.set,
        "edition": record.edition,
        "card_type": record.card_type,
        "rarity": record.rarity,
        "variant": record.variant,
        "card_version": record.card_version,
        "stamp": record.stamp,
        "langs": record.langs,
    }
    return all(mapping.preserved_fields.get(k) == v for k, v in checks.items())


def language_invariance_check(
    records_by_lang: dict[str, list[SourceCardRecord]],
    fields: tuple[str, ...] = ("id", "set", "edition", "rarity", "variant", "sku"),
) -> tuple[int, list[dict[str, Any]]]:
    """Check that identity-relevant fields are invariant across languages for the same Uid.

    Returns (checked_pairs, mismatches).
    """
    by_lang_uid = {
        lang: {r.uid: r for r in recs if r.uid is not None}
        for lang, recs in records_by_lang.items()
    }
    reference_lang = "en" if "en" in by_lang_uid else next(iter(by_lang_uid), None)
    if reference_lang is None:
        return 0, []
    reference = by_lang_uid[reference_lang]

    checked = 0
    mismatches = []
    for lang, uid_map in by_lang_uid.items():
        if lang == reference_lang:
            continue
        for uid, ref_record in reference.items():
            other = uid_map.get(uid)
            if other is None:
                continue
            checked += 1
            for f in fields:
                if getattr(ref_record, f) != getattr(other, f):
                    mismatches.append(
                        {
                            "uid": uid,
                            "lang": lang,
                            "field": f,
                            "reference_value": getattr(ref_record, f),
                            "other_value": getattr(other, f),
                        }
                    )
    return checked, mismatches
