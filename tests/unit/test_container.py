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


@pytest.mark.unit
class TestExtractionAdapterSelection:
    """Which engine the container picks, and — as much to the point — which it never picks.

    The order is deliberate: an explicit fake wins over everything, because it is the one
    switch that turns every adapter off for local development; `EXTRACTION_ADAPTER` then
    names the engine; Azure follows if it is configured; the fake is the last resort.
    """

    @staticmethod
    def _adapter(**overrides):
        from src.container import _create_document_extractor_adapter

        return _create_document_extractor_adapter(Settings(**overrides))

    def test_the_default_is_document_intelligence(self) -> None:
        from src.infrastructure.azure.adapters.document_intelligence_azure import (
            AzureDocumentIntelligenceAdapter,
        )

        adapter = self._adapter(
            document_intelligence={"endpoint": "https://di.example.com", "api_key": "k"}
        )

        assert isinstance(adapter, AzureDocumentIntelligenceAdapter)

    def test_docling_is_selected_when_it_is_named(self) -> None:
        pytest.importorskip("docling", reason="the optional docling extra is not installed")
        from src.infrastructure.docling.adapter import DoclingExtractionAdapter

        adapter = self._adapter(extraction_adapter="docling")

        assert isinstance(adapter, DoclingExtractionAdapter)

    def test_an_explicit_fake_still_wins(self) -> None:
        from src.infrastructure.azure.adapters.document_intelligence_fake import (
            FakeDocumentIntelligenceAdapter,
        )

        adapter = self._adapter(
            extraction_adapter="docling",
            document_intelligence={"use_fake": True},
        )

        assert isinstance(adapter, FakeDocumentIntelligenceAdapter)

    def test_an_unconfigured_azure_falls_back_to_the_fake_and_never_to_docling(self) -> None:
        """A missing Azure endpoint is no evidence that Docling's artifacts are present."""
        from src.infrastructure.azure.adapters.document_intelligence_fake import (
            FakeDocumentIntelligenceAdapter,
        )

        adapter = self._adapter(document_intelligence={"endpoint": ""})

        assert isinstance(adapter, FakeDocumentIntelligenceAdapter)

    def test_an_unrecognised_engine_fails_at_startup(self) -> None:
        with pytest.raises(ValueError, match="EXTRACTION_ADAPTER"):
            Settings(extraction_adapter="doclng")
