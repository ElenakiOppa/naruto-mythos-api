"""
CardVariant model.

Represents a specific printed finish/edition of a Card (normal, holographic,
full-art, secret, gold, promo, numbered, etc). `variant_type` is a free-text,
indexed string -- deliberately NOT a Postgres ENUM -- so new variant types
can be introduced by inserting data, never by running a migration.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.card import Card
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.printing_taxonomy import normalize_printing_taxonomy

if TYPE_CHECKING:
    from app.models.edition import Edition
    from app.models.image import CardImage
    from app.models.translation import PrintingTranslation


class CardVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "card_variants"

    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Redundant owner key supports composite foreign keys that enforce the
    # Card/Edition same-Set invariant in PostgreSQL, including direct SQL.
    set_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
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
    # Raw nullable publisher identity; variant_type remains the legacy API classification.
    source_variant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stamp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_rarity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collector_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_treatment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rarity_resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNRESOLVED", server_default="UNRESOLVED"
    )
    variant_resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNSPECIFIED", server_default="UNSPECIFIED"
    )
    serial_numbered: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    serial_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    card: Mapped["Card"] = relationship(back_populates="variants", foreign_keys=[card_id])
    edition_record: Mapped["Edition | None"] = relationship(
        back_populates="printings", foreign_keys=[edition_id]
    )
    translations: Mapped[list["PrintingTranslation"]] = relationship(
        back_populates="printing", cascade="all, delete-orphan", passive_deletes=True
    )

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
        Index(
            "uq_printing_semantic_identity",
            card_id,
            edition_id,
            func.normalize(rarity_override),
            func.normalize(source_variant),
            func.normalize(card_version),
            func.normalize(stamp),
            unique=True,
            postgresql_nulls_not_distinct=True,
        ).ddl_if(dialect="postgresql"),
        UniqueConstraint("id", "card_id", name="uq_card_variants_id_card_id"),
        ForeignKeyConstraint(
            ["card_id", "set_id"],
            ["cards.id", "cards.set_id"],
            name="fk_card_variants_card_set_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["edition_id", "set_id"],
            ["editions.id", "editions.set_id"],
            name="fk_card_variants_edition_set_owner",
            ondelete="RESTRICT",
        ),
        # A null serial_numbered value means the source provided no evidence;
        # a known serialized printing may still have an unknown serial_total.
        CheckConstraint(
            "serial_total IS NULL OR serial_total > 0",
            name="ck_card_variants_serial_total_positive",
        ),
        CheckConstraint(
            "rarity_resolution_status IN ('MAPPED', 'UNRESOLVED')",
            name="ck_card_variants_rarity_resolution_status",
        ),
        CheckConstraint(
            "variant_resolution_status IN ('MAPPED', 'UNSPECIFIED', 'UNRESOLVED')",
            name="ck_card_variants_variant_resolution_status",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<CardVariant public_id={self.public_id!r} variant_type={self.variant_type!r}>"


# Same mapper/table and public IDs; no duplicate entity or physical rename.
Printing = CardVariant


@event.listens_for(CardVariant, "before_insert")
def _populate_printing_set_id(_mapper, connection, target: CardVariant) -> None:
    if target.set_id is not None:
        return
    if target.card is not None:
        target.set_id = target.card.set_id
        return
    target.set_id = connection.execute(
        select(Card.set_id).where(Card.id == target.card_id)
    ).scalar_one()


@event.listens_for(CardVariant, "before_insert")
@event.listens_for(CardVariant, "before_update")
def _populate_printing_taxonomy(_mapper, connection, target: CardVariant) -> None:
    card_type = (
        target.card.card_type
        if target.card is not None
        else connection.execute(
            select(Card.card_type).where(Card.id == target.card_id)
        ).scalar_one()
    )
    taxonomy = normalize_printing_taxonomy(target.rarity_override, target.source_variant, card_type)
    for field, value in taxonomy.as_dict().items():
        setattr(target, field, value)
