"""A known collectible edition scoped to one CardSet."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.edition_identity import normalize_edition_name

if TYPE_CHECKING:
    from app.models.set import CardSet
    from app.models.variant import CardVariant


class Edition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "editions"

    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(64), nullable=False)

    set: Mapped["CardSet"] = relationship(back_populates="editions")
    printings: Mapped[list["CardVariant"]] = relationship(
        back_populates="edition_record", foreign_keys="CardVariant.edition_id"
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_editions_name_nonblank"),
        CheckConstraint(
            "normalized_name = lower(normalize(regexp_replace(btrim(name), E'\\\\s+', ' ', 'g'), NFC))",
            name="ck_editions_normalized_name",
        ).ddl_if(dialect="postgresql"),
        UniqueConstraint("set_id", "normalized_name", name="uq_editions_set_normalized_name"),
        UniqueConstraint("id", "set_id", name="uq_editions_id_set_id"),
    )


@event.listens_for(Edition, "before_insert")
@event.listens_for(Edition, "before_update")
def _set_normalized_edition_name(_mapper, _connection, target: Edition) -> None:
    normalized = normalize_edition_name(target.name)
    if not normalized:
        raise ValueError("Edition name cannot be blank")
    target.normalized_name = normalized
