"""Unit tests for ManageCollectionUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.collection_dto import (
    CreateCollectionInput,
    DeleteCollectionInput,
    GetCollectionInput,
)
from src.application.use_cases.manage_collection import ManageCollectionUseCase
from src.core.errors import IndexAlreadyExistsError, IndexNotFoundError


@pytest.fixture
def mock_vector_database():
    """Create a mock vector database port."""
    return AsyncMock()


@pytest.fixture
def use_case(mock_vector_database):
    """Create ManageCollectionUseCase with mocked dependencies."""
    return ManageCollectionUseCase(vector_database=mock_vector_database)


class TestCreateCollection:
    """Tests for create_collection method."""

    async def test_create_collection_success(self, use_case, mock_vector_database):
        """Test successful collection creation."""
        # Arrange
        input_dto = CreateCollectionInput(
            tenant_id="test-tenant",
            name="test-collection",
            vector_dimension=1536,
            embedding_model="text-embedding-3-small",
            description="Test collection",
            correlation_id="test-correlation-id",
        )

        mock_vector_database.create_index.return_value = True

        # Act
        result = await use_case.create_collection(input_dto)

        # Assert
        assert result.name == "test-collection"
        assert result.vector_dimension == 1536
        assert result.embedding_model == "text-embedding-3-small"
        assert result.status == "created"
        assert result.correlation_id == "test-correlation-id"
        assert isinstance(result.created_at, datetime)

        mock_vector_database.create_index.assert_called_once_with(
            "test-collection",
            {"vector_dimension": 1536, "embedding_model": "text-embedding-3-small", "document_category": "operational"}
        )

    async def test_create_collection_already_exists(
        self, use_case, mock_vector_database
    ):
        """Test creating a collection that already exists."""
        # Arrange
        input_dto = CreateCollectionInput(
            tenant_id="test-tenant",
            name="existing-collection",
            vector_dimension=1536,
            embedding_model="text-embedding-3-small",
            description=None,
            correlation_id="test-correlation-id",
        )

        mock_vector_database.create_index.side_effect = IndexAlreadyExistsError(
            "existing-collection"
        )

        # Act & Assert
        with pytest.raises(IndexAlreadyExistsError):
            await use_case.create_collection(input_dto)


class TestListCollections:
    """Tests for list_collections method."""

    async def test_list_collections_success(self, use_case, mock_vector_database):
        """Test successful collection listing."""
        # Arrange
        mock_indexes = [
            {
                "name": "collection1",
                "vector_dimension": 1536,
                "embedding_model": "text-embedding-3-small",
                "document_count": 100,
                "created_at": datetime.utcnow(),
            },
            {
                "name": "collection2",
                "vector_dimension": 3072,
                "embedding_model": "text-embedding-3-large",
                "document_count": 200,
            },
        ]
        mock_vector_database.list_indexes.return_value = mock_indexes

        # Act
        result = await use_case.list_collections("test-tenant", "test-correlation-id")

        # Assert
        assert len(result.collections) == 2
        assert result.total_count == 2
        assert result.collections[0].name == "collection1"
        assert result.collections[0].vector_dimension == 1536
        assert result.collections[0].embedding_model == "text-embedding-3-small"
        assert result.collections[0].document_count == 100
        assert result.collections[1].name == "collection2"
        assert result.collections[1].vector_dimension == 3072
        assert result.collections[1].embedding_model == "text-embedding-3-large"
        assert result.collections[1].document_count == 200
        assert result.correlation_id == "test-correlation-id"

        mock_vector_database.list_indexes.assert_called_once()

    async def test_list_collections_empty(self, use_case, mock_vector_database):
        """Test listing collections when none exist."""
        # Arrange
        mock_vector_database.list_indexes.return_value = []

        # Act
        result = await use_case.list_collections("test-tenant", "test-correlation-id")

        # Assert
        assert len(result.collections) == 0
        assert result.total_count == 0
        assert result.correlation_id == "test-correlation-id"


class TestGetCollection:
    """Tests for get_collection method."""

    async def test_get_collection_success(self, use_case, mock_vector_database):
        """Test successful collection retrieval."""
        # Arrange
        input_dto = GetCollectionInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            correlation_id="test-correlation-id",
        )

        mock_index_info = {
            "name": "test-collection",
            "vector_dimension": 1536,
            "embedding_model": "text-embedding-3-small",
            "document_count": 500,
            "schema": {"fields": ["id", "content", "vector"]},
            "created_at": datetime.utcnow(),
            "last_updated": datetime.utcnow(),
        }
        mock_vector_database.get_index.return_value = mock_index_info

        # Act
        result = await use_case.get_collection(input_dto)

        # Assert
        assert result.name == "test-collection"
        assert result.vector_dimension == 1536
        assert result.embedding_model == "text-embedding-3-small"
        assert result.document_count == 500
        assert result.index_schema == {"fields": ["id", "content", "vector"]}
        assert result.created_at is not None
        assert result.last_updated is not None
        assert result.correlation_id == "test-correlation-id"

        mock_vector_database.get_index.assert_called_once_with("test-collection")

    async def test_get_collection_not_found(self, use_case, mock_vector_database):
        """Test getting a non-existent collection."""
        # Arrange
        input_dto = GetCollectionInput(
            tenant_id="test-tenant",
            collection_name="non-existent",
            correlation_id="test-correlation-id",
        )

        mock_vector_database.get_index.side_effect = IndexNotFoundError("non-existent")

        # Act & Assert
        with pytest.raises(IndexNotFoundError):
            await use_case.get_collection(input_dto)


class TestDeleteCollection:
    """Tests for delete_collection method."""

    async def test_delete_collection_success(self, use_case, mock_vector_database):
        """Test successful collection deletion."""
        # Arrange
        input_dto = DeleteCollectionInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            correlation_id="test-correlation-id",
        )

        mock_vector_database.get_document_count.return_value = 250
        mock_vector_database.delete_index.return_value = True

        # Act
        result = await use_case.delete_collection(input_dto)

        # Assert
        assert result.name == "test-collection"
        assert result.status == "deleted"
        assert result.documents_deleted == 250
        assert result.correlation_id == "test-correlation-id"

        mock_vector_database.get_document_count.assert_called_once_with(
            "test-collection"
        )
        mock_vector_database.delete_index.assert_called_once_with("test-collection")

    async def test_delete_collection_not_found(self, use_case, mock_vector_database):
        """Test deleting a non-existent collection."""
        # Arrange
        input_dto = DeleteCollectionInput(
            tenant_id="test-tenant",
            collection_name="non-existent",
            correlation_id="test-correlation-id",
        )

        mock_vector_database.get_document_count.side_effect = IndexNotFoundError(
            "non-existent"
        )
        mock_vector_database.delete_index.side_effect = IndexNotFoundError(
            "non-existent"
        )

        # Act & Assert
        with pytest.raises(IndexNotFoundError):
            await use_case.delete_collection(input_dto)

    async def test_delete_collection_count_error_continues(
        self, use_case, mock_vector_database
    ):
        """Test deletion continues if document count fails."""
        # Arrange
        input_dto = DeleteCollectionInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            correlation_id="test-correlation-id",
        )

        mock_vector_database.get_document_count.side_effect = Exception(
            "Count failed"
        )
        mock_vector_database.delete_index.return_value = True

        # Act
        result = await use_case.delete_collection(input_dto)

        # Assert
        assert result.name == "test-collection"
        assert result.status == "deleted"
        assert result.documents_deleted == 0  # Defaults to 0 when count fails
        assert result.correlation_id == "test-correlation-id"

        mock_vector_database.delete_index.assert_called_once_with("test-collection")
