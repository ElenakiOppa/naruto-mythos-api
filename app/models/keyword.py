"""
Keyword model and the card_keywords many-to-many association table.

Keywords are reusable, catalogue-wide tags (e.g. "team-7"). A card may have
zero or many keywords.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.card import Card

# Plain many-to-many association table (not an association *object*, since
# the relationship carries no attributes of its own beyond the two foreign
# keys). Composite primary key on (card_id, keyword_id) makes a duplicate
# association a straightforward, database-enforced integrity error rather
# than something the application has to check for itself.
card_keywords = Table(
    "card_keywords",
    Base.metadata,
    Column(
        "card_id",
        Uuid(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "keyword_id",
        Uuid(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Keyword(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "keywords"

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    cards: Mapped[list["Card"]] = relationship(
        secondary=card_keywords,
        back_populates="keywords",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Keyword slug={self.slug!r}>"
