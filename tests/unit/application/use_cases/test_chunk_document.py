"""Unit tests for ChunkDocumentUseCase."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.chunking import ChunkDocumentRequest
from src.application.dto.document_analysis import ProcessingStatus
from src.application.use_cases.chunk_document import ChunkDocumentUseCase
from src.core.entities.chunk import Chunk, ChunkMetadata
from src.core.entities.composites import DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.errors import (
    ChunkingError,
    DocumentNotFoundError,
    InvalidChunkingStrategyError,
    TextNotFoundError,
)
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName


@pytest.fixture
def mock_chunker() -> MagicMock:
    """Create a mock ChunkerPort."""
    chunker = MagicMock()
    chunker.chunk_text = AsyncMock(
        return_value=[
            Chunk(
                file_id="test-file",
                chunk_id="test-file_chunk_0",
                chunk_index=0,
                text="First chunk content",
                start_char=0,
                end_char=19,
                metadata=ChunkMetadata(),
            ),
            Chunk(
                file_id="test-file",
                chunk_id="test-file_chunk_1",
                chunk_index=1,
                text="Second chunk content",
                start_char=19,
                end_char=39,
                metadata=ChunkMetadata(),
            ),
        ]
    )
    chunker.get_supported_strategies = MagicMock(
        return_value=[ChunkingStrategyName.FIXED_SIZE]
    )
    chunker.is_strategy_supported = MagicMock(return_value=True)
    return chunker


@pytest.fixture
def mock_pipeline_store() -> MagicMock:
    """Create a mock PipelineStorePort."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(
        return_value=DocumentWithPipeline(
            document=Document(
                tenant_id="default",
                file_id="test-file",
                blob_name="document.pdf",
                content_type="application/pdf",
                size_bytes=1000,
                content_hash="abc123",
                file_version=1,
                collection_name="test-collection",
                # Blob storage references (SSOT for content location)
                raw_blob_ref="default/test-file/document.pdf",
                text_blob_ref="default/test-file/text.json",
            ),
            pipeline=PipelineState(
                file_id="test-file",
                current_stage=ProcessingStage.CONVERT,
                overall_status=OverallStatus.PROCESSING,
            ),
        )
    )
    repo.mark_processing = AsyncMock()
    repo.mark_failed = AsyncMock()
    repo.update_chunk_counts = AsyncMock()
    return repo


@pytest.fixture
def mock_chunk_index_repository() -> MagicMock:
    """Create a mock ChunkIndexRepository."""
    repo = MagicMock()
    repo.delete_by_file = AsyncMock()
    repo.batch_create = AsyncMock()
    return repo


@pytest.fixture
def chunk_document_use_case(
    mock_blob_client: MagicMock,
    mock_chunker: MagicMock,
    mock_chunk_index_repository: MagicMock,
    mock_pipeline_store: MagicMock,
) -> ChunkDocumentUseCase:
    """Create a ChunkDocumentUseCase with mocked dependencies."""
    return ChunkDocumentUseCase(
        blob_client=mock_blob_client,
        chunker=mock_chunker,
        chunk_index_repository=mock_chunk_index_repository,
        pipeline_store=mock_pipeline_store,
    )


class TestChunkDocumentUseCase:
    """Tests for ChunkDocumentUseCase."""

    async def test_execute_success(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_chunker: MagicMock,
    ):
        """Test successful document chunking."""
        # Setup
        text_data = {
            "extracted_text": "This is the extracted text content for chunking.",
            "file_id": "test-file",
        }
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        # Execute
        result = await chunk_document_use_case.execute(request)

        # Assert
        assert result.file_id == "test-file"
        assert result.status == ProcessingStatus.COMPLETED
        assert result.chunk_count == 2
        assert result.chunking_strategy == "fixed_size"
        assert result.correlation_id is not None
        assert result.processing_time_ms is not None

    async def test_execute_with_custom_strategy(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
    ):
        """Test chunking with custom strategy."""
        text_data = {"extracted_text": "Custom strategy test content."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
            chunking_strategy=ChunkingStrategy.fixed_size(
                chunk_size=256,
                chunk_overlap=25,
            ),
        )

        result = await chunk_document_use_case.execute(request)

        assert result.status == ProcessingStatus.COMPLETED
        assert result.chunking_strategy == "fixed_size"

    async def test_execute_document_not_found(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_pipeline_store: MagicMock,
    ):
        """Test error when document not found."""
        mock_pipeline_store.get_by_id = AsyncMock(return_value=None)

        request = ChunkDocumentRequest(
            file_id="nonexistent-file",
            tenant_id="default",
        )

        with pytest.raises(DocumentNotFoundError) as exc_info:
            await chunk_document_use_case.execute(request)

        assert "nonexistent-file" in str(exc_info.value)

    async def test_execute_text_not_found(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
    ):
        """Test error when extracted text not found."""
        mock_blob_client.blob_exists = AsyncMock(return_value=False)

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        with pytest.raises(TextNotFoundError) as exc_info:
            await chunk_document_use_case.execute(request)

        assert "test-file" in str(exc_info.value)

    async def test_execute_invalid_strategy(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_chunker: MagicMock,
    ):
        """Test error with invalid chunking strategy."""
        text_data = {"extracted_text": "Some content."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )
        mock_chunker.is_strategy_supported = MagicMock(return_value=False)

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
            chunking_strategy=ChunkingStrategy(
                strategy_name=ChunkingStrategyName.SEMANTIC,
            ),
        )

        with pytest.raises(InvalidChunkingStrategyError):
            await chunk_document_use_case.execute(request)

    async def test_execute_empty_text(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
    ):
        """Test error when extracted text is empty."""
        text_data = {"extracted_text": ""}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        with pytest.raises(ChunkingError) as exc_info:
            await chunk_document_use_case.execute(request)

        assert "No text content" in str(exc_info.value)

    async def test_execute_requires_extracted_text_field(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
    ):
        """Test failure when extracted_text is missing."""
        text_data = {
            "markdown": "# Title\n\nMarkdown content to chunk.",
        }
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        with pytest.raises(ChunkingError) as exc_info:
            await chunk_document_use_case.execute(request)
        assert "No text content" in str(exc_info.value)

    async def test_execute_stores_chunks(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_chunk_index_repository: MagicMock,
    ):
        """Test that chunks are stored correctly."""
        text_data = {"extracted_text": "Content to chunk."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        await chunk_document_use_case.execute(request)

        # Verify blobs were uploaded
        assert mock_blob_client.upload_blob.call_count == 2  # 2 chunks

        # Verify chunk index entries were created
        mock_chunk_index_repository.batch_create.assert_called_once()
        call_args = mock_chunk_index_repository.batch_create.call_args
        chunk_indices = call_args.args[0]
        assert len(chunk_indices) == 2

    async def test_execute_deletes_existing_chunks(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_chunk_index_repository: MagicMock,
    ):
        """Test that existing chunks are deleted before creating new ones."""
        text_data = {"extracted_text": "Content to chunk."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        await chunk_document_use_case.execute(request)

        # Verify delete was called before batch_create
        mock_chunk_index_repository.delete_by_file.assert_called_once()

    async def test_execute_updates_file_index(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_pipeline_store: MagicMock,
    ):
        """Test that file index is updated with chunk count."""
        text_data = {"extracted_text": "Content to chunk."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        await chunk_document_use_case.execute(request)

        mock_pipeline_store.update_chunk_counts.assert_called_once_with(
            tenant_id="default",
            file_id="test-file",
            chunk_count=2,
        )

    async def test_execute_marks_processing_status(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_pipeline_store: MagicMock,
    ):
        """Test that processing status is marked."""
        text_data = {"extracted_text": "Content to chunk."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        await chunk_document_use_case.execute(request)

        mock_pipeline_store.mark_processing.assert_called_once_with(
            "default", "test-file", ProcessingStage.CHUNK
        )

    async def test_store_chunks_populates_metadata_json(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_chunk_index_repository: MagicMock,
        mock_chunker: MagicMock,
    ):
        """metadata_json on each ChunkIndex must contain the chunk's metadata."""
        mock_chunker.chunk_text = AsyncMock(
            return_value=[
                Chunk(
                    file_id="test-file",
                    chunk_id="test-file_chunk_0",
                    chunk_index=0,
                    text="Text chunk",
                    start_char=0,
                    end_char=10,
                    metadata=ChunkMetadata(
                        has_table=False,
                        token_count=5,
                        chunking_strategy="fixed_size",
                        chunk_size=512,
                        section_path=["Introduction"],
                    ),
                ),
                Chunk(
                    file_id="test-file",
                    chunk_id="test-file_chunk_1",
                    chunk_index=1,
                    text="<table><tr><td>cell</td></tr></table>",
                    start_char=10,
                    end_char=46,
                    metadata=ChunkMetadata(
                        has_table=True,
                        table_id="table_0",
                        token_count=12,
                        chunking_strategy="fixed_size",
                        chunk_size=512,
                    ),
                ),
            ]
        )

        text_data = {"extracted_text": "Some content with a table."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )

        request = ChunkDocumentRequest(file_id="test-file", tenant_id="default")
        await chunk_document_use_case.execute(request)

        mock_chunk_index_repository.batch_create.assert_called_once()
        chunk_indices = mock_chunk_index_repository.batch_create.call_args.args[0]

        text_meta = chunk_indices[0].metadata_json
        assert text_meta["has_table"] is False
        assert text_meta["token_count"] == 5
        assert text_meta["chunking_strategy"] == "fixed_size"
        assert text_meta["chunk_size"] == 512
        assert text_meta["section_path"] == ["Introduction"]

        table_meta = chunk_indices[1].metadata_json
        assert table_meta["has_table"] is True
        assert table_meta["table_id"] == "table_0"
        assert table_meta["token_count"] == 12

    async def test_execute_error_marks_failed(
        self,
        chunk_document_use_case: ChunkDocumentUseCase,
        mock_blob_client: MagicMock,
        mock_pipeline_store: MagicMock,
        mock_chunker: MagicMock,
    ):
        """Test that file is marked as failed on error."""
        text_data = {"extracted_text": "Content to chunk."}
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(text_data).encode()
        )
        mock_chunker.chunk_text = AsyncMock(side_effect=Exception("Chunking failed"))

        request = ChunkDocumentRequest(
            file_id="test-file",
            tenant_id="default",
        )

        with pytest.raises(ChunkingError):
            await chunk_document_use_case.execute(request)

        mock_pipeline_store.mark_failed.assert_called_once()
