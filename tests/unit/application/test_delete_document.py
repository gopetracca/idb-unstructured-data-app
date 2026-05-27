"""Unit tests for DeleteDocumentUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock, call

import pytest

from src.application.dto.document_dto import DeleteDocumentInput
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import PipelineState
from src.core.errors import DocumentNotFoundError, IndexNotFoundError, StorageError
from src.core.value_objects.document_metadata import DocumentMetadata


@pytest.fixture
def sample_document_complete() -> DocumentComplete:
    """Create a sample DocumentComplete for testing."""
    return DocumentComplete(
        document=Document(
            tenant_id="tenant-123",
            file_id="file-456",
            blob_name="test-doc.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            collection_name="test-collection",
        ),
        pipeline=PipelineState(file_id="file-456"),
        metadata=DocumentMetadata(file_id="file-456"),
    )


@pytest.fixture
def mock_blob_store() -> AsyncMock:
    """Create mock blob store."""
    mock = AsyncMock()
    mock.delete_by_prefix = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def mock_metadata_store(sample_document_complete: DocumentComplete) -> AsyncMock:
    """Create mock metadata store."""
    mock = AsyncMock()
    mock.get_by_id = AsyncMock(return_value=sample_document_complete)
    mock.delete = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_vector_database() -> AsyncMock:
    """Create mock vector database."""
    mock = AsyncMock()
    mock.delete_by_file_id = AsyncMock(return_value=5)
    return mock


@pytest.fixture
def use_case(
    mock_blob_store: AsyncMock,
    mock_metadata_store: AsyncMock,
    mock_vector_database: AsyncMock,
) -> DeleteDocumentUseCase:
    """Create use case with mocks."""
    return DeleteDocumentUseCase(
        blob_store=mock_blob_store,
        metadata_store=mock_metadata_store,
        vector_database=mock_vector_database,
        container_raw="raw",
        container_text="text",
        container_chunks="chunks",
        container_embeddings="embeddings",
        index_name="test-index",
    )


class TestDeleteDocumentUseCase:
    """Tests for DeleteDocumentUseCase."""

    async def test_successful_deletion(
        self,
        use_case: DeleteDocumentUseCase,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
        mock_vector_database: AsyncMock,
    ) -> None:
        """Test successful document deletion across all storage layers."""
        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        assert result.filename == "test-doc.pdf"
        assert result.message == "Document successfully deleted"
        assert result.deleted_at is not None

        # All four blob containers must be cleaned up
        expected_prefix = "tenant-123/file-456/"
        mock_blob_store.delete_by_prefix.assert_has_calls(
            [
                call("raw", expected_prefix),
                call("text", expected_prefix),
                call("chunks", expected_prefix),
                call("embeddings", expected_prefix),
            ],
            any_order=False,
        )
        assert mock_blob_store.delete_by_prefix.call_count == 4

        # Vector index must be cleaned up using the document's own collection
        mock_vector_database.delete_by_file_id.assert_called_once_with(
            "test-collection", "file-456"
        )

        # SQL metadata must be deleted
        mock_metadata_store.get_by_id.assert_called_once_with("tenant-123", "file-456")
        mock_metadata_store.delete.assert_called_once_with("tenant-123", "file-456")

    async def test_document_not_found(
        self,
        use_case: DeleteDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test error when document not found."""
        mock_metadata_store.get_by_id.return_value = None

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="nonexistent",
        )

        with pytest.raises(DocumentNotFoundError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.file_id == "nonexistent"
        assert exc_info.value.tenant_id == "tenant-123"

    async def test_blob_deletion_failure_does_not_block_metadata_deletion(
        self,
        use_case: DeleteDocumentUseCase,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
        mock_vector_database: AsyncMock,
    ) -> None:
        """Blob failures are logged but metadata deletion still proceeds."""
        mock_blob_store.delete_by_prefix.side_effect = Exception("Blob delete failed")

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        mock_metadata_store.delete.assert_called_once_with("tenant-123", "file-456")

    async def test_vector_deletion_failure_does_not_block_metadata_deletion(
        self,
        use_case: DeleteDocumentUseCase,
        mock_vector_database: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Vector index failures are logged but metadata deletion still proceeds."""
        mock_vector_database.delete_by_file_id.side_effect = Exception(
            "Vector delete failed"
        )

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        mock_metadata_store.delete.assert_called_once_with("tenant-123", "file-456")

    async def test_metadata_deletion_failure(
        self,
        use_case: DeleteDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test StorageError when metadata deletion fails."""
        mock_metadata_store.delete.side_effect = Exception("Metadata delete failed")

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        with pytest.raises(StorageError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.operation == "delete_metadata"

    async def test_deleted_at_timestamp(
        self,
        use_case: DeleteDocumentUseCase,
    ) -> None:
        """Test that deleted_at timestamp is set correctly."""
        before_delete = datetime.utcnow()

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.deleted_at >= before_delete

    async def test_missing_vector_index_does_not_block_metadata_deletion(
        self,
        use_case: DeleteDocumentUseCase,
        mock_vector_database: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """IndexNotFoundError is logged as a warning and does not block SQL cleanup."""
        mock_vector_database.delete_by_file_id.side_effect = IndexNotFoundError(
            "test-collection"
        )

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        mock_metadata_store.delete.assert_called_once_with("tenant-123", "file-456")

    async def test_falls_back_to_default_index_when_collection_name_missing(
        self,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
        mock_vector_database: AsyncMock,
        sample_document_complete: DocumentComplete,
    ) -> None:
        """When collection_name is not set on the document, fall back to the configured default index."""
        sample_document_complete.document.collection_name = None
        mock_metadata_store.get_by_id.return_value = sample_document_complete

        use_case = DeleteDocumentUseCase(
            blob_store=mock_blob_store,
            metadata_store=mock_metadata_store,
            vector_database=mock_vector_database,
            container_raw="raw",
            container_text="text",
            container_chunks="chunks",
            container_embeddings="embeddings",
            index_name="default-index",
        )

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        await use_case.execute(input_dto)

        mock_vector_database.delete_by_file_id.assert_called_once_with(
            "default-index", "file-456"
        )

    async def test_partial_blob_failure_still_attempts_all_containers(
        self,
        use_case: DeleteDocumentUseCase,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """A failure in one blob container does not skip the remaining containers."""
        call_count = 0

        async def fail_on_raw(container: str, prefix: str) -> int:
            nonlocal call_count
            call_count += 1
            if container == "raw":
                raise Exception("raw container unavailable")
            return 1

        mock_blob_store.delete_by_prefix.side_effect = fail_on_raw

        input_dto = DeleteDocumentInput(
            tenant_id="tenant-123",
            file_id="file-456",
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        assert call_count == 4  # all four containers were attempted
        mock_metadata_store.delete.assert_called_once_with("tenant-123", "file-456")
