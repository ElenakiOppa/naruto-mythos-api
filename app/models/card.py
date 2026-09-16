"""
Card model.

Represents a conceptual/base Card within an expansion. Collectible publisher
Printings use CardVariant (also exported as Printing).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.image import CardImage
    from app.models.keyword import Keyword
    from app.models.set import CardSet
    from app.models.variant import CardVariant


class Card(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cards"

    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # ondelete="RESTRICT": a set with existing cards cannot be deleted at the
    # database level. This is a deliberate safety choice beyond what the spec
    # states explicitly -- see CardSet.cards for the matching ORM-side
    # rationale. It prevents an entire catalogue of cards from disappearing
    # as a side effect of removing (or mistakenly re-creating) a set record.
    set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Card numbers are strings on purpose -- collector numbers are not
    # reliably numeric (e.g. "SP-01", "001a", "EX3"). Never cast/store as int.
    card_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rarity: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    chakra: Mapped[int | None] = mapped_column(Integer, nullable=True)
    power: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ability_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    flavor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)

    set: Mapped["CardSet"] = relationship(back_populates="cards")

    # A card's variants and images are owned by the card: deleting a card
    # deletes them too (ORM cascade + FK-level ON DELETE CASCADE, enforced
    # at the database regardless of whether the ORM session has them loaded).
    variants: Mapped[list["CardVariant"]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    images: Mapped[list["CardImage"]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Many-to-many via the card_keywords association table. FK-level
    # ON DELETE CASCADE on card_keywords handles cleanup of the association
    # rows themselves; no ORM delete-orphan cascade is needed here since
    # there's no "orphaned" Keyword to clean up (keywords are independent,
    # reusable, catalogue-wide records).
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary="card_keywords",
        back_populates="cards",
    )

    __table_args__ = (
        # Card numbers repeat across sets (e.g. every set has a "001"), but
        # must be unique *within* a set -- this is the canonical-duplicate
        # guard rail, not a global uniqueness constraint on card_number.
        UniqueConstraint("set_id", "card_number", name="uq_cards_set_id_card_number"),
        CheckConstraint("chakra IS NULL OR chakra >= 0", name="ck_cards_chakra_non_negative"),
        CheckConstraint("points IS NULL OR points >= 0", name="ck_cards_points_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Card public_id={self.public_id!r} name={self.name!r}>"
