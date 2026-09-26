"""Canonical, non-fuzzy Edition label normalization shared by domain and import code."""

import unicodedata


def normalize_edition_name(value: str) -> str:
    """Normalize NFC, whitespace, and case without ordinal or fuzzy matching."""
    return " ".join(unicodedata.normalize("NFC", value).split()).lower()


def display_edition_name(value: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFC", value).split())
    normalized = normalize_edition_name(cleaned)
    return {
        "1st edition": "1st Edition",
        "2nd edition": "2nd Edition",
    }.get(normalized, cleaned)
