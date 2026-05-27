"""Unit tests for AzureAISearchAdapter."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from src.config.settings import VectorSearchSettings
from src.core.entities.search_result import SearchResult
from src.core.entities.vector_document import VectorDocument
from src.core.errors import IndexNotFoundError, VectorDatabaseError
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.fixture
def mock_settings():
    """Create mock VectorSearchSettings for testing."""
    return VectorSearchSettings(
        endpoint="https://test.search.windows.net",
        api_key="test_key",
        default_index_name="test-index",
        hnsw_m=4,
        hnsw_ef_construction=400,
        hnsw_ef_search=500,
        batch_size=1000,
    )


@pytest.fixture
def sample_vector_documents():
    """Create sample VectorDocument instances for testing."""
    return [
        VectorDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Test content 1",
            vector=[0.1] * 1536,
            metadata={"model_version": "v1", "token_count": 100},
        ),
        VectorDocument(
            id="file1_chunk1",
            chunk_id="chunk1",
            file_id="file1",
            text="Test content 2",
            vector=[0.2] * 1536,
            metadata={"model_version": "v1", "token_count": 150},
        ),
    ]


@pytest.fixture
async def adapter(mock_settings):
    """Create AzureAISearchAdapter with mocked client."""
    with patch(
        "src.infrastructure.azure.adapters.vector_search_azure.SearchClientWrapper"
    ) as mock_wrapper:
        adapter = AzureAISearchAdapter(mock_settings)
        # Mock the client wrapper methods
        adapter._client_wrapper = AsyncMock()
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.get_search_client = Mock(return_value=AsyncMock())
        yield adapter


class TestAzureAISearchAdapter:
    """Tests for AzureAISearchAdapter."""

    async def test_create_index_success(self, adapter):
        """Test successful index creation."""
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        result = await adapter.create_index(
            "test-index", {"vector_dimension": 1536, "document_category": "operational"}
        )

        assert result is True
        adapter._client_wrapper.index_client.create_or_update_index.assert_called_once()

    async def test_create_index_failure(self, adapter):
        """Test index creation failure."""
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock(
            side_effect=Exception("Creation failed")
        )

        with pytest.raises(VectorDatabaseError) as exc_info:
            await adapter.create_index(
                "test-index", {"vector_dimension": 1536, "document_category": "operational"}
            )

        assert "Creation failed" in str(exc_info.value)

    async def test_upsert_documents_success(self, adapter, sample_vector_documents):
        """Test successful document upsert."""
        # Mock successful upload
        mock_result = [
            Mock(key="file1_chunk0", succeeded=True),
            Mock(key="file1_chunk1", succeeded=True),
        ]

        mock_client = AsyncMock()
        mock_client.merge_or_upload_documents = AsyncMock(return_value=mock_result)
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        result = await adapter.upsert_documents("test-index", sample_vector_documents)

        assert len(result) == 2
        assert "file1_chunk0" in result
        assert "file1_chunk1" in result
        mock_client.merge_or_upload_documents.assert_called_once()

    async def test_upsert_documents_partial_failure(self, adapter, sample_vector_documents):
        """Test document upsert with partial failures."""
        # Mock partial success
        mock_result = [
            Mock(key="file1_chunk0", succeeded=True),
            Mock(key="file1_chunk1", succeeded=False),
        ]

        mock_client = AsyncMock()
        mock_client.merge_or_upload_documents = AsyncMock(return_value=mock_result)
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        result = await adapter.upsert_documents("test-index", sample_vector_documents)

        assert len(result) == 1
        assert "file1_chunk0" in result
        assert "file1_chunk1" not in result

    async def test_upsert_documents_index_not_found(self, adapter, sample_vector_documents):
        """Test upsert when index doesn't exist."""
        mock_client = AsyncMock()
        mock_client.merge_or_upload_documents = AsyncMock(
            side_effect=HttpResponseError(
                message="Index not found", response=Mock(status_code=404)
            )
        )
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        with pytest.raises(IndexNotFoundError):
            await adapter.upsert_documents("test-index", sample_vector_documents)

    async def test_delete_documents_success(self, adapter):
        """Test successful document deletion."""
        mock_result = [
            Mock(key="doc1", succeeded=True),
            Mock(key="doc2", succeeded=True),
        ]

        mock_client = AsyncMock()
        mock_client.delete_documents = AsyncMock(return_value=mock_result)
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        result = await adapter.delete_documents("test-index", ["doc1", "doc2"])

        assert result is True
        mock_client.delete_documents.assert_called_once()

    async def test_delete_by_file_id_success(self, adapter):
        """Test successful deletion by file_id."""
        # Mock search results
        async def mock_search_results():
            yield {"id": "file1_chunk0"}
            yield {"id": "file1_chunk1"}

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_search_results())
        mock_client.delete_documents = AsyncMock(
            return_value=[Mock(succeeded=True), Mock(succeeded=True)]
        )
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        result = await adapter.delete_by_file_id("test-index", "file1")

        assert result == 2
        mock_client.search.assert_called_once()
        mock_client.delete_documents.assert_called_once()

    async def test_search_success(self, adapter):
        """Test successful vector search."""
        # Mock search results
        async def mock_search_results():
            yield {
                "chunkId": "chunk0",
                "fileId": "file1",
                "content": "test content",
                "@search.score": 0.95,
                "metadata": {"model_version": "v1"},
            }

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_search_results())
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        query_vector = [0.1] * 1536
        results = await adapter.search("test-index", query_vector=query_vector, top_k=10)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].chunk_id == "chunk0"
        assert results[0].file_id == "file1"
        assert results[0].score == 0.95
        mock_client.search.assert_called_once()

    async def test_search_with_filters(self, adapter):
        """Test vector search with promoted metadata filters."""
        async def mock_search_results():
            yield {
                "chunkId": "chunk0",
                "fileId": "file1",
                "content": "test",
                "@search.score": 0.9,
                "metadata": {"sector": "TRANSPORT"},
            }

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_search_results())
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        query_vector = [0.1] * 1536
        filters = {"file_ids": ["file1"], "sector": "TRANSPORT"}

        results = await adapter.search("test-index", query_vector=query_vector, top_k=5, filters=filters)

        assert len(results) == 1
        # Verify filter was applied
        call_args = mock_client.search.call_args
        assert call_args.kwargs["filter"] is not None
        assert "metadata/sector eq 'TRANSPORT'" in call_args.kwargs["filter"]

    async def test_health_check_success(self, adapter):
        """Test successful health check."""
        async def mock_list_indexes():
            yield Mock(name="index1")

        adapter._client_wrapper.index_client.list_indexes = Mock(
            return_value=mock_list_indexes()
        )

        result = await adapter.health_check()

        assert result is True

    async def test_health_check_failure(self, adapter):
        """Test health check failure."""
        adapter._client_wrapper.index_client.list_indexes = Mock(
            side_effect=Exception("Connection failed")
        )

        result = await adapter.health_check()

        assert result is False

    async def test_ensure_index_exists(self, adapter):
        """Test ensure_index when index exists."""
        adapter._client_wrapper.index_client.get_index = AsyncMock(return_value=Mock())

        result = await adapter.ensure_index("test-index")

        assert result is True
        adapter._client_wrapper.index_client.get_index.assert_called_once_with("test-index")

    async def test_ensure_index_creates_new(self, adapter):
        """Test ensure_index creates index when it doesn't exist."""
        adapter._client_wrapper.index_client.get_index = AsyncMock(
            side_effect=ResourceNotFoundError("Index not found")
        )
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        result = await adapter.ensure_index("test-index", {"vector_dimension": 1536})

        assert result is True
        adapter._client_wrapper.index_client.create_or_update_index.assert_called_once()

    async def test_close(self, adapter):
        """Test closing the adapter."""
        adapter._client_wrapper.close = AsyncMock()

        await adapter.close()

        adapter._client_wrapper.close.assert_called_once()

    async def test_context_manager(self, mock_settings):
        """Test adapter as async context manager."""
        with patch(
            "src.infrastructure.azure.adapters.vector_search_azure.SearchClientWrapper"
        ) as mock_wrapper_class:
            # Make the wrapper instance async-compatible
            mock_wrapper_instance = AsyncMock()
            mock_wrapper_class.return_value = mock_wrapper_instance

            async with AzureAISearchAdapter(mock_settings) as adapter:
                assert adapter is not None

            # Verify close was called on exit
            mock_wrapper_instance.close.assert_called_once()

    def test_repr(self, adapter):
        """Test string representation."""
        repr_str = repr(adapter)
        assert "AzureAISearchAdapter" in repr_str
        assert "https://test.search.windows.net" in repr_str

    def test_create_index_fields_includes_promoted_metadata(self, adapter):
        """Test that index schema includes all promoted metadata fields."""
        fields = adapter._create_index_fields(vector_dimension=1536, document_category="operational")

        # Find metadata ComplexField
        metadata_field = next(f for f in fields if f.name == "metadata")
        metadata_field_names = {f.name for f in metadata_field.fields}

        # Verify promoted fields are present
        expected_promoted_fields = {
            "ezshare_id",
            "operation_number",
            "document_name",
            "document_author",
            "disclosed",
            "country",
            "operation_type",
            "dept_id",
            "sector",
            "year",
            "file_extension",
            "access_to_information_policy",
            "document_publish_date",
            "document_approval_date",
            "has_table",
            "table_id",
            "section_path",
        }

        for field in expected_promoted_fields:
            assert field in metadata_field_names, f"Field '{field}' not found in metadata"

    def test_create_index_fields_correct_types(self, adapter):
        """Test that promoted fields have correct data types."""
        from azure.search.documents.indexes.models import SearchFieldDataType

        fields = adapter._create_index_fields(vector_dimension=1536, document_category="operational")
        metadata_field = next(f for f in fields if f.name == "metadata")

        # Create a mapping of field name to field object
        metadata_fields_map = {f.name: f for f in metadata_field.fields}

        # Verify types
        assert metadata_fields_map["operation_number"].type == SearchFieldDataType.String
        assert metadata_fields_map["year"].type == SearchFieldDataType.Int32
        assert metadata_fields_map["disclosed"].type == SearchFieldDataType.Boolean
        assert (
            metadata_fields_map["document_publish_date"].type
            == SearchFieldDataType.DateTimeOffset
        )
        assert metadata_fields_map["has_table"].type == SearchFieldDataType.Boolean
        assert metadata_fields_map["table_id"].type == SearchFieldDataType.String
        assert metadata_fields_map["section_path"].type == SearchFieldDataType.String

    def test_create_index_fields_filterable_attributes(self, adapter):
        """Test that promoted fields are marked as filterable."""
        fields = adapter._create_index_fields(vector_dimension=1536, document_category="operational")
        metadata_field = next(f for f in fields if f.name == "metadata")
        metadata_fields_map = {f.name: f for f in metadata_field.fields}

        # All promoted fields should be filterable
        filterable_fields = [
            "operation_number",
            "sector",
            "country",
            "disclosed",
            "year",
            "document_author",
            "has_table",
            "table_id",
            "section_path",
        ]

        for field_name in filterable_fields:
            assert (
                metadata_fields_map[field_name].filterable
            ), f"Field '{field_name}' should be filterable"

    def test_create_index_fields_sortable_attributes(self, adapter):
        """Test that specific promoted fields are marked as sortable.

        Sortable fields are defined in the Index Schema Registry.
        """
        fields = adapter._create_index_fields(vector_dimension=1536, document_category="operational")
        metadata_field = next(f for f in fields if f.name == "metadata")
        metadata_fields_map = {f.name: f for f in metadata_field.fields}

        # These fields should be sortable (as defined in index_schemas)
        sortable_fields = [
            "operation_number",
            "document_name",
            "country",
            "sector",
            "year",
            "page_number",
            "document_publish_date",
            "document_approval_date",
        ]

        for field_name in sortable_fields:
            assert (
                metadata_fields_map[field_name].sortable
            ), f"Field '{field_name}' should be sortable"

    def test_build_filter_string_operation_number(self, adapter):
        """Test OData filter for operation_number."""
        filters = {"operation_number": "UR-P1180"}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/operation_number eq 'UR-P1180'"

    def test_build_filter_string_sector(self, adapter):
        """Test OData filter for sector."""
        filters = {"sector": "TRANSPORT"}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/sector eq 'TRANSPORT'"

    def test_build_filter_string_sector_list(self, adapter):
        """Test OData filter for multiple sectors."""
        filters = {"sector": ["TRANSPORT", "ENERGY"]}
        filter_string = adapter._build_filter_string(filters)
        assert (
            filter_string
            == "(metadata/sector eq 'TRANSPORT' or metadata/sector eq 'ENERGY')"
        )

    def test_build_filter_string_disclosed_boolean(self, adapter):
        """Test OData filter for disclosed (boolean)."""
        filters = {"disclosed": True}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/disclosed eq true"

        filters = {"disclosed": False}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/disclosed eq false"

    def test_build_filter_string_year_exact(self, adapter):
        """Test OData filter for exact year."""
        filters = {"year": 2024}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/year eq 2024"

    def test_build_filter_string_year_range(self, adapter):
        """Test OData filter for year range."""
        filters = {"year_min": 2020, "year_max": 2024}
        filter_string = adapter._build_filter_string(filters)
        assert "metadata/year ge 2020" in filter_string
        assert "metadata/year le 2024" in filter_string
        assert " and " in filter_string

    def test_build_filter_string_multiple_filters(self, adapter):
        """Test combining multiple filters with AND logic."""
        filters = {
            "operation_number": "UR-P1180",
            "sector": "TRANSPORT",
            "year": 2024,
            "disclosed": True,
        }
        filter_string = adapter._build_filter_string(filters)

        assert "metadata/operation_number eq 'UR-P1180'" in filter_string
        assert "metadata/sector eq 'TRANSPORT'" in filter_string
        assert "metadata/year eq 2024" in filter_string
        assert "metadata/disclosed eq true" in filter_string
        # Should have 3 'and' operators for 4 conditions
        assert filter_string.count(" and ") == 3

    def test_build_filter_string_file_ids_and_metadata(self, adapter):
        """Test combining file_ids (OR) with metadata filters (AND)."""
        filters = {
            "file_ids": ["file1", "file2"],
            "sector": "TRANSPORT",
            "year": 2024,
        }
        filter_string = adapter._build_filter_string(filters)

        assert "(fileId eq 'file1' or fileId eq 'file2')" in filter_string
        assert "metadata/sector eq 'TRANSPORT'" in filter_string
        assert "metadata/year eq 2024" in filter_string

    def test_build_filter_string_document_author(self, adapter):
        """Test search.ismatch() for document_author partial matching."""
        filters = {"document_author": "John Doe"}
        filter_string = adapter._build_filter_string(filters)
        assert "search.ismatch('John Doe', 'metadata/document_author')" in filter_string

    def test_build_filter_string_file_extension(self, adapter):
        """Test file extension filter with dot normalization."""
        filters = {"file_extension": "pdf"}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/file_extension eq '.pdf'"

        filters = {"file_extension": ".docx"}
        filter_string = adapter._build_filter_string(filters)
        assert filter_string == "metadata/file_extension eq '.docx'"

    def test_build_filter_string_empty(self, adapter):
        """Test no filter string when filters dict is empty."""
        filter_string = adapter._build_filter_string({})
        assert filter_string is None

        filter_string = adapter._build_filter_string(None)
        assert filter_string is None

    def test_build_filter_string_date_range(self, adapter):
        """Test date range filtering for document_publish_date."""
        filters = {
            "document_publish_date_from": "2024-01-01T00:00:00Z",
            "document_publish_date_to": "2024-12-31T23:59:59Z",
        }
        filter_string = adapter._build_filter_string(filters)

        assert "metadata/document_publish_date ge 2024-01-01T00:00:00Z" in filter_string
        assert "metadata/document_publish_date le 2024-12-31T23:59:59Z" in filter_string
