"""Localized publisher text and URL references; never artwork bytes or identity."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.variant import CardVariant


class PrintingTranslation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "printing_translations"

    printing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("card_variants.id", ondelete="CASCADE"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rules_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    edition_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    distribution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    printing: Mapped["CardVariant"] = relationship(back_populates="translations")

    __table_args__ = (
        UniqueConstraint("printing_id", "language", name="uq_printing_translation_language"),
    )
