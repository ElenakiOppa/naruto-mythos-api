"""CLI: run the Phase 13B analysis-only pipeline against the local Phase 13A acquisition.

Prints an aggregate summary only (no bulk card text/catalogue is written out).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import (
    audit_sku,
    audit_uid,
    card_grouping_report,
    collision_key_progression,
    language_invariance_check,
    load_records_from_acquisition,
    map_all_records,
    round_trip_ok,
)


def main(root: Path) -> None:
    by_lang = load_records_from_acquisition(root)
    print("languages loaded:", {lang: len(recs) for lang, recs in by_lang.items()})
    en = by_lang["en"]

    uid_result = audit_uid(en)
    print("\n=== UID AUDIT ===")
    print(uid_result)

    sku_result = audit_sku(en)
    print("\n=== SKU AUDIT ===")
    print(sku_result)

    print("\n=== COLLISION KEY PROGRESSION ===")
    for r in collision_key_progression(en):
        print(r)

    print("\n=== CARD GROUPING ===")
    grouping = card_grouping_report(en)
    print(
        "groups:",
        grouping.group_count,
        "multi-printing groups:",
        grouping.groups_with_multiple_printings,
        "invariant:",
        grouping.title_cardtype_invariant_groups,
        "mismatched:",
        len(grouping.mismatched_groups),
        "max per card:",
        grouping.max_printings_per_card,
    )

    print("\n=== MAPPING (all records) ===")
    summary = map_all_records(en)
    print(
        "total",
        summary.total,
        "mapped",
        summary.mapped,
        "ambiguous",
        summary.ambiguous,
        "rejected",
        summary.rejected,
    )

    print("\n=== ROUND-TRIP CHECK ===")
    by_uid = {r.uid: r for r in en}
    ok = sum(
        1
        for m in summary.results
        if m.state.value == "MAPPED" and round_trip_ok(by_uid[m.record_uid], m)
    )
    mapped_count = sum(1 for m in summary.results if m.state.value == "MAPPED")
    print(f"round-trip ok: {ok}/{mapped_count}")

    print("\n=== LANGUAGE INVARIANCE ===")
    checked, mismatches = language_invariance_check(by_lang)
    print("checked pairs:", checked, "mismatches:", len(mismatches))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/acquisition"))
    args = parser.parse_args()
    main(args.root)
