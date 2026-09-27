"""Reconcile official Edition source snapshots with existing Printings.

Default behavior is a read-only dry run from the content-addressed acquisition.
Use --refresh-source to append a fresh gallery-proxy snapshot. Use --persist
only after the live database is independently identified and migrated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from importer.catalogue_design.analyzer import load_records_from_acquisition
from importer.official_edition_reference import (
    EXPECTED_OFFICIAL_EDITIONS,
    build_official_edition_reconciliation,
    persist_official_edition_reconciliation,
)
from scripts.acquisition.run_acquisition import acquire_one
from scripts.acquisition.sources import APPROVED_API_SOURCES

DEFAULT_ROOT = Path("data/acquisition")
EXPECTED_REVISION = "g13c20260927"


def _snapshot_provenance(root: Path) -> tuple[str, datetime, dict[str, str]]:
    entries = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        canonical_url = entry.get("canonical_source_url") or entry.get("source_url", "")
        if "cards.narutotcgmythos.com/api/cards" not in canonical_url:
            continue
        language = parse_qs(urlsplit(canonical_url).query).get("lang", [""])[-1]
        if language in {"en", "fr", "it", "es"} and entry.get("sha256"):
            latest[language] = entry
    if set(latest) != {"en", "fr", "it", "es"}:
        raise ValueError("OFFICIAL_LANGUAGE_SNAPSHOT_INCOMPLETE")
    hashes = {language: latest[language]["sha256"] for language in sorted(latest)}
    retrieved = [datetime.fromisoformat(entry["retrieval_timestamp"]) for entry in latest.values()]
    canonical_sources = {
        (entry.get("canonical_source_url") or entry.get("source_url", "")).split("?", 1)[0]
        for entry in latest.values()
    }
    transport_sources = {entry.get("source_url", "").split("?", 1)[0] for entry in latest.values()}
    if len(canonical_sources) != 1 or len(transport_sources) != 1:
        raise ValueError("OFFICIAL_SOURCE_URL_INCONSISTENT")
    digest_payload = {
        "canonical_source": next(iter(canonical_sources)),
        "transport_source": next(iter(transport_sources)),
        "language_snapshot_hashes": hashes,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest, max(retrieved), hashes


def refresh_official_source(root: Path = DEFAULT_ROOT) -> None:
    raw_dir = root / "raw"
    manifest_path = root / "manifest.json"
    observations_dir = root / "observations"
    for source in APPROVED_API_SOURCES:
        entry = acquire_one(source, raw_dir, manifest_path, observations_dir)
        if entry.get("http_status") != 200 or not entry.get("sha256") or entry.get("error"):
            raise RuntimeError("OFFICIAL_GALLERY_SOURCE_ACQUISITION_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--refresh-source",
        action="store_true",
        help="Fetch the four official gallery API locales and append content-addressed snapshots.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist reference rows after read-only reconciliation; never creates or changes Printings.",
    )
    parser.add_argument(
        "--allow-nonproduction",
        action="store_true",
        help="Permit --persist when APP_ENV is not production (for isolated staging only).",
    )
    args = parser.parse_args()

    if args.refresh_source:
        refresh_official_source(args.root)
    records = load_records_from_acquisition(args.root)
    snapshot_hash, retrieved_at, language_hashes = _snapshot_provenance(args.root)

    if args.persist:
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        from app.config import get_settings
        from app.database import engine

        settings = get_settings()
        if not settings.is_production and not args.allow_nonproduction:
            parser.error(
                "--persist requires APP_ENV=production unless --allow-nonproduction is supplied"
            )
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if revision != EXPECTED_REVISION:
            parser.error("Database migration head does not match the official collector schema")
        with Session(engine) as session:
            reconciliations = []
            for (set_name, edition_name), expected in EXPECTED_OFFICIAL_EDITIONS.items():
                reconciliation = build_official_edition_reconciliation(
                    session,
                    records,
                    set_name=set_name,
                    edition_name=edition_name,
                    source_snapshot_sha256=snapshot_hash,
                    retrieved_at=retrieved_at,
                )
                if reconciliation["expected_printing_count"] != expected:
                    parser.error("OFFICIAL_EXPECTED_COUNT_POLICY_MISMATCH")
                counts = reconciliation["counts"]
                if (
                    counts["matched_existing_printings"] != expected
                    or counts["official_only"]
                    or counts["database_only"]
                    or counts["identity_conflicts"]
                    or counts["duplicate_semantic_identities"]
                ):
                    parser.error("OFFICIAL_EDITION_RECONCILIATION_INCOMPLETE")
                reconciliations.append(reconciliation)
            outputs = []
            for reconciliation in reconciliations:
                set_name = reconciliation["set_name"]
                edition_name = reconciliation["edition_name"]
                expected = reconciliation["expected_printing_count"]
                verification = persist_official_edition_reconciliation(session, reconciliation)
                outputs.append(
                    {
                        "set": set_name,
                        "edition": edition_name,
                        "counts": reconciliation["counts"],
                        "verified": verification.verified,
                        "reference_count": verification.reference_count,
                    }
                )
    else:
        outputs = []
        for (set_name, edition_name), expected in EXPECTED_OFFICIAL_EDITIONS.items():
            output = {
                "set": set_name,
                "edition": edition_name,
                "expected_count": expected,
                "official_source_count": sum(
                    record.set == set_name and (record.edition or "").strip() == edition_name
                    for record in records["en"]
                ),
            }
            outputs.append(output)

    print(
        json.dumps(
            {
                "source_type": "OFFICIAL_GALLERY_API",
                "canonical_source": "https://cards.narutotcgmythos.com/api/cards",
                "transport_source": "https://services.agenziamarketingcarpi.it/proxy/naruto/proxy.php",
                "source_snapshot_sha256": snapshot_hash,
                "language_snapshot_hashes": language_hashes,
                "retrieved_at": retrieved_at.isoformat(),
                "persisted": bool(args.persist),
                "editions": outputs,
            },
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
