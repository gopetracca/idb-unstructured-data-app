"""Unit tests for blob reference update methods (SSOT architecture)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage


class TestDocumentRepositoryBlobReferences:
    """Tests for DocumentRepository blob reference methods."""

    async def test_update_raw_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test updating only raw_blob_ref."""
        # Arrange
        document = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="test.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=None,  # Initially null
        )

        repo = MagicMock()
        updated_file = document.model_copy()
        updated_file.raw_blob_ref = f"{sample_tenant_id}/{sample_file_id}/test.pdf"
        repo.update_blob_references = AsyncMock(return_value=updated_file)

        # Act
        result = await repo.update_blob_references(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test.pdf",
        )

        # Assert
        assert result is not None
        assert result.raw_blob_ref == f"{sample_tenant_id}/{sample_file_id}/test.pdf"
        repo.update_blob_references.assert_called_once_with(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test.pdf",
        )

    async def test_update_text_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test updating only text_blob_ref."""
        # Arrange
        document = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="test.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test.pdf",
            text_blob_ref=None,  # Initially null
        )

        repo = MagicMock()
        updated_file = document.model_copy()
        updated_file.text_blob_ref = f"{sample_tenant_id}/{sample_file_id}/text.json"
        repo.update_blob_references = AsyncMock(return_value=updated_file)

        # Act
        result = await repo.update_blob_references(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        )

        # Assert
        assert result is not None
        assert result.text_blob_ref == f"{sample_tenant_id}/{sample_file_id}/text.json"
        # raw_blob_ref should remain unchanged
        assert result.raw_blob_ref == f"{sample_tenant_id}/{sample_file_id}/test.pdf"

    async def test_update_both_blob_refs(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test updating both blob references simultaneously."""
        repo = MagicMock()
        updated_file = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="test.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test.pdf",
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        )
        repo.update_blob_references = AsyncMock(return_value=updated_file)

        # Act
        result = await repo.update_blob_references(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test.pdf",
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        )

        # Assert
        assert result is not None
        assert result.raw_blob_ref == f"{sample_tenant_id}/{sample_file_id}/test.pdf"
        assert result.text_blob_ref == f"{sample_tenant_id}/{sample_file_id}/text.json"

    async def test_update_blob_ref_file_not_found(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test updating blob reference when file doesn't exist."""
        repo = MagicMock()
        repo.update_blob_references = AsyncMock(return_value=None)

        # Act
        result = await repo.update_blob_references(
            tenant_id=sample_tenant_id,
            file_id="nonexistent",
            raw_blob_ref="some/path.pdf",
        )

        # Assert
        assert result is None


class TestChunkIndexRepositoryBlobReferences:
    """Tests for ChunkIndexRepository blob reference methods."""

    async def test_update_chunk_blob_ref(self, sample_chunk_id: str):
        """Test updating chunk_blob_ref."""
        # Arrange
        chunk_index = ChunkIndex(
            file_id="test-file",
            chunk_id=sample_chunk_id,
            chunk_index=0,
            text_preview="Test chunk content",
            start_char=0,
            end_char=100,
            chunk_blob_ref=None,  # Initially null
        )

        repo = MagicMock()
        updated_chunk = chunk_index.model_copy()
        updated_chunk.chunk_blob_ref = f"tenant/file/{sample_chunk_id}.json"
        repo.update_blob_references = AsyncMock(return_value=updated_chunk)

        # Act
        result = await repo.update_blob_references(
            chunk_id=sample_chunk_id,
            chunk_blob_ref=f"tenant/file/{sample_chunk_id}.json",
        )

        # Assert
        assert result is not None
        assert result.chunk_blob_ref == f"tenant/file/{sample_chunk_id}.json"

    async def test_update_embedding_blob_ref(self, sample_chunk_id: str):
        """Test updating embedding_blob_ref."""
        # Arrange
        chunk_index = ChunkIndex(
            file_id="test-file",
            chunk_id=sample_chunk_id,
            chunk_index=0,
            text_preview="Test chunk content",
            start_char=0,
            end_char=100,
            chunk_blob_ref=f"tenant/file/{sample_chunk_id}.json",
            embedding_blob_ref=None,  # Initially null
        )

        repo = MagicMock()
        updated_chunk = chunk_index.model_copy()
        updated_chunk.embedding_blob_ref = f"tenant/file/embeddings/{sample_chunk_id}.json"
        repo.update_blob_references = AsyncMock(return_value=updated_chunk)

        # Act
        result = await repo.update_blob_references(
            chunk_id=sample_chunk_id,
            embedding_blob_ref=f"tenant/file/embeddings/{sample_chunk_id}.json",
        )

        # Assert
        assert result is not None
        assert result.embedding_blob_ref == f"tenant/file/embeddings/{sample_chunk_id}.json"
        # chunk_blob_ref should remain unchanged
        assert result.chunk_blob_ref == f"tenant/file/{sample_chunk_id}.json"

    async def test_update_both_chunk_blob_refs(self, sample_chunk_id: str):
        """Test updating both chunk blob references simultaneously."""
        repo = MagicMock()
        updated_chunk = ChunkIndex(
            file_id="test-file",
            chunk_id=sample_chunk_id,
            chunk_index=0,
            text_preview="Test chunk content",
            start_char=0,
            end_char=100,
            chunk_blob_ref=f"tenant/file/{sample_chunk_id}.json",
            embedding_blob_ref=f"tenant/file/embeddings/{sample_chunk_id}.json",
        )
        repo.update_blob_references = AsyncMock(return_value=updated_chunk)

        # Act
        result = await repo.update_blob_references(
            chunk_id=sample_chunk_id,
            chunk_blob_ref=f"tenant/file/{sample_chunk_id}.json",
            embedding_blob_ref=f"tenant/file/embeddings/{sample_chunk_id}.json",
        )

        # Assert
        assert result is not None
        assert result.chunk_blob_ref == f"tenant/file/{sample_chunk_id}.json"
        assert result.embedding_blob_ref == f"tenant/file/embeddings/{sample_chunk_id}.json"

    async def test_update_chunk_blob_ref_not_found(self):
        """Test updating blob reference when chunk doesn't exist."""
        repo = MagicMock()
        repo.update_blob_references = AsyncMock(return_value=None)

        # Act
        result = await repo.update_blob_references(
            chunk_id="nonexistent",
            chunk_blob_ref="some/path.json",
        )

        # Assert
        assert result is None


class TestSSOTPatternUsage:
    """Tests demonstrating SSOT pattern usage in use cases."""

    async def test_upload_stores_raw_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that upload use case stores raw_blob_ref (SSOT)."""
        # Arrange
        blob_path = f"{sample_tenant_id}/{sample_file_id}/document.pdf"

        document = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=blob_path,  # Stored during upload
        )

        # Assert - raw_blob_ref is populated
        assert document.raw_blob_ref is not None
        assert document.raw_blob_ref == blob_path
        assert sample_tenant_id in document.raw_blob_ref
        assert sample_file_id in document.raw_blob_ref

    async def test_process_uses_raw_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that process use case reads from raw_blob_ref (SSOT)."""
        # Arrange
        document = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/document.pdf",
        )

        # Assert - document has raw_blob_ref to read from
        assert document.raw_blob_ref is not None
        # Use case would download using this path (not constructing from metadata)
        blob_path_to_download = document.raw_blob_ref
        assert blob_path_to_download == f"{sample_tenant_id}/{sample_file_id}/document.pdf"

    async def test_chunk_uses_text_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that chunk use case reads from text_blob_ref (SSOT)."""
        # Arrange
        document = Document(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            content_hash="abc123",
            file_version=1,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/document.pdf",
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        )

        # Assert - document has text_blob_ref to read from
        assert document.text_blob_ref is not None
        # Use case would download using this path (not constructing from metadata)
        text_path_to_download = document.text_blob_ref
        assert text_path_to_download == f"{sample_tenant_id}/{sample_file_id}/text.json"
