"""Unit tests for dependency container error paths."""

import sys

import pytest
from dependency_injector import providers

from src.config.settings import Settings, SqlServerSettings
from src.container import (
    Container,
    ExtractionConfigurationError,
    verify_extraction_configuration,
)


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

    def test_docling_without_the_extra_names_the_remedy(self, monkeypatch) -> None:
        """The deployment image is built without the extra, so this is the failure a
        deployed `EXTRACTION_ADAPTER=docling` actually produces. A bare
        `ModuleNotFoundError: docling_core` would name neither the setting nor the fix."""
        import builtins

        real_import = builtins.__import__

        def without_docling(name, *args, **kwargs):
            if name.startswith("src.infrastructure.docling") or name.startswith("docling"):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "src.infrastructure.docling.adapter", raising=False)
        monkeypatch.setattr(builtins, "__import__", without_docling)

        with pytest.raises(ExtractionConfigurationError) as failure:
            self._adapter(extraction_adapter="docling")

        message = str(failure.value)
        assert "EXTRACTION_ADAPTER=docling" in message
        assert "uv sync --extra docling" in message


@pytest.mark.unit
class TestExtractionIsVerifiedAtStartup:
    """Every provider is lazy, so without this the first *document* is what discovers a
    deployment that cannot extract — inside a queue trigger, whose message is then
    redelivered and poisoned."""

    def test_the_check_builds_the_configured_adapter(self) -> None:
        settings = Settings(document_intelligence={"endpoint": "https://di.example.com"})
        container = Container()

        with container.settings.override(providers.Object(settings)):
            verify_extraction_configuration(container)

            assert container.document_extractor_adapter() is not None

    def test_it_raises_rather_than_deferring_to_the_first_document(self) -> None:
        """An engine that cannot be built takes the process down at startup, where the
        readiness probe can see it, instead of failing every message it is handed."""
        settings = Settings(extraction_adapter="docling", docling={"artifacts_path": "/nope"})
        container = Container()

        with container.settings.override(providers.Object(settings)):
            with pytest.raises(Exception, match="DOCLING_ARTIFACTS_PATH"):
                verify_extraction_configuration(container)
