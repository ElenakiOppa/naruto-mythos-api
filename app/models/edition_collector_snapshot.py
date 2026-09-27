"""Edition-scoped source snapshot and expected collector completeness."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EditionCollectorSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "edition_collector_snapshots"

    edition_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    set_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    transport_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_printing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    identity_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    exhaustive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    edition = relationship("Edition", back_populates="collector_snapshots")
    references = relationship("PrintingReference", back_populates="snapshot")

    __table_args__ = (
        ForeignKeyConstraint(
            ["edition_id", "set_id"],
            ["editions.id", "editions.set_id"],
            name="fk_edition_collector_snapshots_edition_set",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "edition_id",
            "source_type",
            "source_snapshot_sha256",
            name="uq_edition_collector_snapshot_source_hash",
        ),
        CheckConstraint(
            "expected_printing_count > 0",
            name="ck_edition_collector_snapshots_expected_count_positive",
        ),
        CheckConstraint(
            "length(source_snapshot_sha256) = 64 AND length(identity_digest) = 64",
            name="ck_edition_collector_snapshots_hash_lengths",
        ),
    )
