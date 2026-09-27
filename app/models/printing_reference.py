"""Curated external references attached to collectible Printings."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.variant import CardVariant


class PrintingReference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "printing_references"

    printing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("card_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("edition_collector_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    reference_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    worksheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workbook_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    semantic_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    collector_number: Mapped[str] = mapped_column(String(64), nullable=False)
    card_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rarity_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    variant_raw: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_rarity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collector_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_treatment: Mapped[str] = mapped_column(String(128), nullable=False)

    printing: Mapped["CardVariant"] = relationship(back_populates="references")
    snapshot = relationship("EditionCollectorSnapshot", back_populates="references")

    __table_args__ = (
        CheckConstraint(
            "workbook_row IS NULL OR workbook_row > 0",
            name="ck_printing_references_workbook_row_positive",
        ),
        UniqueConstraint("source_name", "reference_key", name="uq_printing_reference_source_key"),
        UniqueConstraint(
            "printing_id", "source_name", "reference_key", name="uq_printing_reference_owner_key"
        ),
    )
