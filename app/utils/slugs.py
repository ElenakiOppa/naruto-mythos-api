"""Derived presentation slugs, never database identities."""

import re


def rarity_slug(name: str) -> str:
    # Preserve Unicode letters/digits, collapse all other characters as separators.
    # Punctuation-only input produces an empty presentation slug; names stay separate.
    return re.sub(
        r"-+", "-", "".join(c if c.isalnum() else "-" for c in name.strip().lower())
    ).strip("-")
