"""Read-only statistical audit of acquired card API responses (Phase 13A).

Computes raw factual counts and value-frequency distributions from the
already-downloaded `cards.narutotcgmythos.com/api/cards` JSON responses.
This performs NO normalization and generates NO identity: it only counts
and groups the raw values exactly as the source API returned them.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("data/acquisition")


def _load_manifest(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _cards_by_lang(root: Path) -> dict[str, list[dict[str, Any]]]:
    entries = _load_manifest(root)
    cards_by_lang: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        url = entry.get("source_url", "")
        if "cards.narutotcgmythos.com/api/cards" not in url or entry.get("sha256") is None:
            continue
        lang = url.rsplit("lang=", 1)[-1]
        raw_file = Path(entry["raw_file"])
        payload = json.loads(raw_file.read_text(encoding="utf-8"))
        cards = payload[0]["Cards"] if payload and "Cards" in payload[0] else []
        cards_by_lang[lang] = cards
    return cards_by_lang


def _counter_to_dict(counter: collections.Counter) -> dict[str, int]:
    return {str(key): count for key, count in counter.most_common()}


def build_audit(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    by_lang = _cards_by_lang(root)
    audit: dict[str, Any] = {
        "record_counts_by_lang": {lang: len(cards) for lang, cards in by_lang.items()}
    }

    if "en" not in by_lang:
        return audit
    en_cards = by_lang["en"]

    keys: set[str] = set()
    for card in en_cards:
        keys.update(card.keys())
    presence: collections.Counter[str] = collections.Counter()
    for card in en_cards:
        for key in keys:
            if card.get(key) not in (None, ""):
                presence[key] += 1

    id_to_uids: dict[str, set[Any]] = collections.defaultdict(set)
    for card in en_cards:
        id_to_uids[str(card.get("ID"))].add(card.get("Uid"))
    collision_ids = {k: sorted(v, key=str) for k, v in id_to_uids.items() if len(v) > 1}

    uids = [card.get("Uid") for card in en_cards]

    audit.update(
        {
            "field_presence_en": {k: f"{presence[k]}/{len(en_cards)}" for k in sorted(keys) if k},
            "rarity_distribution_en": _counter_to_dict(
                collections.Counter(c.get("Rarity") for c in en_cards)
            ),
            "cardtype_distribution_en": _counter_to_dict(
                collections.Counter(c.get("CardType") for c in en_cards)
            ),
            "variant_distribution_en": _counter_to_dict(
                collections.Counter(c.get("Variant") for c in en_cards)
            ),
            "stamp_distribution_en": _counter_to_dict(
                collections.Counter(c.get("Stamp") for c in en_cards)
            ),
            "edition_distribution_en": _counter_to_dict(
                collections.Counter(c.get("Edition") for c in en_cards)
            ),
            "set_distribution_en": _counter_to_dict(
                collections.Counter(c.get("Set") for c in en_cards)
            ),
            "set_edition_crosstab_en": _counter_to_dict(
                collections.Counter(f"{c.get('Set')} | {c.get('Edition')}" for c in en_cards)
            ),
            "set_rarity_crosstab_en": _counter_to_dict(
                collections.Counter(f"{c.get('Set')} | {c.get('Rarity')}" for c in en_cards)
            ),
            "uid_total": len(uids),
            "uid_unique": len(set(uids)),
            "id_unique_count": len(id_to_uids),
            "id_collision_count": len(collision_ids),
            "id_non_numeric_sample": sorted(
                {str(c.get("ID")) for c in en_cards if not re.fullmatch(r"\d+", str(c.get("ID")))}
            )[:40],
        }
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    audit = build_audit(args.root)
    out_path = args.root / "card_data_audit.json"
    out_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
