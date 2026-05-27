"""Integration tests for document-type-specific index creation.

These tests require a live Azure AI Search instance. They are skipped
automatically in CI unless AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY
are set in the environment.

Run with:
    uv run pytest tests/integration/infrastructure/test_vector_search_index_types.py -v
"""

import pytest

from src.config.settings import get_settings
from src.core.errors import IndexNotFoundError
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.mark.integration
class TestOperationalIndexLifecycle:
    """Integration tests for operational document index lifecycle."""

    @pytest.fixture
    async def adapter(self):
        settings = get_settings()
        adapter = AzureAISearchAdapter(settings.vector_search)
        yield adapter
        await adapter.close()

    @pytest.fixture
    def index_name(self):
        return "test-operational-integration-112"

    async def test_create_and_introspect_operational_index(self, adapter, index_name):
        """Full lifecycle: create → introspect → delete."""
        try:
            result = await adapter.create_operational_index(index_name)
            assert result is True

            info = await adapter.get_index(index_name)
            assert info["document_category"] == "operational"

            # Operational-specific fields must be in the schema
            field_names = {f for f in info["schema"]["fields"]}
            assert "metadata" in field_names

        finally:
            try:
                await adapter.delete_index(index_name)
            except (IndexNotFoundError, Exception):
                pass

    async def test_list_indexes_includes_document_category(self, adapter, index_name):
        """list_indexes() should return document_category for each index."""
        try:
            await adapter.create_operational_index(index_name)

            indexes = await adapter.list_indexes()
            match = next((i for i in indexes if i["name"] == index_name), None)

            assert match is not None
            assert match["document_category"] == "operational"

        finally:
            try:
                await adapter.delete_index(index_name)
            except (IndexNotFoundError, Exception):
                pass


@pytest.mark.integration
class TestPublicationIndexLifecycle:
    """Integration tests for publication document index lifecycle."""

    @pytest.fixture
    async def adapter(self):
        settings = get_settings()
        adapter = AzureAISearchAdapter(settings.vector_search)
        yield adapter
        await adapter.close()

    @pytest.fixture
    def index_name(self):
        return "test-publication-integration-112"

    async def test_create_and_introspect_publication_index(self, adapter, index_name):
        """Full lifecycle: create → introspect → delete."""
        try:
            result = await adapter.create_publication_index(index_name)
            assert result is True

            info = await adapter.get_index(index_name)
            assert info["document_category"] == "publication"

        finally:
            try:
                await adapter.delete_index(index_name)
            except (IndexNotFoundError, Exception):
                pass


@pytest.mark.integration
class TestCreateIndexRequiresDocumentType:
    """Integration tests for document_type enforcement."""

    @pytest.fixture
    async def adapter(self):
        settings = get_settings()
        adapter = AzureAISearchAdapter(settings.vector_search)
        yield adapter
        await adapter.close()

    async def test_create_index_without_document_category_raises(self, adapter):
        """create_index() raises ValueError when document_category is omitted."""
        with pytest.raises(ValueError, match="document_category"):
            await adapter.create_index("should-not-exist", {"vector_dimension": 1536})
