"""
CardVariant model.

Represents a specific printed finish/edition of a Card (normal, holographic,
full-art, secret, gold, promo, numbered, etc). `variant_type` is a free-text,
indexed string -- deliberately NOT a Postgres ENUM -- so new variant types
can be introduced by inserting data, never by running a migration.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.card import Card
    from app.models.image import CardImage


class CardVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "card_variants"

    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Free-text and indexed, not an ENUM -- see module docstring.
    variant_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    finish: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rarity_override: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collector_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="EN", server_default="EN"
    )
    edition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial_numbered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    serial_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    card: Mapped["Card"] = relationship(back_populates="variants")

    # Deleting a variant does NOT delete its images -- see CardImage.variant_id
    # (ON DELETE SET NULL) for the rationale. No cascade is configured here;
    # the database-level SET NULL, and SQLAlchemy's default nullify-on-delete
    # behavior for a nullable FK, handle this without deleting image rows.
    images: Mapped[list["CardImage"]] = relationship(
        back_populates="variant",
        foreign_keys="CardImage.variant_id",
        primaryjoin="CardVariant.id == CardImage.variant_id",
    )

    __table_args__ = (
        UniqueConstraint("id", "card_id", name="uq_card_variants_id_card_id"),
        # serial_numbered=False cards are never required to carry a total;
        # this only constrains serial_total's own value when present, it
        # does not force serial_total to exist when serial_numbered is true
        # (a numbered variant's total print run may simply be unknown yet).
        CheckConstraint(
            "serial_total IS NULL OR serial_total > 0",
            name="ck_card_variants_serial_total_positive",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<CardVariant public_id={self.public_id!r} variant_type={self.variant_type!r}>"
