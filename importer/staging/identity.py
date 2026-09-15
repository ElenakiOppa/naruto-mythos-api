"""Versioned, database-free identities and collision-checked public-ID proposals."""

import hashlib
import json
import unicodedata
from collections.abc import Mapping

from .models import PrintingIdentity, Treatment


def canonical(value: dict) -> str:
    # NFC only: no case folding, punctuation removal, whitespace collapse or integer coercion.
    return unicodedata.normalize(
        "NFC", json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def printing_identity(identity: PrintingIdentity) -> str:
    scope = identity.scope
    if any(
        v is None
        for v in (
            scope.expansion,
            scope.edition,
            scope.language,
            identity.numbering_namespace,
            identity.printed_identifier,
        )
    ):
        raise ValueError("Incomplete printing identity")
    return canonical({"version": 1, "kind": "PRINTING", **identity.model_dump()})


def treatment_identity(parent_identity: str, treatment: Treatment) -> str:
    if treatment.treatment_key is None:
        raise ValueError("Incomplete treatment identity")
    return canonical(
        {
            "version": 1,
            "kind": "TREATMENT",
            "parent": json.loads(parent_identity),
            "treatment": treatment.treatment_key,
            "finish": treatment.finish_key,
            "collector_number": treatment.collector_number,
        }
    )


def derived_public_id(identity: str) -> str:
    prefix = "cpr_" if json.loads(identity)["kind"] == "PRINTING" else "trt_"
    return prefix + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:56]


class Registry:
    """Read-only registry snapshot; assignments are proposed, never persisted or replaced.

    Existing assignments take precedence over derivation. The validator compares all
    proposals against every reserved ID, including identities absent from this batch.
    """

    def __init__(self, assignments: Mapping[str, str] | None = None):
        self.assignments = dict(assignments or {})

    def propose(self, identity: str) -> str:
        if identity in self.assignments:
            return self.assignments[identity]
        return derived_public_id(identity)
