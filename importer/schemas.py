"""Dedicated normalized importer schema; independent of public API schemas."""

import json
from datetime import date
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Id = Annotated[str, Field(min_length=1, max_length=64)]
Name = Annotated[str, Field(min_length=1, max_length=255)]
Nonnegative = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
SignedPower = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]
Positive = Annotated[int, Field(strict=True, gt=0, le=2147483647)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def trim_optional(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for key, value in data.items():
                if isinstance(value, str):
                    value = value.strip()
                    field = cls.model_fields.get(key)
                    if (
                        not value
                        and field is not None
                        and not field.is_required()
                        and field.default is None
                    ):
                        value = None
                    data[key] = value
        return data


def safe_url(value):
    if value is not None and (value.username or value.password):
        raise ValueError("URL credentials are not permitted")
    return value


class ImportSource(InputModel):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    url: AnyHttpUrl | None = None
    retrieved_at: AwareDatetime
    _url = field_validator("url")(safe_url)


class ImportImage(InputModel):
    url: AnyHttpUrl
    type: Annotated[str, Field(min_length=1, max_length=32)] = "front"
    width: Positive | None = None
    height: Positive | None = None
    source_name: Annotated[str, Field(max_length=128)] | None = None
    source_url: AnyHttpUrl | None = None
    _url = field_validator("url", "source_url")(safe_url)


class ImportKeyword(InputModel):
    slug: Id
    name: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value):
        return value.lower()


class ImportVariant(InputModel):
    id: Id
    type: Id
    finish: Annotated[str, Field(max_length=64)] | None = None
    rarity: Annotated[str, Field(max_length=64)] | None = None
    collector_number: Annotated[str, Field(max_length=32)] | None = None
    language: Annotated[str, Field(min_length=1, max_length=8)] = "EN"
    edition: Annotated[str, Field(max_length=64)] | None = None
    serial_numbered: Annotated[bool, Field(strict=True)] = False
    serial_total: Positive | None = None
    images: list[ImportImage] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_serial(self):
        if not self.serial_numbered and self.serial_total is not None:
            raise ValueError("serial_total requires serial_numbered=true")
        return self


class ImportCard(InputModel):
    id: Id
    number: Annotated[str, Field(min_length=1, max_length=32)]
    name: Name
    subtitle: Annotated[str, Field(max_length=255)] | None = None
    type: Annotated[str, Field(max_length=64)] | None = None
    rarity: Annotated[str, Field(max_length=64)] | None = None
    chakra: Nonnegative | None = None
    power: SignedPower | None = None
    faction: Annotated[str, Field(max_length=64)] | None = None
    ability_text: str | None = None
    flavor_text: str | None = None
    artist: Annotated[str, Field(max_length=255)] | None = None
    # None/omission preserves existing associations; [] explicitly clears them.
    keywords: list[ImportKeyword] | None = None
    variants: list[ImportVariant] = Field(default_factory=list)
    images: list[ImportImage] = Field(default_factory=list)


class ImportSet(InputModel):
    id: Id
    code: Annotated[str, Field(max_length=32)] | None = None
    name: Name
    edition: Annotated[str, Field(max_length=64)] | None = None
    language: Annotated[str, Field(min_length=1, max_length=8)] = "EN"
    release_date: date | None = None
    printed_total: Nonnegative | None = None
    total_with_variants: Nonnegative | None = None
    logo_url: AnyHttpUrl | None = None
    symbol_url: AnyHttpUrl | None = None
    cards: list[ImportCard] = Field(default_factory=list)
    _url = field_validator("logo_url", "symbol_url")(safe_url)


class ImportCatalogue(InputModel):
    source: ImportSource
    # Exact, case-sensitive aliases explicitly supplied by the approved dataset.
    variant_aliases: dict[Id, Id] = Field(default_factory=dict)
    sets: list[ImportSet]

    @model_validator(mode="after")
    def cross_validate(self):
        sets, cards, variants, keywords = set(), set(), set(), {}

        def unique(seen, key, label):
            if key in seen:
                raise ValueError(f"Duplicate {label}: {key}")
            seen.add(key)

        def images(records):
            seen = set()
            for image in records:
                identity = (image.type, str(image.url))
                if identity in seen:
                    raise ValueError("Duplicate image within owner")
                seen.add(identity)

        for target in self.variant_aliases.values():
            if target in self.variant_aliases and self.variant_aliases[target] != target:
                raise ValueError("Variant alias chains/cycles are not permitted")
        for st in self.sets:
            unique(sets, st.id, "set ID")
            numbers = set()
            for card in st.cards:
                unique(cards, card.id, "card ID")
                unique(numbers, card.number, "card number within set")
                local = set()
                for keyword in card.keywords or []:
                    unique(local, keyword.slug, "keyword slug within card")
                    if keyword.slug in keywords and keywords[keyword.slug] != keyword.name:
                        raise ValueError(f"Conflicting keyword definition: {keyword.slug}")
                    keywords[keyword.slug] = keyword.name
                images(card.images)
                for variant in card.variants:
                    unique(variants, variant.id, "variant ID")
                    images(variant.images)
        return self


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def parse_catalogue(raw: str | bytes | dict) -> ImportCatalogue:
    if isinstance(raw, (str, bytes)):
        raw = json.loads(
            raw,
            object_pairs_hook=_unique_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number")),
        )
    return ImportCatalogue.model_validate(raw)
