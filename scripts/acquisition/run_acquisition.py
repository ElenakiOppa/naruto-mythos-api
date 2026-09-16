"""CLI entry point: acquire the Phase 13A approved official sources.

Read-only. Writes raw bytes (content-addressed, immutable) plus an
append-only manifest and one small factual observation record per source.
Never generates identity, never normalizes, never touches the database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.acquisition.fetch import AcquisitionError, fetch
from scripts.acquisition.sources import (
    APPROVED_API_SOURCES,
    APPROVED_DOCUMENT_SOURCES,
    APPROVED_PAGE_SOURCES,
)
from scripts.acquisition.storage import append_manifest_entry, save_raw

DEFAULT_ACQUISITION_ROOT = Path("data/acquisition")


def acquire_one(source, raw_dir: Path, manifest_path: Path, observations_dir: Path) -> dict:
    try:
        result = fetch(source.url, expected_content_types=source.expected_content_types)
    except AcquisitionError as exc:
        entry = {
            "source_url": source.url,
            "source_type": "UNKNOWN",
            "retrieval_timestamp": None,
            "http_status": None,
            "content_type": None,
            "content_length": None,
            "sha256": None,
            "raw_file": None,
            "is_new_content": False,
            "error": f"{type(exc).__name__}: {exc}",
            "notes": source.notes,
        }
        append_manifest_entry(manifest_path, entry)
        return entry

    raw_path, is_new = save_raw(raw_dir, result.sha256, result.content_type, result.body)
    source_type = _classify_source_type(result.content_type)
    entry = {
        "source_url": source.url,
        "final_url": result.final_url,
        "source_type": source_type,
        "retrieval_timestamp": result.retrieved_at,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "content_length": result.content_length,
        "sha256": result.sha256,
        "raw_file": str(raw_path.as_posix()),
        "is_new_content": is_new,
        "redirect_chain": list(result.redirect_chain),
        "notes": source.notes,
    }
    append_manifest_entry(manifest_path, entry)

    observations_dir.mkdir(parents=True, exist_ok=True)
    observation_path = observations_dir / f"{result.sha256}.json"
    if not observation_path.exists():
        observation_path.write_text(
            json.dumps(
                {
                    "source_url": source.url,
                    "sha256": result.sha256,
                    "retrieval_timestamp": result.retrieved_at,
                    "source_type": source_type,
                    "notes": source.notes,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return entry


def _classify_source_type(content_type: str | None) -> str:
    if not content_type:
        return "OTHER"
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized == "text/html":
        return "HTML_PAGE"
    if normalized in ("application/pdf", "application/octet-stream"):
        return "PDF_GUIDE"
    if normalized == "application/json":
        return "API_RESPONSE"
    return "OTHER"


def main(root: Path = DEFAULT_ACQUISITION_ROOT) -> list[dict]:
    raw_dir = root / "raw"
    manifest_path = root / "manifest.json"
    observations_dir = root / "observations"

    results = []
    for source in (*APPROVED_PAGE_SOURCES, *APPROVED_DOCUMENT_SOURCES, *APPROVED_API_SOURCES):
        results.append(acquire_one(source, raw_dir, manifest_path, observations_dir))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ACQUISITION_ROOT)
    args = parser.parse_args()
    entries = main(args.root)
    for entry in entries:
        status = entry.get("http_status")
        error = entry.get("error")
        print(
            f"{entry['source_url']} -> status={status} sha256={entry.get('sha256')} error={error}"
        )
