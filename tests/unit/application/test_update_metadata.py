"""Unit tests for UpdateMetadataUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.application.dto.document_dto import UpdateMetadataInput
from src.application.use_cases.update_metadata import UpdateMetadataUseCase
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import PipelineState
from src.core.errors import DocumentNotFoundError, StorageError
from src.core.value_objects.document_metadata import DocumentMetadata

INDEX_NAME = "test-index"


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
            file_version=1,
            collection_name="test-collection",
        ),
        pipeline=PipelineState(file_id="file-456"),
        metadata=DocumentMetadata(
            file_id="file-456",
            document_type="report",
            country="Uruguay",
            year=2024,
            tags=["original"],
            document_author="Original Author",
        ),
    )


@pytest.fixture
def mock_metadata_store(sample_document_complete: DocumentComplete) -> AsyncMock:
    """Create mock metadata store."""
    mock = AsyncMock()
    mock.get_by_id = AsyncMock(return_value=sample_document_complete)
    mock.update = AsyncMock(side_effect=lambda x: x)
    return mock


@pytest.fixture
def mock_vector_database() -> AsyncMock:
    """Create mock vector database."""
    mock = AsyncMock()
    mock.update_metadata_by_file_id = AsyncMock(return_value=3)
    return mock


@pytest.fixture
def use_case(mock_metadata_store: AsyncMock, mock_vector_database: AsyncMock) -> UpdateMetadataUseCase:
    """Create use case with mocks."""
    return UpdateMetadataUseCase(
        metadata_store=mock_metadata_store,
        vector_database=mock_vector_database,
        index_name=INDEX_NAME,
    )


class TestUpdateMetadataUseCase:
    """Tests for UpdateMetadataUseCase."""

    async def test_successful_flexible_update(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test successful update of flexible metadata fields."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"tags": ["updated"], "department": "Engineering"},
        )

        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"
        assert result.filename == "test-doc.pdf"
        assert result.metadata.tags == ["updated"]
        assert result.metadata.department == "Engineering"
        # Original field preserved
        assert result.metadata.document_author == "Original Author"

        # Verify store was called
        mock_metadata_store.get_by_id.assert_called_once_with("tenant-123", "file-456")
        mock_metadata_store.update.assert_called_once()

    async def test_promoted_field_update_sets_on_metadata(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
        sample_document_complete: DocumentComplete,
    ) -> None:
        """Test that promoted field updates are routed to DocumentMetadata attributes."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"country": "Brazil", "year": 2025},
        )

        await use_case.execute(input_dto)

        # Verify promoted fields updated on DocumentMetadata
        call_args = mock_metadata_store.update.call_args
        updated_doc = call_args[0][0]
        assert updated_doc.metadata.country == "Brazil"
        assert updated_doc.metadata.year == 2025

    async def test_mixed_promoted_and_flexible_update(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test update with both promoted and flexible fields."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={
                "country": "Argentina",  # promoted
                "tags": ["new_tag"],  # flexible
                "description": "New desc",  # flexible
            },
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.update.call_args
        updated_doc = call_args[0][0]

        # All fields are SQL columns on DocumentMetadata
        assert updated_doc.metadata.country == "Argentina"
        assert updated_doc.metadata.tags == ["new_tag"]
        assert updated_doc.metadata.description == "New desc"
        # Original field preserved
        assert updated_doc.metadata.document_author == "Original Author"

    async def test_document_not_found(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test error when document not found."""
        mock_metadata_store.get_by_id.return_value = None

        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="nonexistent",
            metadata_updates={"tags": ["test"]},
        )

        with pytest.raises(DocumentNotFoundError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.file_id == "nonexistent"
        assert exc_info.value.tenant_id == "tenant-123"

    async def test_storage_error_on_update_failure(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test StorageError when update fails."""
        mock_metadata_store.update.side_effect = Exception("Update failed")

        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"tags": ["test"]},
        )

        with pytest.raises(StorageError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.operation == "update_metadata"

    async def test_partial_update_preserves_unset_fields(
        self,
        use_case: UpdateMetadataUseCase,
    ) -> None:
        """Test that partial updates don't overwrite unset fields."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"description": "New description"},
        )

        result = await use_case.execute(input_dto)

        # New field set
        assert result.metadata.description == "New description"
        # Existing fields preserved
        assert result.metadata.tags == ["original"]
        assert result.metadata.document_author == "Original Author"

    async def test_file_version_incremented(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that file version is incremented on update."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"tags": ["new"]},
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.update.call_args
        updated_doc = call_args[0][0]
        assert updated_doc.document.file_version == 2

    async def test_last_updated_timestamp_set(
        self,
        use_case: UpdateMetadataUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that last_updated timestamp is set."""
        before_update = datetime.utcnow()

        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"source": "test"},
        )

        result = await use_case.execute(input_dto)

        assert result.updated_at >= before_update

    async def test_vector_database_called_with_correct_promoted_fields(
        self,
        use_case: UpdateMetadataUseCase,
        mock_vector_database: AsyncMock,
    ) -> None:
        """Test that vector DB is updated with promoted fields after SQL update."""
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"country": "Brazil", "year": 2025},
        )

        await use_case.execute(input_dto)

        mock_vector_database.update_metadata_by_file_id.assert_called_once_with(
            "test-collection",  # doc.document.collection_name, not the default index_name
            "file-456",
            {"country": "Brazil", "year": 2025},
        )

    async def test_vector_database_error_does_not_raise(
        self,
        use_case: UpdateMetadataUseCase,
        mock_vector_database: AsyncMock,
    ) -> None:
        """Test that a vector DB failure is logged but does not propagate (best-effort)."""
        mock_vector_database.update_metadata_by_file_id.side_effect = Exception("Search unavailable")

        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"country": "Chile"},
        )

        # Must not raise — SQL update already succeeded
        result = await use_case.execute(input_dto)

        assert result.file_id == "file-456"

    async def test_vector_database_not_called_when_no_promoted_fields_updated(
        self,
        use_case: UpdateMetadataUseCase,
        mock_vector_database: AsyncMock,
        mock_metadata_store: AsyncMock,
        sample_document_complete: DocumentComplete,
    ) -> None:
        """Test that vector DB is not called when no promoted fields are in the update."""
        # Use a document type with known promoted fields; pass only a non-promoted field
        # DocumentMetadata.promoted_field_names() for "report" type will not include "unknown_field"
        input_dto = UpdateMetadataInput(
            tenant_id="tenant-123",
            file_id="file-456",
            metadata_updates={"unknown_non_promoted_field": "value"},
        )

        await use_case.execute(input_dto)

        mock_vector_database.update_metadata_by_file_id.assert_not_called()
