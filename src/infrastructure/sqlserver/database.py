"""Async database engine and session factory for SQL Server."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import SqlServerSettings

logger = logging.getLogger(__name__)


def create_engine(settings: SqlServerSettings) -> AsyncEngine:
    """Create an async SQLAlchemy engine from settings.

    Args:
        settings: SQL Server configuration

    Returns:
        Configured async engine
    """
    db_url = settings.database_url
    # Ensure ODBC connection timeout is set to avoid hanging on unreachable servers
    if "Connection+Timeout" not in db_url and "Connection Timeout" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{separator}Connection+Timeout=10"

    return create_async_engine(
        db_url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        echo=settings.echo_sql,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: Async SQLAlchemy engine

    Returns:
        Session factory that produces AsyncSession instances
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, rolling back on error.

    Usage:
        async for session in get_session(factory):
            await session.execute(...)

    Args:
        session_factory: Async session factory

    Yields:
        AsyncSession instance
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
