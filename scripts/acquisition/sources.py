"""Approved Phase 13A source URL inventory (read-only, discovery only).

These are the official pages named in the Phase 13A brief plus the
first-party PDF documents (collection guides, rulebook) that the official
pages directly link to. Card artwork image URLs are intentionally NOT
included here: this phase records artwork references as text, it never
downloads them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovedSource:
    url: str
    expected_content_types: tuple[str, ...]
    notes: str


# Direct first-party card API discovered via page-embedded JavaScript
# (cards.narutotcgmythos.com/api/cards). Same official domain as the public
# Card Gallery, called naturally by that page's own client-side code (via a
# third-party proxy for CORS/token hiding); responds without authentication
# when called directly. This is the site's own data source for the exact
# public gallery content, not a private/internal endpoint.
APPROVED_API_SOURCES: tuple[ApprovedSource, ...] = tuple(
    ApprovedSource(
        f"https://cards.narutotcgmythos.com/api/cards?lang={lang}",
        ("application/json",),
        f"Direct card-data API response, lang={lang} (discovered in card-gallery page JS).",
    )
    for lang in ("en", "fr", "it", "es")
)

APPROVED_PAGE_SOURCES: tuple[ApprovedSource, ...] = (
    ApprovedSource(
        "https://www.narutotcgmythos.com/",
        ("text/html",),
        "Official homepage.",
    ),
    ApprovedSource(
        "https://www.narutotcgmythos.com/collection-guide",
        ("text/html",),
        "Rarity breakdown and collection guide download links.",
    ),
    ApprovedSource(
        "https://www.narutotcgmythos.com/card-gallery",
        ("text/html",),
        "Public card gallery; previously reported under maintenance.",
    ),
    ApprovedSource(
        "https://www.narutotcgmythos.com/set-1-konoha-shido",
        ("text/html",),
        "Set 1: Konoha Shido official page.",
    ),
    ApprovedSource(
        "https://www.narutotcgmythos.com/set-2--shinobi-shiren",
        ("text/html",),
        "Set 2: Shinobi Shiren official page.",
    ),
    ApprovedSource(
        "https://www.narutotcgmythos.com/products",
        ("text/html",),
        "Products page; mentions Set 3 Akatsuki as coming soon.",
    ),
)

# First-party downloadable documents directly linked from the collection-guide
# and homepage pages above (hosted on the site's document/asset CDN).
APPROVED_DOCUMENT_SOURCES: tuple[ApprovedSource, ...] = (
    ApprovedSource(
        "https://irp.cdn-website.com/99e556bf/files/uploaded/Naruto_TCG_Collection_Guide_EN.pdf",
        ("application/pdf", "application/octet-stream"),
        "Collection guide: Set 1 Konoha Shido, 1st edition.",
    ),
    ApprovedSource(
        "https://irp.cdn-website.com/99e556bf/files/uploaded/Naruto_TCG_Collection_guide_EN_v2-a83b0a03.pdf",
        ("application/pdf", "application/octet-stream"),
        "Collection guide: Set 1 Konoha Shido, 2nd edition.",
    ),
    ApprovedSource(
        "https://irp.cdn-website.com/99e556bf/files/uploaded/Collection+guide+Shinobi+Shiren+EN.pdf",
        ("application/pdf", "application/octet-stream"),
        "Collection guide: Set 2 Shinobi Shiren, 1st edition.",
    ),
    ApprovedSource(
        "https://irp.cdn-website.com/99e556bf/files/uploaded/Naruto-Mythos-TCG-Rulebook-EN.pdf",
        ("application/pdf", "application/octet-stream"),
        "Official rulebook PDF (gameplay rules, not catalogue data).",
    ),
)
