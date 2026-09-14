"""
Set model.

Represents a single printed set/expansion (e.g. a Naruto Mythos booster
set). No real set data is created here -- only the schema.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.card import Card


class CardSet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Maps to the `sets` table.

    Named `CardSet` rather than `Set` to avoid shadowing Python's built-in
    `set` type throughout the codebase (a plain `Set` class name is easy to
    trip over in code that also does `set()` operations).
    """

    __tablename__ = "sets"

    # Stable public identifier (e.g. "konoha-shido-1e"). This -- not `id` --
    # is what the API and importer reference; `id` never leaves the database.
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    edition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="EN", server_default="EN"
    )
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    printed_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_with_variants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Intentionally NOT cascade="all, delete-orphan": a Set that still has
    # Cards cannot be deleted (see cards.set_id ForeignKey ondelete="RESTRICT"
    # in app/models/card.py). If a set genuinely needs to be removed, its
    # cards must be removed/reassigned first -- this prevents an accidental
    # `DELETE FROM sets WHERE ...` from silently wiping an entire catalogue
    # of cards via ORM cascade.
    cards: Mapped[list["Card"]] = relationship(back_populates="set")

    __table_args__ = (
        CheckConstraint(
            "printed_total IS NULL OR printed_total >= 0",
            name="ck_sets_printed_total_non_negative",
        ),
        CheckConstraint(
            "total_with_variants IS NULL OR total_with_variants >= 0",
            name="ck_sets_total_with_variants_non_negative",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<CardSet public_id={self.public_id!r} name={self.name!r}>"
