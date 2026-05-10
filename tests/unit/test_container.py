"""Unit tests for dependency container error paths."""

import pytest
from dependency_injector import providers

from src.config.settings import Settings, SqlServerSettings
from src.container import Container


@pytest.mark.unit
class TestContainerSqlServerGuards:
    """Ensure SQL-only repository providers fail fast when SQL Server is disabled."""

    def test_document_repository_raises_when_sql_disabled(self) -> None:
        settings = Settings(
            sql_server=SqlServerSettings(
                enabled=False,
                database_url="",
            )
        )
        container = Container()

        with container.settings.override(providers.Object(settings)):
            with pytest.raises(RuntimeError, match="SQL Server metadata store is required"):
                container.document_repository()

    def test_chunk_index_repository_raises_when_sql_disabled(self) -> None:
        settings = Settings(
            sql_server=SqlServerSettings(
                enabled=False,
                database_url="",
            )
        )
        container = Container()

        with container.settings.override(providers.Object(settings)):
            with pytest.raises(RuntimeError, match="SQL Server metadata store is required"):
                container.chunk_index_repository()
