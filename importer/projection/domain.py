"""Version 2 sparse projection preview. No legacy plan/approval conversion or writer."""

from typing import Literal

from importer.projection.canonical import digest
from importer.projection.models import Patch
from importer.staging.domain import PrintingRecord, validate_printings
from importer.staging.models import Model


class DomainProjection(Model):
    input_hash: str
    identities: dict[str, str]
    patches: dict[str, dict[str, Patch]]
    rejected: dict[str, list[str]]
    production_execution_authorized: Literal[False] = False


def project_printings(records: list[PrintingRecord]) -> DomainProjection:
    records = [PrintingRecord.model_validate(r.model_dump()) for r in records]
    checked = validate_printings(records)
    return DomainProjection(
        input_hash=digest([r.model_dump(mode="json") for r in records]),
        identities=checked.accepted,
        patches={
            r.record_key: {
                name: Patch.model_validate(getattr(r, name).model_dump())
                for name in ("title", "rules_text", "card_type", "chakra", "power", "points")
            }
            for r in records
            if r.record_key in checked.accepted
        },
        rejected=checked.quarantined,
    )
