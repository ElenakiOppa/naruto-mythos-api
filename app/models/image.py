"""
CardImage model.

Stores metadata about an image associated with a card (and optionally a
specific variant). No image bytes/artwork are ever downloaded or stored --
only URLs and provenance metadata, per project policy.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.card import Card
    from app.models.variant import CardVariant


class CardImage(Base, UUIDPrimaryKeyMixin):
    """Maps to the `card_images` table.

    Deliberately does NOT use TimestampMixin: the spec's field list for this
    table includes only `created_at`, with no `updated_at` -- an image
    row retains its original creation time. The importer can update dimensions
    and attribution in place; source_records tracks its observation times.
    """

    __tablename__ = "card_images"

    card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nullable, and ON DELETE SET NULL rather than CASCADE: if the specific
    # variant this image depicts is later removed from the catalogue, the
    # image metadata (URL, dimensions, source/provenance) still has value on
    # its own and is preserved -- it just becomes variant-unspecified rather
    # than being destroyed. This avoids silent data loss from what might be
    # a routine variant correction.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    image_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="front", server_default="front"
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hosted_by_us: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    card: Mapped["Card"] = relationship(back_populates="images")
    variant: Mapped["CardVariant | None"] = relationship(
        back_populates="images",
        foreign_keys=[variant_id],
        primaryjoin="CardImage.variant_id == CardVariant.id",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["variant_id", "card_id"],
            ["card_variants.id", "card_variants.card_id"],
            name="fk_card_images_variant_card_owner",
            ondelete="SET NULL (variant_id)",
        ).ddl_if(dialect="postgresql"),
        # SQLite unit databases retain their real simple FK and delete action.
        # PostgreSQL alone verifies the composite ownership invariant.
        ForeignKeyConstraint(
            ["variant_id"],
            ["card_variants.id"],
            name="fk_card_images_variant_id_card_variants",
            ondelete="SET NULL",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_card_images_width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_card_images_height_positive"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<CardImage card_id={self.card_id!r} image_type={self.image_type!r}>"
