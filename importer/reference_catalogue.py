"""Reconcile curated collector references with the local upstream catalogue."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from app.utils.edition_identity import normalize_edition_name
from app.utils.printing_taxonomy import normalize_printing_taxonomy
from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.catalogue_design.identity import (
    CanonicalCardKey,
    CanonicalEditionKey,
    CanonicalExpansionKey,
    CanonicalPrintingKey,
)

DEFAULT_REFERENCE_PATH = Path("data/reference/konoha_shido_1st_edition_master.json")
TARGET_SET = "Set 1: Konoha Shidō"
TARGET_EDITION = "1st edition"
REFERENCE_SOURCE = "konoha_shido_1st_edition_master"

RARITY_LABELS = {
    "c": "Common",
    "uc": "Uncommon",
    "r": "Rare",
    "ra": "Rare ART",
    "s": "Secret",
    "sv": "Secret Variant",
    "l": "Legendary",
    "m": "Mythos",
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "rare art": "Rare ART",
    "secret": "Secret",
    "secret variant": "Secret Variant",
    "legendary": "Legendary",
    "mythos": "Mythos",
    "mission": "Mission",
}
RARITY_LABELS_FOLDED = {key.casefold(): value for key, value in RARITY_LABELS.items()}

SIMPLE_TREATMENTS = {
    "normal": "Normal",
    "full art": "FullArt",
    "fullart": "FullArt",
    "holo": "Holographic",
    "holographic": "Holographic",
    "standard": "Standard",
    "gold": "Gold",
}


class ReferenceReconciliationError(ValueError):
    """A curated identity cannot be safely reconciled without manual review."""


def _text(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFC", value or "").split())


def _fold(value: str | None) -> str:
    return _text(value).casefold()


def _number_key(value: str) -> str:
    folded = _fold(value)
    match = re.fullmatch(r"0*(\d+)([a-z]?)", folded)
    return f"{int(match.group(1))}{match.group(2)}" if match else folded


def _source_number(record) -> str | None:
    if record.card_type == "Mission":
        match = re.fullmatch(r"MSS\s*0*(\d+)", record.id or "", re.IGNORECASE)
    else:
        match = re.match(r"\s*0*(\d+)", record.id or "")
    return str(int(match.group(1))) if match else None


def _primary_name(value: str) -> str:
    return _fold(re.split(r"\s+-\s+", value, maxsplit=1)[0])


def _canonical_rarity(raw: str) -> str | None:
    return RARITY_LABELS_FOLDED.get(_fold(raw))


def _canonical_treatment(raw: str) -> str:
    folded = _fold(raw)
    return SIMPLE_TREATMENTS.get(folded, _text(raw))


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_entries(reference_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "konoha-shido-reference-v1":
        raise ReferenceReconciliationError("UNSUPPORTED_REFERENCE_SCHEMA")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != 396:
        raise ReferenceReconciliationError("REFERENCE_ENTRY_COUNT_MISMATCH")
    keys = [entry.get("reference_key") for entry in entries]
    if any(not isinstance(key, str) for key in keys) or len(set(keys)) != len(keys):
        raise ReferenceReconciliationError("DUPLICATE_REFERENCE_KEY")
    return payload, entries


def _resolve_card(entry: dict[str, Any], source_records: list[Any]) -> tuple[str, str, list[Any]]:
    number = _number_key(entry["collector_number"])
    primary = _primary_name(entry["card_name"])
    rarity = _canonical_rarity(entry["rarity_raw"])

    if number == "n/2000":
        candidates = [
            record
            for record in source_records
            if _fold(record.title) == primary
            and rarity is not None
            and _canonical_rarity(record.rarity or "") == rarity
        ]
    elif rarity == "Mission":
        candidates = [
            record
            for record in source_records
            if record.card_type == "Mission"
            and _source_number(record) == number
            and _fold(record.title) == primary
        ]
    else:
        suffix_alias = number.endswith("a") and rarity == "Rare ART"
        base_number = number[:-1] if suffix_alias else number
        candidates = [
            record
            for record in source_records
            if record.card_type != "Mission"
            and _source_number(record) == base_number
            and _fold(record.title) == primary
        ]

    card_keys = {(record.set, record.id) for record in candidates}
    if len(card_keys) != 1:
        raise ReferenceReconciliationError(
            "UNMAPPED_OR_AMBIGUOUS_CANONICAL_CARD:" + entry["reference_key"]
        )
    expansion, printed_identifier = next(iter(card_keys))
    if expansion != TARGET_SET:
        raise ReferenceReconciliationError("REFERENCE_CARD_OUTSIDE_TARGET_SET")
    card_public_id = CanonicalCardKey(expansion, printed_identifier).analysis_public_id()
    return card_public_id, printed_identifier, candidates


def _reference_taxonomy(entry: dict[str, Any], card_type: str | None) -> dict[str, str | None]:
    normalized_rarity = _canonical_rarity(entry["rarity_raw"])
    normalized_variant = _canonical_treatment(entry["variant_raw"])
    taxonomy = normalize_printing_taxonomy(
        entry["rarity_raw"],
        entry["variant_raw"],
        card_type,
    )
    if normalized_rarity == "Mission" and card_type == "Mission":
        return {
            "normalized_rarity": None,
            "collector_class": "Mission",
            "rarity_resolution_status": "MAPPED",
            "normalized_treatment": normalized_variant,
            "variant_resolution_status": "MAPPED",
        }
    if normalized_rarity is None:
        raise ReferenceReconciliationError("UNRESOLVED_REFERENCE_RARITY")
    return {
        "normalized_rarity": normalized_rarity,
        "collector_class": taxonomy.collector_class,
        "rarity_resolution_status": "MAPPED",
        "normalized_treatment": normalized_variant,
        "variant_resolution_status": "MAPPED",
    }


def build_reference_reconciliation(
    reference_path: Path = DEFAULT_REFERENCE_PATH,
) -> dict[str, Any]:
    """Create a deterministic dry-run reconciliation; this function never writes."""
    reference, entries = _load_entries(reference_path)
    source_by_language = load_records_from_acquisition()
    upstream_records = source_by_language["en"]
    source_records = [record for record in upstream_records if record.set == TARGET_SET]
    first_edition_rows = [record for record in source_records if record.edition == TARGET_EDITION]
    edition_public_id = CanonicalEditionKey(
        set_public_id=CanonicalExpansionKey(TARGET_SET).analysis_public_id(),
        normalized_name=normalize_edition_name(TARGET_EDITION),
    ).analysis_public_id()
    canonical_card_count = len(
        {
            CanonicalCardKey(record.set, record.id).analysis_public_id()
            for record in upstream_records
            if record.set is not None and record.id is not None
        }
    )
    upstream_printing_count = len(
        {
            CanonicalPrintingKey.from_record(record).analysis_public_id()
            for record in upstream_records
        }
    )
    if canonical_card_count != 318 or upstream_printing_count != 636:
        raise ReferenceReconciliationError("UPSTREAM_CANONICAL_BASELINE_MISMATCH")
    source_printings = {
        str(record.uid): CanonicalPrintingKey.from_record(record).analysis_public_id()
        for record in first_edition_rows
        if record.uid is not None
    }
    card_types = {
        CanonicalCardKey(TARGET_SET, record.id).analysis_public_id(): record.card_type
        for record in source_records
        if record.id is not None
    }
    matches: list[dict[str, Any]] = []
    curated: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    description_differences: list[dict[str, Any]] = []
    checklist_identities: Counter[tuple[str, str, str, str, str]] = Counter()
    used_source_uids: Counter[int] = Counter()

    for entry in entries:
        card_public_id, printed_identifier, card_candidates = _resolve_card(entry, source_records)
        card_type = card_types[card_public_id]
        taxonomy = _reference_taxonomy(entry, card_type)
        source_descriptors = sorted(
            {
                _text(f"{record.title} - {record.version}")
                if record.version
                else _text(record.title)
                for record in card_candidates
            }
        )
        reference_description = _fold(entry["card_name"])
        if not any(_fold(descriptor) == reference_description for descriptor in source_descriptors):
            description_differences.append(
                {
                    "reference_key": entry["reference_key"],
                    "collector_number": entry["collector_number"],
                    "reference_card_name": entry["card_name"],
                    "source_descriptions": source_descriptors,
                    "canonical_printed_identifier": printed_identifier,
                }
            )
        number_note = None
        normalized_collector_number = _number_key(entry["collector_number"])
        if normalized_collector_number == "n/2000":
            number_note = "Special collector label mapped by unique primary Card name and Legendary rarity; not treated as a serial value."
        elif normalized_collector_number.endswith("a"):
            number_note = "Rare ART suffix is retained in the reference number and maps to the base-number canonical Card."
        elif taxonomy["collector_class"] == "Mission":
            number_note = (
                "Mission ordinal resolves only in the Mission namespace (for example, 1 to MSS 01)."
            )
        collector_identity = (
            card_public_id,
            edition_public_id,
            taxonomy["normalized_rarity"] or taxonomy["collector_class"] or "",
            _fold(taxonomy["normalized_treatment"]),
            _number_key(entry["collector_number"]),
        )
        checklist_identities[collector_identity] += 1
        if checklist_identities[collector_identity] > 1:
            raise ReferenceReconciliationError("DUPLICATE_COLLECTIBLE_IDENTITY")

        same_card_rarity = [
            record
            for record in first_edition_rows
            if record.id is not None
            and CanonicalCardKey(TARGET_SET, record.id).analysis_public_id() == card_public_id
            and _canonical_rarity(record.rarity or "")
            == (taxonomy["normalized_rarity"] or taxonomy["collector_class"])
        ]
        source_treatment_matches = [
            record
            for record in same_card_rarity
            if record.variant
            and _fold(_canonical_treatment(record.variant))
            == _fold(taxonomy["normalized_treatment"])
        ]
        unspecified_source_rows = [record for record in same_card_rarity if not record.variant]

        upstream_record = None
        match_type = None
        if len(source_treatment_matches) == 1:
            upstream_record = source_treatment_matches[0]
            match_type = "EXACT_UPSTREAM_IDENTITY"
        elif len(source_treatment_matches) > 1:
            raise ReferenceReconciliationError("AMBIGUOUS_UPSTREAM_PRINTING_MATCH")
        elif len(unspecified_source_rows) == 1:
            upstream_record = unspecified_source_rows[0]
            match_type = "CURATED_CONFIRMS_UNSPECIFIED_UPSTREAM_TREATMENT"
        elif len(unspecified_source_rows) > 1:
            raise ReferenceReconciliationError("AMBIGUOUS_UNSPECIFIED_UPSTREAM_MATCH")

        reference_identity = {
            "version": 1,
            "card_public_id": card_public_id,
            "edition_public_id": edition_public_id,
            "collector_number": entry["collector_number"],
            "normalized_rarity": taxonomy["normalized_rarity"],
            "collector_class": taxonomy["collector_class"],
            "normalized_treatment": taxonomy["normalized_treatment"],
        }
        identity_hash = _fingerprint(reference_identity)
        if upstream_record is not None:
            if upstream_record.uid is None:
                raise ReferenceReconciliationError("MATCHED_UPSTREAM_UID_MISSING")
            used_source_uids[upstream_record.uid] += 1
            matches.append(
                {
                    **entry,
                    "source_sha256": reference["source_sha256"],
                    "worksheet": reference["worksheet"],
                    "card_public_id": card_public_id,
                    "canonical_printed_identifier": printed_identifier,
                    "edition_public_id": edition_public_id,
                    "taxonomy": taxonomy,
                    "number_mapping_note": number_note,
                    "origin": "UPSTREAM_AND_CURATED",
                    "match_type": match_type,
                    "printing_public_id": source_printings[str(upstream_record.uid)],
                    "source_uid": upstream_record.uid,
                }
            )
        else:
            curated.append(
                {
                    **entry,
                    "source_sha256": reference["source_sha256"],
                    "worksheet": reference["worksheet"],
                    "card_public_id": card_public_id,
                    "canonical_printed_identifier": printed_identifier,
                    "edition_public_id": edition_public_id,
                    "taxonomy": taxonomy,
                    "number_mapping_note": number_note,
                    "origin": "CURATED_REFERENCE",
                    "match_type": "NEW_CURATED_PRINTING",
                    "reference_identity": identity_hash,
                    "printing_public_id": "prc_" + identity_hash[:56],
                    "source_uid": None,
                    "source_sku": None,
                }
            )

        # Same number/name/treatment but different source rarity is retained as
        # a conflict rather than merged into the checklist identity.
        if upstream_record is None:
            conflicting_rows = [
                record
                for record in first_edition_rows
                if record.id is not None
                and CanonicalCardKey(TARGET_SET, record.id).analysis_public_id() == card_public_id
                and record.variant
                and _fold(_canonical_treatment(record.variant))
                == _fold(taxonomy["normalized_treatment"])
                and _canonical_rarity(record.rarity or "")
                != (taxonomy["normalized_rarity"] or taxonomy["collector_class"])
            ]
            for record in conflicting_rows:
                conflicts.append(
                    {
                        "reference_key": entry["reference_key"],
                        "collector_number": entry["collector_number"],
                        "collector_rarity": entry["rarity_raw"],
                        "collector_variant": entry["variant_raw"],
                        "source_printing_public_id": CanonicalPrintingKey.from_record(
                            record
                        ).analysis_public_id(),
                        "source_uid": record.uid,
                        "source_rarity": record.rarity,
                        "source_variant": record.variant,
                    }
                )

    if any(count > 1 for count in used_source_uids.values()):
        raise ReferenceReconciliationError("UPSTREAM_PRINTING_REUSED_BY_MULTIPLE_ENTRIES")

    all_upstream_ids = {
        str(record.uid): CanonicalPrintingKey.from_record(record).analysis_public_id()
        for record in first_edition_rows
        if record.uid is not None
    }
    matched_uids = set(used_source_uids)
    source_only = [
        {
            "printing_public_id": all_upstream_ids[str(record.uid)],
            "source_uid": record.uid,
            "collector_number": record.id,
            "rarity": record.rarity,
            "variant": record.variant,
        }
        for record in first_edition_rows
        if record.uid is not None and record.uid not in matched_uids
    ]
    upstream_plan = {
        CanonicalCardKey(TARGET_SET, record.id).analysis_public_id()
        for record in source_records
        if record.id is not None
    }
    checklist_card_ids = {item["card_public_id"] for item in matches + curated}
    if not checklist_card_ids <= upstream_plan:
        raise ReferenceReconciliationError("CHECKLIST_REQUIRES_NEW_CANONICAL_CARD")

    counts = {
        "canonical_card_count": canonical_card_count,
        "upstream_printing_count": upstream_printing_count,
        "curated_reference_entry_count": len(entries),
        "curated_reference_only_printing_count": len(curated),
        "total_collectible_printing_count": upstream_printing_count + len(curated),
        "konoha_1e_checklist_count": len(entries),
        "konoha_1e_canonical_card_count": len(checklist_card_ids),
        "konoha_1e_upstream_overlap_count": len(matches),
        "konoha_1e_source_only_count": len(source_only),
        "konoha_1e_new_curated_count": len(curated),
    }
    return {
        "schema_version": "konoha-shido-reconciliation-v1",
        "reference_source": REFERENCE_SOURCE,
        "workbook_sha256": reference["source_sha256"],
        "counts": counts,
        "matches": sorted(matches, key=lambda item: item["reference_key"]),
        "curated_printings": sorted(curated, key=lambda item: item["reference_key"]),
        "source_only": sorted(source_only, key=lambda item: item["source_uid"]),
        "conflicts": sorted(conflicts, key=lambda item: item["reference_key"]),
        "description_differences": sorted(
            description_differences, key=lambda item: item["reference_key"]
        ),
        "ambiguities": [],
    }
