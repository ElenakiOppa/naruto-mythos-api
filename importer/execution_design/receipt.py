"""Future receipt and replay contracts. No receipts are issued or persisted here."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from importer.projection.canonical import digest
from importer.projection.models import Hash, Model
from importer.staging.models import Text


def idempotency_key(plan_hash: str, destination_reference: str) -> str:
    return digest({"version": 1, "plan_hash": plan_hash, "destination": destination_reference})


class ExecutionReceipt(Model):
    version: Literal["1"] = "1"
    plan_hash: Hash
    destination_reference: Text
    idempotency_key: Hash
    approval_reference: Text
    pre_state_hash: Hash
    post_state_hash: Hash | None = None
    operation_counts: dict[str, Annotated[int, Field(strict=True, ge=0)]]
    executed_at: AwareDatetime
    executor_authentication_reference: Text
    transaction_reference: Text
    outcome: Literal["SUCCESS", "FAILED"]
    rolled_back: StrictBool
    provenance_reference: Text | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.idempotency_key != idempotency_key(self.plan_hash, self.destination_reference):
            raise ValueError("Receipt idempotency identity mismatch")
        if self.outcome == "SUCCESS" and (
            self.rolled_back or self.post_state_hash is None or self.provenance_reference is None
        ):
            raise ValueError("Success requires post-state and provenance, without rollback")
        if self.outcome == "FAILED" and not self.rolled_back:
            raise ValueError("Atomic failure must report rollback")
        if self.rolled_back and self.post_state_hash not in (None, self.pre_state_hash):
            raise ValueError("Rollback cannot report partial committed state")
        return self


def previously_succeeded(
    plan_hash: str, destination: str, receipts: tuple[ExecutionReceipt, ...]
) -> bool:
    key = idempotency_key(plan_hash, destination)
    return any(
        ExecutionReceipt.model_validate(r.model_dump(mode="json")).idempotency_key == key
        and r.outcome == "SUCCESS"
        for r in receipts
    )
