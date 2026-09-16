"""Version 1 staging contract. Unknown values never imply permission or deletion."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Blank text is not permitted")
    return value


Text = Annotated[str, Field(strict=True, min_length=1, max_length=4096), AfterValidator(nonblank)]
Key = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
PublicID = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Namespace = Annotated[str, Field(strict=True, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
Language = Annotated[str, Field(strict=True, pattern=r"^[A-Z]{2,3}(-[A-Za-z0-9]{2,8})*$")]
Number = Annotated[str, Field(strict=True, min_length=1, max_length=128)]
Nonnegative = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
SignedPower = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]
Positive = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
T = TypeVar("T")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Authority(StrEnum):
    OFFICIAL_AUTHORITATIVE = "OFFICIAL_AUTHORITATIVE"
    OFFICIAL_INCOMPLETE = "OFFICIAL_INCOMPLETE"
    THIRD_PARTY_REFERENCE = "THIRD_PARTY_REFERENCE"
    UNSUITABLE = "UNSUITABLE"


class RightsState(StrEnum):
    UNKNOWN = "UNKNOWN"
    PERMITTED = "PERMITTED"
    RESTRICTED = "RESTRICTED"
    EXCLUDED = "EXCLUDED"


class SafeURL(Model):
    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def no_url_credentials(cls, value):
        if isinstance(value, AnyHttpUrl) and (value.username or value.password):
            raise ValueError("Credential-bearing URLs are not permitted")
        return value


class Source(SafeURL):
    name: Text
    url: AnyHttpUrl | None = None
    retrieved_at: AwareDatetime
    revision: Text | None = None
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    authority: Authority


class Rights(Model):
    metadata: RightsState = RightsState.UNKNOWN
    text: RightsState = RightsState.UNKNOWN
    images: RightsState = RightsState.UNKNOWN
    permission_reference: Text | None = None


class State(StrEnum):
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    VALUE = "VALUE"
    CLEAR = "CLEAR"


class FieldValue(Model, Generic[T]):  # noqa: UP046 -- supports the declared Pydantic 2.7 minimum
    """Explicit operations; CLEAR needs a review reference, never inferred from null."""

    state: State = State.ABSENT
    value: T | None = None
    approval_reference: Text | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (self.state == State.VALUE) != (self.value is not None):
            raise ValueError("Only VALUE carries a non-null value")
        if self.state == State.CLEAR:
            if self.approval_reference is None or not self.approval_reference.strip():
                raise ValueError("CLEAR requires an explicit approval reference")
        elif self.approval_reference is not None:
            raise ValueError("Approval reference is only valid for CLEAR")
        return self


class CardFields(Model):
    name: FieldValue[Text] = Field(default_factory=FieldValue)
    subtitle: FieldValue[Text] = Field(default_factory=FieldValue)
    type: FieldValue[Text] = Field(default_factory=FieldValue)
    chakra: FieldValue[Nonnegative] = Field(default_factory=FieldValue)
    power: FieldValue[SignedPower] = Field(default_factory=FieldValue)
    faction: FieldValue[Text] = Field(default_factory=FieldValue)
    ability_text: FieldValue[Text] = Field(default_factory=FieldValue)
    flavor_text: FieldValue[Text] = Field(default_factory=FieldValue)
    artist: FieldValue[Text] = Field(default_factory=FieldValue)
    mission_points: FieldValue[Nonnegative] = Field(default_factory=FieldValue)
    mission_rank: FieldValue[Text] = Field(default_factory=FieldValue)

    @field_validator("*", mode="before")
    @classmethod
    def explicit_null_is_unknown(cls, value):
        return {"state": "UNKNOWN"} if value is None else value

    @model_validator(mode="after")
    def protect_required_name(self):
        if self.name.state == State.CLEAR:
            raise ValueError("Card name cannot be cleared")
        return self

    @property
    def present_fields(self) -> list[str]:
        return [k for k in type(self).model_fields if getattr(self, k).state != State.ABSENT]

    @property
    def explicit_clear_fields(self) -> list[str]:
        return [k for k in type(self).model_fields if getattr(self, k).state == State.CLEAR]


class Scope(Model):
    expansion: Key | None = None
    edition: Key | None = None
    language: Language | None = None
    territory: Key | None = None


class PrintingIdentity(Model):
    scope: Scope = Field(default_factory=Scope)
    numbering_namespace: Namespace | None = None
    printed_identifier: Number | None = None

    @field_validator("printed_identifier")
    @classmethod
    def preserve_number(cls, value):
        if value is not None and (value != value.strip() or not value.strip()):
            raise ValueError("Printed identifier must not have surrounding whitespace")
        return value


class Evidence(SafeURL):
    source_url: AnyHttpUrl | None = None
    locator: Text
    original_value: Text | None = None
    note: Text | None = None


class Treatment(Model):
    parent_record_key: Key | None = None
    equivalence: Literal["UNKNOWN", "VERIFIED"] = "UNKNOWN"
    evidence_reference: Key | None = None
    treatment_key: Key | None = None
    finish_key: Key | None = None
    collector_number: Number | None = None
    serial_numbered: StrictBool | None = None
    serial_total: Positive | None = None

    @field_validator("collector_number")
    @classmethod
    def preserve_number(cls, value):
        return PrintingIdentity.preserve_number(value)

    @model_validator(mode="after")
    def serialization(self):
        if self.serial_total is not None and self.serial_numbered is not True:
            raise ValueError("Known serial_total requires serial_numbered=true")
        return self


class Rarity(Model):
    official_label: FieldValue[Text] = Field(default_factory=FieldValue)
    abbreviation: FieldValue[Text] = Field(default_factory=FieldValue)
    normalized_key: FieldValue[Key] = Field(default_factory=FieldValue)

    @field_validator("*", mode="before")
    @classmethod
    def explicit_null_is_unknown(cls, value):
        return {"state": "UNKNOWN"} if value is None else value


class Keyword(Model):
    key: Key
    label: Text


class Image(SafeURL):
    url: AnyHttpUrl
    owner: Literal["PRINTING", "TREATMENT"]
    type: Key
    source_url: AnyHttpUrl | None = None
    width: Positive | None = None
    height: Positive | None = None


class Availability(Model):
    channel: Key
    territory: Key | None = None
    status: Literal["UNKNOWN", "ANNOUNCED", "RELEASED"] = "UNKNOWN"
    release_date: date | None = None


class Record(Model):
    schema_version: Literal["1"] = "1"
    record_key: Key
    kind: Literal["PRINTING", "TREATMENT"] = "PRINTING"
    source: Source
    rights: Rights = Field(default_factory=Rights)
    identity: PrintingIdentity = Field(default_factory=PrintingIdentity)
    expansion_label: Text | None = None
    edition_label: Text | None = None
    card: CardFields = Field(default_factory=CardFields)
    treatment: Treatment | None = None
    rarity: Rarity = Field(default_factory=Rarity)
    keywords: FieldValue[list[Keyword]] = Field(default_factory=FieldValue)
    images: FieldValue[list[Image]] = Field(default_factory=FieldValue)
    availability: FieldValue[list[Availability]] = Field(default_factory=FieldValue)
    field_evidence: dict[Key, Evidence] = Field(default_factory=dict)
    unresolved_questions: list[Text] = Field(default_factory=list)
    review_status: Literal["UNREVIEWED", "APPROVED", "REJECTED"] = "UNREVIEWED"
    existing_public_id: PublicID | None = None

    @field_validator("keywords", "images", "availability", mode="before")
    @classmethod
    def explicit_null_is_unknown(cls, value):
        return {"state": "UNKNOWN"} if value is None else value

    @model_validator(mode="after")
    def correct_kind(self):
        if (self.kind == "TREATMENT") != (self.treatment is not None):
            raise ValueError("Only TREATMENT records must carry treatment metadata")
        return self


class Policy(Model):
    """Explicitly approved combinations, never an inferred edition/language cross-product."""

    approved_scopes: list[Scope]
    namespaces: list[Namespace] = Field(
        default_factory=lambda: ["STANDARD", "MISSION", "PROMO", "SPECIAL"]
    )
    treatment_keys: list[Key] = Field(default_factory=list)
    finish_keys: list[Key] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete_scopes(self):
        if any(
            s.expansion is None or s.edition is None or s.language is None
            for s in self.approved_scopes
        ):
            raise ValueError("Approved scopes must specify expansion, edition and language")
        return self
