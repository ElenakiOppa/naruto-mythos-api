"""
SourceRecord model.

Tracks where a piece of catalogue data (a set, card, variant, etc.)
originated from. Deliberately has NO foreign key on entity_id, since a
single source_records table needs to reference rows across several
different tables (sets, cards, variants, ...) identified by entity_type.
A polymorphic foreign key isn't representable as a single real FK constraint
without either a shared identity table or per-entity-type nullable FKs, and
this is unlikely to be worth the added schema complexity for what is
fundamentally an audit/provenance trail rather than a live relationship the
API needs to join through.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class SourceRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "source_records"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    source_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Typed observations supplement existing polymorphic provenance without rewriting it.
    printing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("card_variants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "printing_id IS NULL OR (entity_type = 'card_variants' AND entity_id = printing_id)",
            name="ck_source_printing_owner",
        ),
        # Composite index for the primary lookup pattern: "what do we know
        # about this specific catalogue entity". No separate single-column
        # index on entity_type alone -- a composite index's leftmost column
        # (entity_type) is already usable on its own by the query planner,
        # so a standalone index would be redundant.
        Index("ix_source_records_entity_type_entity_id", "entity_type", "entity_id"),
        # Composite index for the reverse lookup pattern: "what did source X
        # tell us about external ID Y" (e.g. de-duplicating during import).
        Index("ix_source_records_source_name_external_id", "source_name", "external_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SourceRecord entity_type={self.entity_type!r} source_name={self.source_name!r}>"
