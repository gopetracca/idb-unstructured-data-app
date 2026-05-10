"""Alembic environment configuration for SQL Server migrations."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.config.settings import get_settings
from src.infrastructure.sqlserver.models.base import Base

# Import all models so that Base.metadata is fully populated
import src.infrastructure.sqlserver.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Get the database URL, preferring the ini config value over application settings.

    When called programmatically (e.g. from testcontainers fixtures), the caller
    sets ``sqlalchemy.url`` via ``cfg.set_main_option()``.  Honour that value so
    the migration runs against the ephemeral container rather than the URL stored
    in the application settings / environment.
    """
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url
    return get_settings().sql_server.database_url_migrations


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script without connecting to the database.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations with a database connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Supports two modes:
    1. Programmatic: connection passed via config.attributes["connection"]
    2. CLI: creates its own async engine and connection
       (used by `uv run python scripts/migrate.py` or `alembic upgrade head`)
    """
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        do_run_migrations(connectable)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
