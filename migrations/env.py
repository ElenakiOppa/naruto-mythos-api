"""
Alembic environment script.

The database URL is pulled from the application's own Settings
(app.config.get_settings()) rather than being duplicated in alembic.ini, so
there is exactly one source of truth for DATABASE_URL. target_metadata comes
from importing app.models, which registers every ORM model on Base's
declarative registry.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app package so `app.config` / `app.database` / `app.models` are
# resolvable. This assumes Alembic is run from the project root (the default
# `alembic upgrade head` usage documented in the README), where `app` is
# importable thanks to `prepend_sys_path = .` in alembic.ini.
import app.models  # noqa: F401 -- registers all models on Base.metadata
from app.config import get_settings
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def include_object(obj, name, type_, reflected, compare_to):
    # Conditional SQLite-only metadata constraint must not appear as a
    # PostgreSQL autogenerate addition. Its replacement is the composite FK.
    return not (
        type_ == "foreign_key_constraint"
        and not reflected
        and name == "fk_card_images_variant_id_card_variants"
    )


def migrate_connection(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        migrate_connection(supplied_connection)
        return
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        migrate_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
