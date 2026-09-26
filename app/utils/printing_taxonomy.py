"""Evidence-backed normalization for raw collectible Printing labels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedPrintingTaxonomy:
    normalized_rarity: str | None
    collector_class: str | None
    rarity_resolution_status: str
    normalized_treatment: str | None
    variant_resolution_status: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "normalized_rarity": self.normalized_rarity,
            "collector_class": self.collector_class,
            "rarity_resolution_status": self.rarity_resolution_status,
            "normalized_treatment": self.normalized_treatment,
            "variant_resolution_status": self.variant_resolution_status,
        }


RARITY_LABELS = {
    "C": "Common",
    "Common": "Common",
    "UC": "Uncommon",
    "Uncommon": "Uncommon",
    "R": "Rare",
    "Rare": "Rare",
    "RA": "Rare ART",
    "Rare ART": "Rare ART",
    "S": "Secret",
    "Secret": "Secret",
    "SV": "Secret Variant",
    "Secret Variant": "Secret Variant",
    "L": "Legendary",
    "Legendary": "Legendary",
    "M": "Mythos",
    "Mythos": "Mythos",
}

TREATMENT_LABELS = {
    "Normal": "Normal",
    "Full Art": "FullArt",
    "FullArt": "FullArt",
    "Holo": "Holographic",
    "Holographic": "Holographic",
    "Gold": "Gold",
}


def normalize_printing_taxonomy(
    raw_rarity: str | None,
    raw_variant: str | None,
    card_type: str | None,
) -> NormalizedPrintingTaxonomy:
    """Map only reviewed labels; preserve unknown meaning as unresolved status."""
    normalized_rarity = RARITY_LABELS.get(raw_rarity) if raw_rarity is not None else None
    collector_class = None
    if normalized_rarity is not None:
        rarity_status = "MAPPED"
    elif raw_rarity == "Mission" and card_type == "Mission":
        rarity_status = "MAPPED"
        collector_class = "Mission"
    else:
        rarity_status = "UNRESOLVED"

    if raw_variant is None or raw_variant == "":
        normalized_treatment = None
        variant_status = "UNSPECIFIED"
    else:
        normalized_treatment = TREATMENT_LABELS.get(raw_variant)
        variant_status = "MAPPED" if normalized_treatment is not None else "UNRESOLVED"

    return NormalizedPrintingTaxonomy(
        normalized_rarity=normalized_rarity,
        collector_class=collector_class,
        rarity_resolution_status=rarity_status,
        normalized_treatment=normalized_treatment,
        variant_resolution_status=variant_status,
    )
