"""
Shared base class for every public-facing API schema.

Not part of the originally sketched `app/schemas/` file list, but added for
the same reason `app/models/mixins.py` was added in Phase 2: every public
schema needs the same two config flags, and centralizing them avoids that
config drifting out of sync across a dozen files.

- `from_attributes=True`: lets a schema be built directly from a SQLAlchemy
  ORM instance (`SomeSchema.model_validate(orm_object)`), including nested
  relationships (e.g. `card.set`, `card.keywords`) -- every schema that
  might appear as a nested field of another ORM-sourced schema needs this
  set on itself too, not just on the top-level schema being validated.
- `populate_by_name=True`: several fields use a `validation_alias` that
  differs from the field name (see individual schema modules for why --
  short version: the field name IS the public JSON key, and the alias is
  only used to pull the value from a differently-named ORM attribute).
  Without `populate_by_name=True`, manually constructing a schema with
  keyword arguments (e.g. in a test) would only accept the alias, not the
  friendly field name -- which would be a confusing, inconsistent
  developer experience for anyone building these objects by hand.
"""

from pydantic import BaseModel, ConfigDict


class PublicSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
