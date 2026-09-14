"""
Shared declarative mixins.

Not part of the originally sketched `app/models/` file list, but added
because every catalogue table needs the same UUID-primary-key and
created_at/updated_at behavior. Centralizing it here avoids repeating
(and risking drift in) the same three columns across six model files.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Internal UUID primary key.

    Uses SQLAlchemy's backend-agnostic `Uuid` type rather than
    `sqlalchemy.dialects.postgresql.UUID` directly. On PostgreSQL this still
    compiles to the native `UUID` column type (satisfying the requirement to
    use PostgreSQL UUID types), but it also allows the same model code to run
    against SQLite for isolated unit tests, per the project's testing policy.

    UUIDs are generated application-side (`default=uuid.uuid4`) rather than
    via a Postgres server-side default such as `gen_random_uuid()`, so no
    Postgres extension (pgcrypto/uuid-ossp) needs to be enabled.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Timezone-aware created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
