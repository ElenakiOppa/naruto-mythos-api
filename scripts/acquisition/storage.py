"""Content-addressed, immutable raw storage and append-only manifest for Phase 13A.

Raw bytes are never overwritten. A repeated fetch of a URL whose content is
unchanged reuses the existing content-addressed file; changed content is
stored under its own new hash. The manifest is append-only: every fetch
attempt gets its own entry, so history of observations is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_EXTENSION_BY_CONTENT_TYPE = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/plain": ".txt",
}


def extension_for_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    normalized = content_type.split(";", 1)[0].strip().lower()
    return _EXTENSION_BY_CONTENT_TYPE.get(normalized, ".bin")


def raw_path_for(raw_dir: Path, sha256: str, content_type: str | None) -> Path:
    return raw_dir / f"{sha256}{extension_for_content_type(content_type)}"


def save_raw(
    raw_dir: Path, sha256: str, content_type: str | None, body: bytes
) -> tuple[Path, bool]:
    """Persist raw bytes under a content-addressed, immutable filename.

    Returns (path, is_new). Never overwrites an existing file for the same hash.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_path_for(raw_dir, sha256, content_type)
    if path.exists():
        return path, False
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(body)
    tmp_path.replace(path)
    return path, True


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def append_manifest_entry(manifest_path: Path, entry: dict[str, Any]) -> None:
    """Append one immutable observation entry; never rewrites prior entries' content."""
    entries = load_manifest(manifest_path)
    entries.append(entry)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")


REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "source_url",
        "source_type",
        "retrieval_timestamp",
        "http_status",
        "content_type",
        "content_length",
        "sha256",
        "raw_file",
        "is_new_content",
    }
)


def validate_manifest_entry(entry: dict[str, Any]) -> list[str]:
    """Return a list of validation problems (empty list means valid)."""
    problems = []
    missing = REQUIRED_MANIFEST_FIELDS - entry.keys()
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    return problems
