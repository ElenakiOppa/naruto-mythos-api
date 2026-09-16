"""
Importing this package registers every ORM model on `Base`'s declarative
registry. This module must be imported (directly or transitively) before
`Base.metadata` is used for anything -- Alembic's `env.py`, test fixtures
that call `Base.metadata.create_all(...)`, etc. -- or tables defined in
modules that were never imported simply won't exist in the metadata.
"""

from app.models.card import Card
from app.models.image import CardImage
from app.models.keyword import Keyword, card_keywords
from app.models.set import CardSet
from app.models.source import SourceRecord
from app.models.translation import PrintingTranslation
from app.models.variant import CardVariant, Printing

__all__ = [
    "Card",
    "CardImage",
    "CardSet",
    "CardVariant",
    "Keyword",
    "Printing",
    "PrintingTranslation",
    "SourceRecord",
    "card_keywords",
]
