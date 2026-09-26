"""Validate the curated Konoha Shido checklist against local source data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from importer.reference_catalogue import (
    DEFAULT_REFERENCE_PATH,
    build_reference_reconciliation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_PATH)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = build_reference_reconciliation(args.reference)
    output = {
        "counts": result["counts"],
        "conflict_count": len(result["conflicts"]),
        "ambiguity_count": len(result["ambiguities"]),
        "description_difference_count": len(result["description_differences"]),
    }
    if args.details:
        output.update(
            {
                "conflicts": result["conflicts"],
                "ambiguities": result["ambiguities"],
                "source_only": result["source_only"],
                "description_differences": result["description_differences"],
            }
        )
    print(json.dumps(output, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if not result["ambiguities"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
