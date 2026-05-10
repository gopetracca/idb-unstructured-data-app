"""Unit tests for AzureAISearchAdapter index creation with registry support."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from azure.search.documents.indexes.models import (
    ComplexField,
    SearchField,
    SearchFieldDataType,
)

from src.config.settings import VectorSearchSettings
from src.core.errors import VectorDatabaseError
from src.core.index_schemas import get_index_schema, list_document_types
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.fixture
def mock_settings():
    """Create mock VectorSearchSettings."""
    return VectorSearchSettings(
        endpoint="https://test.search.windows.net",
        api_key="test-api-key",
        hnsw_m=4,
        hnsw_ef_construction=400,
        hnsw_ef_search=500,
        batch_size=100,
    )


@pytest.fixture
def adapter(mock_settings):
    """Create AzureAISearchAdapter with mocked client."""
    with patch(
        "src.infrastructure.azure.adapters.vector_search_azure.SearchClientWrapper"
    ) as mock_wrapper:
        mock_wrapper.return_value = MagicMock()
        return AzureAISearchAdapter(mock_settings)


class TestCreateMetadataFields:
    """Tests for _create_metadata_fields method."""

    def test_creates_fields_for_operational(self, adapter):
        """Test creating metadata fields for operational document type."""
        fields = adapter._create_metadata_fields("operational")

        # Should be list of SearchField
        assert isinstance(fields, list)
        assert all(isinstance(f, SearchField) for f in fields)

        # Should contain operational-specific fields
        field_names = {f.name for f in fields}
        assert "operation_number" in field_names
        assert "sector" in field_names
        assert "operation_type" in field_names

        # Should contain common fields
        assert "country" in field_names
        assert "year" in field_names
        assert "document_type" in field_names

        # Should contain chunk fields
        assert "page_number" in field_names
        assert "section_path" in field_names

    def test_creates_fields_for_publication(self, adapter):
        """Test creating metadata fields for publication document type."""
        fields = adapter._create_metadata_fields("publication")

        field_names = {f.name for f in fields}

        # Should contain publication-specific fields
        assert "journal" in field_names
        assert "doi" in field_names
        assert "peer_reviewed" in field_names

        # Should contain common fields
        assert "country" in field_names
        assert "year" in field_names

        # Should NOT contain operational fields
        assert "operation_number" not in field_names
        assert "sector" not in field_names

    def test_field_count_matches_registry(self, adapter):
        """Test that field count matches registry schema."""
        for doc_type in list_document_types():
            fields = adapter._create_metadata_fields(doc_type)
            registry_schema = get_index_schema(doc_type)

            assert len(fields) == len(registry_schema)

    def test_unknown_document_type_raises_error(self, adapter):
        """Test that unknown document type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown document type"):
            adapter._create_metadata_fields("unknown_type")


class TestCreateIndexFields:
    """Tests for _create_index_fields method."""

    def test_creates_top_level_fields(self, adapter):
        """Test that top-level fields are always created."""
        fields = adapter._create_index_fields(1536, "operational")

        field_names = [f.name for f in fields]

        assert "id" in field_names
        assert "chunkId" in field_names
        assert "fileId" in field_names
        assert "content" in field_names
        assert "contentVector" in field_names
        assert "metadata" in field_names

    def test_metadata_is_complex_field(self, adapter):
        """Test that metadata is a ComplexField with nested fields."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")
        # ComplexField has a 'fields' attribute containing nested fields
        assert hasattr(metadata_field, "fields")
        assert metadata_field.fields is not None
        assert len(metadata_field.fields) > 0

    def test_vector_dimension_applied(self, adapter):
        """Test that vector dimension is applied to contentVector field."""
        fields = adapter._create_index_fields(3072, "operational")

        vector_field = next(f for f in fields if f.name == "contentVector")
        assert vector_field.vector_search_dimensions == 3072

    def test_operational_and_publication_differ(self, adapter):
        """Test that operational and publication schemas produce different field sets."""
        fields_operational = adapter._create_index_fields(1536, "operational")
        fields_publication = adapter._create_index_fields(1536, "publication")

        op_metadata = next(f for f in fields_operational if f.name == "metadata")
        pub_metadata = next(f for f in fields_publication if f.name == "metadata")

        # Schemas should have different field counts (different type-specific fields)
        op_names = {f.name for f in op_metadata.fields}
        pub_names = {f.name for f in pub_metadata.fields}
        assert op_names != pub_names

    def test_operational_schema_includes_operational_fields(self, adapter):
        """Test that operational schema includes operation-specific fields."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")
        metadata_field_names = {f.name for f in metadata_field.fields}

        assert "operation_number" in metadata_field_names
        assert "sector" in metadata_field_names
        assert "operation_type" in metadata_field_names

    def test_publication_schema_excludes_operational_fields(self, adapter):
        """Test that publication schema excludes operation-specific fields."""
        fields = adapter._create_index_fields(1536, "publication")

        metadata_field = next(f for f in fields if f.name == "metadata")
        metadata_field_names = {f.name for f in metadata_field.fields}

        assert "operation_number" not in metadata_field_names
        assert "sector" not in metadata_field_names
        assert "journal" in metadata_field_names
        assert "doi" in metadata_field_names


class TestCreateIndexWithDocumentType:
    """Tests for create_index method with document_type support."""

    @pytest.mark.asyncio
    async def test_create_index_without_document_type_raises(self, adapter):
        """Test creating index without document_type raises ValueError."""
        adapter._client_wrapper.index_client = AsyncMock()

        with pytest.raises(ValueError, match="document_type"):
            await adapter.create_index("test-index", {"vector_dimension": 1536})

    @pytest.mark.asyncio
    async def test_create_index_with_operational_document_type(self, adapter):
        """Test creating index with explicit operational document_type."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.create_index(
            "test-index",
            {"vector_dimension": 1536, "document_type": "operational"},
        )

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        index = call_args[0][0]

        # Verify metadata fields include operational fields
        metadata_field = next(f for f in index.fields if f.name == "metadata")
        metadata_field_names = {f.name for f in metadata_field.fields}

        assert "operation_number" in metadata_field_names
        assert "sector" in metadata_field_names

    @pytest.mark.asyncio
    async def test_create_index_with_publication_document_type(self, adapter):
        """Test creating index with publication document_type."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.create_index(
            "test-index",
            {"vector_dimension": 1536, "document_type": "publication"},
        )

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        index = call_args[0][0]

        # Verify metadata fields include publication fields
        metadata_field = next(f for f in index.fields if f.name == "metadata")
        metadata_field_names = {f.name for f in metadata_field.fields}

        assert "journal" in metadata_field_names
        assert "doi" in metadata_field_names
        assert "operation_number" not in metadata_field_names

        # Verify description contains correct document_type
        import json

        description = json.loads(index.description)
        assert description["document_type"] == "publication"

    @pytest.mark.asyncio
    async def test_create_index_with_invalid_document_type_raises_error(self, adapter):
        """Test creating index with invalid document_type raises ValueError."""
        adapter._client_wrapper.index_client = AsyncMock()

        with pytest.raises(ValueError, match="Unknown document_type"):
            await adapter.create_index(
                "test-index",
                {"vector_dimension": 1536, "document_type": "invalid_type"},
            )

    @pytest.mark.asyncio
    async def test_create_index_stores_embedding_model_in_description(self, adapter):
        """Test that embedding_model is stored in index description."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.create_index(
            "test-index",
            {
                "vector_dimension": 1536,
                "embedding_model": "text-embedding-3-large",
                "document_type": "operational",
            },
        )

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        index = call_args[0][0]

        import json

        description = json.loads(index.description)
        assert description["embedding_model"] == "text-embedding-3-large"
        assert description["document_type"] == "operational"


class TestIndexFieldProperties:
    """Tests for verifying field properties are correctly set."""

    def test_filterable_fields_are_filterable(self, adapter):
        """Test that fields marked filterable in registry are filterable in index."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")

        # country should be filterable
        country_field = next(f for f in metadata_field.fields if f.name == "country")
        assert country_field.filterable is True

        # blob_name should NOT be filterable
        blob_name_field = next(f for f in metadata_field.fields if f.name == "blob_name")
        assert blob_name_field.filterable is False

    def test_sortable_fields_are_sortable(self, adapter):
        """Test that fields marked sortable in registry are sortable in index."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")

        # year should be sortable
        year_field = next(f for f in metadata_field.fields if f.name == "year")
        assert year_field.sortable is True

        # page_number should be sortable
        page_number_field = next(f for f in metadata_field.fields if f.name == "page_number")
        assert page_number_field.sortable is True

    def test_boolean_fields_have_correct_type(self, adapter):
        """Test that boolean fields have Boolean type."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")

        disclosed_field = next(f for f in metadata_field.fields if f.name == "disclosed")
        assert disclosed_field.type == SearchFieldDataType.Boolean

        has_table_field = next(f for f in metadata_field.fields if f.name == "has_table")
        assert has_table_field.type == SearchFieldDataType.Boolean

    def test_integer_fields_have_correct_type(self, adapter):
        """Test that integer fields have Int32 type."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")

        year_field = next(f for f in metadata_field.fields if f.name == "year")
        assert year_field.type == SearchFieldDataType.Int32

        page_number_field = next(f for f in metadata_field.fields if f.name == "page_number")
        assert page_number_field.type == SearchFieldDataType.Int32

    def test_date_fields_have_correct_type(self, adapter):
        """Test that date fields have DateTimeOffset type."""
        fields = adapter._create_index_fields(1536, "operational")

        metadata_field = next(f for f in fields if f.name == "metadata")

        publish_date_field = next(
            f for f in metadata_field.fields if f.name == "document_publish_date"
        )
        assert publish_date_field.type == SearchFieldDataType.DateTimeOffset


class TestCreateBaseFields:
    """Tests for _create_base_fields method."""

    def test_returns_all_top_level_fields(self, adapter):
        """Test that all expected top-level fields are returned."""
        fields = adapter._create_base_fields(1536)
        field_names = {f.name for f in fields}

        assert "id" in field_names
        assert "chunkId" in field_names
        assert "fileId" in field_names
        assert "content" in field_names
        assert "contentVector" in field_names

    def test_vector_dimension_applied(self, adapter):
        """Test that the vector dimension is set on contentVector."""
        fields = adapter._create_base_fields(3072)
        vector_field = next(f for f in fields if f.name == "contentVector")
        assert vector_field.vector_search_dimensions == 3072

    def test_metadata_not_included(self, adapter):
        """Test that metadata ComplexField is NOT in base fields."""
        fields = adapter._create_base_fields(1536)
        field_names = {f.name for f in fields}
        assert "metadata" not in field_names


class TestConvenienceMethods:
    """Tests for create_operational_index and create_publication_index."""

    @pytest.mark.asyncio
    async def test_create_operational_index(self, adapter):
        """Test convenience method sets document_type=operational."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        result = await adapter.create_operational_index("ops-index")

        assert result is True
        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        created_index = call_args[0][0]

        import json
        meta = json.loads(created_index.description)
        assert meta["document_type"] == "operational"

    @pytest.mark.asyncio
    async def test_create_operational_index_custom_dimension(self, adapter):
        """Test convenience method passes through vector_dimension."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.create_operational_index("ops-index", vector_dimension=3072)

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        created_index = call_args[0][0]
        vector_field = next(f for f in created_index.fields if f.name == "contentVector")
        assert vector_field.vector_search_dimensions == 3072

    @pytest.mark.asyncio
    async def test_create_publication_index(self, adapter):
        """Test convenience method sets document_type=publication."""
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        result = await adapter.create_publication_index("pub-index")

        assert result is True
        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        created_index = call_args[0][0]

        import json
        meta = json.loads(created_index.description)
        assert meta["document_type"] == "publication"

        metadata_field = next(f for f in created_index.fields if f.name == "metadata")
        field_names = {f.name for f in metadata_field.fields}
        assert "journal" in field_names
        assert "doi" in field_names
        assert "operation_number" not in field_names


class TestGetIndexDocumentType:
    """Tests for document_type in get_index and list_indexes responses."""

    @pytest.mark.asyncio
    async def test_get_index_returns_document_type(self, adapter):
        """Test that get_index includes document_type from description."""
        import json
        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.name = "ops-index"
        mock_index.description = json.dumps(
            {"embedding_model": "text-embedding-3-small", "document_type": "operational"}
        )
        mock_index.fields = []

        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.get_index = AsyncMock(return_value=mock_index)
        adapter.get_document_count = AsyncMock(return_value=42)

        result = await adapter.get_index("ops-index")

        assert result["document_type"] == "operational"

    @pytest.mark.asyncio
    async def test_get_index_returns_none_when_description_missing(self, adapter):
        """Test that get_index returns None when description has no document_type."""
        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.name = "legacy-index"
        mock_index.description = None
        mock_index.fields = []

        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.get_index = AsyncMock(return_value=mock_index)
        adapter.get_document_count = AsyncMock(return_value=0)

        result = await adapter.get_index("legacy-index")

        assert result["document_type"] is None
        assert result["embedding_model"] is None
        assert result["vector_dimension"] is None


class TestEnsureIndexDefaultsToOperational:
    """Tests for ensure_index defaulting to operational document type."""

    @pytest.mark.asyncio
    async def test_ensure_index_creates_with_operational_default(self, adapter):
        """Test that ensure_index defaults to operational when index doesn't exist."""
        from azure.core.exceptions import ResourceNotFoundError

        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.get_index = AsyncMock(
            side_effect=ResourceNotFoundError("Not found")
        )
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.ensure_index("new-index")

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        created_index = call_args[0][0]

        import json
        meta = json.loads(created_index.description)
        assert meta["document_type"] == "operational"

    @pytest.mark.asyncio
    async def test_ensure_index_respects_provided_document_type(self, adapter):
        """Test that ensure_index uses the document_type from the provided schema."""
        from azure.core.exceptions import ResourceNotFoundError

        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.index_client.get_index = AsyncMock(
            side_effect=ResourceNotFoundError("Not found")
        )
        adapter._client_wrapper.index_client.create_or_update_index = AsyncMock()

        await adapter.ensure_index(
            "pub-index", schema={"vector_dimension": 1536, "document_type": "publication"}
        )

        call_args = adapter._client_wrapper.index_client.create_or_update_index.call_args
        created_index = call_args[0][0]

        import json
        meta = json.loads(created_index.description)
        assert meta["document_type"] == "publication"
