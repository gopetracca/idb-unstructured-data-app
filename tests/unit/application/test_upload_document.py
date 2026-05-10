"""Unit tests for UploadDocumentUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_dto import UploadDocumentInput
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import PipelineState
from src.core.errors import DuplicateDocumentError, FileSizeExceededError, InvalidFileTypeError, StorageError
from src.core.value_objects.document_metadata import DocumentMetadata


@pytest.fixture
def mock_blob_store() -> AsyncMock:
    """Create mock blob store."""
    mock = AsyncMock()
    mock.upload = AsyncMock(return_value={"etag": "test-etag"})
    mock.delete = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_metadata_store() -> AsyncMock:
    """Create mock metadata store."""
    mock = AsyncMock()
    mock.create = AsyncMock(side_effect=lambda x: x)
    mock.query_by_ezshare_id = AsyncMock(return_value=None)  # No duplicate by default
    return mock


@pytest.fixture
def use_case(mock_blob_store: AsyncMock, mock_metadata_store: AsyncMock) -> UploadDocumentUseCase:
    """Create use case with mocks."""
    return UploadDocumentUseCase(
        blob_store=mock_blob_store,
        metadata_store=mock_metadata_store,
        container_name="raw",
        allowed_types=["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        max_size_bytes=50 * 1024 * 1024,
    )


class TestUploadDocumentUseCase:
    """Tests for UploadDocumentUseCase."""

    async def test_successful_upload(
        self,
        use_case: UploadDocumentUseCase,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test successful document upload."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-001",
            filename="test-doc.pdf",
            content=b"PDF content here",
            content_type="application/pdf",
            metadata={"tags": ["test"], "source": "research"},
        )

        result = await use_case.execute(input_dto)

        assert result.filename == "test-doc.pdf"
        assert result.mime_type == "application/pdf"
        assert result.size_bytes == len(b"PDF content here")
        assert result.file_id is not None

        # Verify blob store called
        mock_blob_store.upload.assert_called_once()
        call_args = mock_blob_store.upload.call_args
        assert call_args.kwargs["container"] == "raw"
        assert "tenant-123" in call_args.kwargs["blob_path"]
        assert "test-doc.pdf" in call_args.kwargs["blob_path"]

        # Verify metadata store called
        mock_metadata_store.create.assert_called_once()

    async def test_promoted_fields_populated_at_upload(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that promoted fields from metadata are populated on DocumentComplete."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-010",
            filename="report.pdf",
            content=b"PDF content",
            content_type="application/pdf",
            metadata={
                "document_type": "operational",
                "country": "Uruguay",
                "sector": "TRANSPORT",
                "year": 2024,
                "operation_number": "UR-P1180",
                "disclosed": True,
            },
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.create.call_args
        doc_complete = call_args[0][0]

        # Promoted fields should be set on the DocumentMetadata entity
        assert doc_complete.metadata.document_type == "operational"
        assert doc_complete.metadata.country == "Uruguay"
        assert doc_complete.metadata.sector == "TRANSPORT"
        assert doc_complete.metadata.year == 2024
        assert doc_complete.metadata.operation_number == "UR-P1180"
        assert doc_complete.metadata.disclosed is True

    async def test_file_extension_auto_derived(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that file_extension is auto-derived from filename."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-011",
            filename="document.pdf",
            content=b"PDF content",
            content_type="application/pdf",
            metadata={},
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.create.call_args
        doc_complete = call_args[0][0]
        assert doc_complete.metadata.file_extension == ".pdf"

    async def test_metadata_fields_stored_as_sql_columns(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that all metadata fields (tags, source, description) are SQL columns on DocumentMetadata."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-012",
            filename="report.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={
                "country": "Brazil",
                "tags": ["test"],
                "source": "research",
                "description": "A doc",
            },
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.create.call_args
        doc_complete = call_args[0][0]

        assert doc_complete.metadata.country == "Brazil"
        assert doc_complete.metadata.tags == ["test"]
        assert doc_complete.metadata.source == "research"
        assert doc_complete.metadata.description == "A doc"

    async def test_invalid_file_type_rejected(
        self,
        use_case: UploadDocumentUseCase,
    ) -> None:
        """Test that invalid file types are rejected."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-002",
            filename="test.txt",
            content=b"text content",
            content_type="text/plain",
            metadata={},
        )

        with pytest.raises(InvalidFileTypeError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.mime_type == "text/plain"
        assert "application/pdf" in exc_info.value.allowed_types

    async def test_file_size_exceeded_rejected(
        self,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that oversized files are rejected."""
        use_case = UploadDocumentUseCase(
            blob_store=mock_blob_store,
            metadata_store=mock_metadata_store,
            max_size_bytes=100,  # Very small limit for testing
        )

        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-003",
            filename="large-file.pdf",
            content=b"x" * 200,  # 200 bytes, exceeds 100 byte limit
            content_type="application/pdf",
            metadata={},
        )

        with pytest.raises(FileSizeExceededError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.size_bytes == 200
        assert exc_info.value.max_size_bytes == 100

    async def test_blob_store_failure_raises_storage_error(
        self,
        use_case: UploadDocumentUseCase,
        mock_blob_store: AsyncMock,
    ) -> None:
        """Test that blob store failures are wrapped in StorageError."""
        mock_blob_store.upload.side_effect = Exception("Connection failed")

        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-004",
            filename="test.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={},
        )

        with pytest.raises(StorageError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.operation == "upload"
        assert "Connection failed" in exc_info.value.reason

    async def test_metadata_store_failure_cleans_up_blob(
        self,
        use_case: UploadDocumentUseCase,
        mock_blob_store: AsyncMock,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that blob is cleaned up if metadata store fails."""
        mock_metadata_store.create.side_effect = Exception("Table error")

        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-005",
            filename="test.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={},
        )

        with pytest.raises(StorageError):
            await use_case.execute(input_dto)

        # Verify cleanup was attempted
        mock_blob_store.delete.assert_called_once()

    async def test_generates_unique_file_id(
        self,
        use_case: UploadDocumentUseCase,
    ) -> None:
        """Test that unique file IDs are generated."""
        input_dto1 = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-006",
            filename="test.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={},
        )
        input_dto2 = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-007",
            filename="test.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={},
        )

        result1 = await use_case.execute(input_dto1)
        result2 = await use_case.execute(input_dto2)

        assert result1.file_id != result2.file_id

    async def test_computes_content_hash(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that content hash is computed and stored."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-008",
            filename="test.pdf",
            content=b"test content for hashing",
            content_type="application/pdf",
            metadata={},
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.create.call_args
        doc_complete = call_args[0][0]
        assert doc_complete.document.content_hash is not None
        assert len(doc_complete.document.content_hash) == 64  # SHA-256 hex length

    async def test_word_document_accepted(
        self,
        use_case: UploadDocumentUseCase,
    ) -> None:
        """Test that Word documents are accepted."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-123456789-009",
            filename="document.docx",
            content=b"docx content",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            metadata={},
        )

        result = await use_case.execute(input_dto)

        assert result.filename == "document.docx"
        assert result.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    async def test_duplicate_ezshare_id_rejected(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that duplicate ezshare_id is rejected with 409."""
        existing_doc = DocumentComplete(
            document=Document(
                tenant_id="tenant-123",
                file_id="existing-file-id",
                blob_name="existing.pdf",
                ezshare_id="EZSHARE-DUPLICATE-123",
            ),
            pipeline=PipelineState(file_id="existing-file-id"),
            metadata=DocumentMetadata(file_id="existing-file-id"),
        )
        mock_metadata_store.query_by_ezshare_id = AsyncMock(return_value=existing_doc)

        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-DUPLICATE-123",
            filename="new-doc.pdf",
            content=b"PDF content",
            content_type="application/pdf",
            metadata={},
        )

        with pytest.raises(DuplicateDocumentError) as exc_info:
            await use_case.execute(input_dto)

        assert exc_info.value.ezshare_id == "EZSHARE-DUPLICATE-123"
        assert exc_info.value.existing_file_id == "existing-file-id"

    async def test_ezshare_id_stored_in_file_index(
        self,
        use_case: UploadDocumentUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that ezshare_id is stored in the Document entity."""
        input_dto = UploadDocumentInput(
            tenant_id="tenant-123",
            collection_name="test-collection",
            ezshare_id="EZSHARE-510177122-450",
            filename="test.pdf",
            content=b"content",
            content_type="application/pdf",
            metadata={},
        )

        await use_case.execute(input_dto)

        call_args = mock_metadata_store.create.call_args
        doc_complete = call_args[0][0]
        assert doc_complete.document.ezshare_id == "EZSHARE-510177122-450"
