"""Read-only importer and deterministic dry-run planner for the Phase 13A snapshot.

This module deliberately has no SQLAlchemy/database imports, no network client,
and no artwork resolver. It reads only the local content-addressed acquisition
through the Phase 13B analysis loader, validates every normalized observation
against the Phase 13C domain DTO, and keeps the complete plan in memory.

The CLI emits aggregate report data and a plan hash, never the normalized card
text or image URLs. A caller can use `build_dry_run` in a controlled local
process when the complete in-memory plan is needed for further review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.catalogue_design.identity import CanonicalPrintingKey
from importer.catalogue_design.models import SourceCardRecord
from importer.domain_schemas import LocalizedPrinting, PrintingSchema
from importer.staging.domain import PrintingFingerprint

DEFAULT_ACQUISITION_ROOT = Path("data/acquisition")


class CatalogueImportError(ValueError):
    """A source record cannot be represented without data loss."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _observed_integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise CatalogueImportError("UNSUPPORTED_NUMERIC_REPRESENTATION")


def _fingerprint(record: SourceCardRecord) -> PrintingFingerprint:
    identity = CanonicalPrintingKey.from_record(record)
    payload = identity.payload()
    return PrintingFingerprint.model_validate(
        {key: value for key, value in payload.items() if key not in ("version", "kind")}
    )


def _localized_schema(record: SourceCardRecord, language: str) -> PrintingSchema:
    return PrintingSchema(
        identity=_fingerprint(record),
        card_type=record.card_type,
        chakra=_observed_integer(record.chakra),
        power=_observed_integer(record.power),
        points=_observed_integer(record.points),
        localization=LocalizedPrinting(
            language=language.upper(),
            title=record.title,
            subtitle=record.version,
            rules_text=record.text,
            edition_label=record.edition,
            distribution_text=record.obtain,
            image_url=record.image,
        ),
        source_uid=str(record.uid) if record.uid is not None else None,
        source_sku=record.sku,
        observation=record.raw,
    )


def _source_observation(record: SourceCardRecord, language: str) -> dict[str, Any]:
    """Build deterministic provenance metadata without changing raw values."""
    return {
        "language": language,
        "source_uid": record.uid,
        "source_sku": record.sku,
        "observation": record.raw,
    }


def _validate_card_grouping(records: list[SourceCardRecord]) -> None:
    groups: dict[tuple[str | None, str | None], list[SourceCardRecord]] = defaultdict(list)
    for record in records:
        groups[(record.set, record.id)].append(record)
    for key, members in groups.items():
        card_types = {record.card_type for record in members}
        titles = {record.title for record in members}
        if len(card_types) > 1 or len(titles) > 1:
            raise CatalogueImportError(
                f"CARD_GROUPING_CONFLICT:{key!r}:"
                f"card_types={sorted(str(value) for value in card_types)}:"
                f"titles={sorted(str(value) for value in titles)}"
            )


def _build_plan(
    records_by_language: dict[str, list[SourceCardRecord]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if "en" not in records_by_language:
        raise CatalogueImportError("MISSING_REFERENCE_LANGUAGE:en")

    reference = records_by_language["en"]
    _validate_card_grouping(reference)
    by_uid: dict[str, dict[int, SourceCardRecord]] = {
        language: {record.uid: record for record in records if record.uid is not None}
        for language, records in records_by_language.items()
    }

    cards: dict[str, dict[str, Any]] = {}
    printings: dict[str, dict[str, Any]] = {}
    quarantined: dict[str, str] = {}
    provenance_count = 0
    localization_counts: Counter[str] = Counter()
    card_type_counts: Counter[str] = Counter()
    rarity_counts: Counter[str] = Counter()
    variant_counts: Counter[str] = Counter()
    edition_counts: Counter[str] = Counter()
    negative_power_count = 0
    mission_points_count = 0

    for record in reference:
        record_key = f"uid:{record.uid}"
        try:
            if record.uid is None:
                raise CatalogueImportError("MISSING_SOURCE_UID")
            fingerprint = _fingerprint(record)
            printing_id = fingerprint.key().analysis_public_id()
            card_id = fingerprint.card_key().analysis_public_id()
            if printing_id in printings:
                raise CatalogueImportError("DUPLICATE_SEMANTIC_PRINTING")

            localizations: dict[str, dict[str, Any]] = {}
            source_observations: list[dict[str, Any]] = []
            for language in sorted(records_by_language):
                localized_record = by_uid[language].get(record.uid)
                if localized_record is None:
                    raise CatalogueImportError(f"MISSING_LOCALIZATION:{language}")
                schema = _localized_schema(localized_record, language)
                localizations[language] = schema.localization.model_dump(mode="json")
                source_observations.append(_source_observation(localized_record, language))
                localization_counts[language] += 1

            if card_id not in cards:
                cards[card_id] = {
                    "public_id": card_id,
                    "expansion": record.set,
                    "printed_identifier": record.id,
                    "card_type": record.card_type,
                    "title": record.title,
                    "printing_ids": [],
                }
            cards[card_id]["printing_ids"].append(printing_id)
            printings[printing_id] = {
                "public_id": printing_id,
                "card_id": card_id,
                "identity": fingerprint.model_dump(mode="json"),
                "source_uid": str(record.uid),
                "source_sku": record.sku,
                "localizations": localizations,
                "source_observations": source_observations,
            }
            provenance_count += 1
            card_type_counts[record.card_type or ""] += 1
            rarity_counts[record.rarity or ""] += 1
            variant_counts[record.variant or ""] += 1
            edition_counts[record.edition or ""] += 1
            if record.power == -1:
                negative_power_count += 1
            if record.card_type == "Mission" and record.points not in (None, ""):
                mission_points_count += 1
        except (CatalogueImportError, ValidationError, ValueError) as error:
            quarantined[record_key] = str(error)

    if quarantined:
        raise CatalogueImportError(f"UNEXPLAINED_QUARANTINE:{quarantined}")

    for card in cards.values():
        card["printing_ids"] = sorted(card["printing_ids"])

    plan = {
        "schema_version": "phase14-dry-run-v1",
        "cards": [cards[key] for key in sorted(cards)],
        "printings": [printings[key] for key in sorted(printings)],
    }
    report = {
        "source_records": len(reference),
        "parsed": len(reference),
        "accepted": len(printings),
        "rejected": 0,
        "unexplained_quarantine": 0,
        "unique_cards": len(cards),
        "unique_printings": len(printings),
        "localization_count_by_language": dict(sorted(localization_counts.items())),
        "provenance_count": provenance_count,
        "source_observation_count": sum(
            len(item["source_observations"]) for item in printings.values()
        ),
        "card_type_counts": dict(sorted(card_type_counts.items())),
        "rarity_distribution": dict(sorted(rarity_counts.items())),
        "variant_distribution": dict(sorted(variant_counts.items())),
        "edition_distribution": dict(sorted(edition_counts.items())),
        "negative_power_count": negative_power_count,
        "mission_points_count": mission_points_count,
        "identity_collision_count": 0,
        "quarantined_records": {},
    }
    return plan, report


def build_dry_run(root: Path = DEFAULT_ACQUISITION_ROOT) -> dict[str, Any]:
    """Build the complete 636-record plan in memory from local files only."""
    records_by_language = load_records_from_acquisition(root)
    plan, report = _build_plan(records_by_language)
    report["plan_sha256"] = _sha256_json(plan)
    return {"report": report, "plan": plan}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ACQUISITION_ROOT)
    args = parser.parse_args()
    result = build_dry_run(args.root)
    print(json.dumps(result["report"], ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
