"""Read-only schema compatibility audit of an existing local acquisition.

No database/application imports, network, output files, IDs persisted or writer calls.
Raw observations are retained verbatim in memory; output contains counts/reasons only.
"""

from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from importer.catalogue_design.analyzer import load_records_from_acquisition, map_all_records
from importer.catalogue_design.identity import CanonicalPrintingKey
from importer.catalogue_design.models import SourceCardRecord
from importer.domain_schemas import LocalizedPrinting, PrintingSchema
from importer.staging.domain import PrintingFingerprint


def observed_integer(value):
    """Explicit source-to-typed mapping, never a mutation of the raw observation.

    The source uses empty strings for absent stats and decimal strings for Points.
    Preserve both forms in observation; reject every other non-integer representation.
    Signed source integers are retained exactly. No default/clamp/sentinel conversion.
    """
    if value is None or value == "":
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError("UNSUPPORTED_NUMERIC_REPRESENTATION")


def schema_record(record: SourceCardRecord, language: str) -> PrintingSchema:
    identity = CanonicalPrintingKey.from_record(record)
    return PrintingSchema(
        identity=PrintingFingerprint(
            **{k: v for k, v in identity.payload().items() if k not in ("version", "kind")}
        ),
        card_type=record.card_type,
        chakra=observed_integer(record.chakra),
        power=observed_integer(record.power),
        points=observed_integer(record.points),
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


def check_records(records: list[SourceCardRecord], language: str = "EN") -> dict:
    mapping = map_all_records(records)
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for record, result in zip(records, mapping.results, strict=True):
        try:
            if result.state.value != "MAPPED":
                raise ValueError("IDENTITY_NOT_MAPPED")
            projected = schema_record(record, language)
            if projected.observation != record.raw:
                raise ValueError("RAW_OBSERVATION_CHANGED")
            if projected.identity.key().analysis_public_id() != result.canonical_public_id:
                raise ValueError("IDENTITY_CHANGED")
            counts["SCHEMA_COMPATIBLE"] += 1
        except (ValidationError, ValueError) as error:
            counts["SCHEMA_INCOMPATIBLE_WITH_REASON"] += 1
            if isinstance(error, ValidationError):
                for e in error.errors():
                    reasons[".".join(map(str, e["loc"])) + ":" + e["type"]] += 1
            else:
                reasons[str(error)] += 1
    return {
        "records": len(records),
        "SCHEMA_COMPATIBLE": counts["SCHEMA_COMPATIBLE"],
        "SCHEMA_INCOMPATIBLE_WITH_REASON": counts["SCHEMA_INCOMPATIBLE_WITH_REASON"],
        "reasons": dict(sorted(reasons.items())),
    }


if __name__ == "__main__":
    import json

    by_language = load_records_from_acquisition(Path("data/acquisition"))
    reports = {
        language: check_records(records, language) for language, records in by_language.items()
    }
    print(json.dumps(reports, sort_keys=True))
    raise SystemExit(
        1 if any(r["SCHEMA_INCOMPATIBLE_WITH_REASON"] for r in reports.values()) else 0
    )
