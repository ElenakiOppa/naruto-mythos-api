"""Schema-only domain DTOs. Not accepted by the legacy importer runner."""

from typing import Annotated

from pydantic import Field, JsonValue

from importer.staging.domain import PrintingFingerprint
from importer.staging.models import Language, Model, Nonnegative, SignedPower


class LocalizedPrinting(Model):
    language: Language
    title: Annotated[str, Field(max_length=255)] | None = None
    subtitle: Annotated[str, Field(max_length=255)] | None = None
    rules_text: str | None = None
    edition_label: Annotated[str, Field(max_length=64)] | None = None
    distribution_text: str | None = None
    image_url: str | None = None  # Reference only: no URL resolver/downloader.


class PrintingSchema(Model):
    identity: PrintingFingerprint
    card_type: Annotated[str, Field(max_length=64)] | None
    chakra: Nonnegative | None
    power: SignedPower | None
    points: Nonnegative | None
    localization: LocalizedPrinting
    source_uid: Annotated[str, Field(max_length=255)] | None
    source_sku: Annotated[str, Field(max_length=255)] | None
    # Full observation is provenance, including extra fields not yet interpreted.
    observation: dict[str, JsonValue]
