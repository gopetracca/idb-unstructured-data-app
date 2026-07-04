"""Startup database migration runner (AIA-394).

Runs ``alembic upgrade head`` against ``SQL_SERVER_DATABASE_URL_MIGRATIONS``
(falling back to ``SQL_SERVER_DATABASE_URL``) while holding a SQL Server
application lock, so concurrent replicas starting the same revision cannot run
migrations at the same time.

This module lives under ``src/`` (not ``scripts/``) because ``scripts/`` is
excluded from the container image by ``.dockerignore``; the container startup
script triggers it when ``RUN_DB_MIGRATIONS_ON_STARTUP=true`` (set by the CD
pipeline via the deploy script's ``--run-migrations`` flag).

Usage (inside the container / locally):
    python -m src.infrastructure.sqlserver.run_migrations
"""

import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

_LOCK_RESOURCE = "alembic_migrations"
_LOCK_TIMEOUT_MS = 120_000  # wait up to 2 minutes for a concurrent migrator


def _find_alembic_ini() -> Path:
    """Locate alembic.ini relative to the repository / image root."""
    for candidate in (
        Path(__file__).resolve().parents[3] / "alembic.ini",  # repo/image root
        Path.cwd() / "alembic.ini",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("alembic.ini not found — cannot run migrations")


async def _run() -> None:
    settings = get_settings().sql_server
    if not settings.enabled:
        logger.info("SQL Server disabled (SQL_SERVER_ENABLED=false) — skipping migrations")
        return

    url = settings.database_url_migrations or settings.database_url
    if not url:
        raise RuntimeError(
            "SQL_SERVER_DATABASE_URL_MIGRATIONS (or SQL_SERVER_DATABASE_URL) must be set"
        )

    alembic_ini = _find_alembic_ini()
    engine = create_async_engine(url, poolclass=NullPool)

    try:
        async with engine.connect() as connection:
            # Session-scoped app lock: serializes migrators across replicas.
            result = await connection.execute(
                text(
                    "DECLARE @rc int; "
                    "EXEC @rc = sp_getapplock @Resource = :resource, "
                    "@LockMode = 'Exclusive', @LockOwner = 'Session', "
                    "@LockTimeout = :timeout_ms; "
                    "SELECT @rc"
                ),
                {"resource": _LOCK_RESOURCE, "timeout_ms": _LOCK_TIMEOUT_MS},
            )
            if (result.scalar() or 0) < 0:
                raise RuntimeError(
                    "Could not acquire the migration app lock — is another migrator stuck?"
                )

            def _upgrade(sync_connection) -> None:
                config = Config(str(alembic_ini))
                config.attributes["connection"] = sync_connection
                command.upgrade(config, "head")

            try:
                await connection.run_sync(_upgrade)
                await connection.commit()
            finally:
                await connection.execute(
                    text(
                        "EXEC sp_releaseapplock @Resource = :resource, @LockOwner = 'Session'"
                    ),
                    {"resource": _LOCK_RESOURCE},
                )
        logger.info("Database migrations applied successfully (alembic upgrade head)")
    finally:
        await engine.dispose()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("Database migration failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
