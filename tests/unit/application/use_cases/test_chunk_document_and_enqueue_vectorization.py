"""Unit tests for ChunkDocumentAndEnqueueVectorizationUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.chunking import ChunkDocumentRequest, ChunkDocumentResult
from src.application.dto.document_analysis import ProcessingStatus
from src.application.use_cases.chunk_document_and_enqueue_vectorization import (
    ChunkDocumentAndEnqueueVectorizationUseCase,
)


@pytest.fixture
def chunk_and_enqueue_vectorization_use_case() -> (
    ChunkDocumentAndEnqueueVectorizationUseCase
):
    """Create a ChunkDocumentAndEnqueueVectorizationUseCase with mock dependencies."""
    chunk_use_case = MagicMock()
    queue_publisher = MagicMock()
    pipeline_store = MagicMock()

    chunk_use_case.execute = AsyncMock()
    queue_publisher.publish = AsyncMock()
    pipeline_store.get_by_id = AsyncMock()

    return ChunkDocumentAndEnqueueVectorizationUseCase(
        chunk_use_case=chunk_use_case,
        queue_publisher=queue_publisher,
        queue_name="chunk-to-vector",
        pipeline_store=pipeline_store,
        embedding_output_container="embeddings",
        embedding_model="text-embedding-3-small",
        embedding_batch_size=64,
    )


async def test_execute_enqueues_vectorization_on_success(
    chunk_and_enqueue_vectorization_use_case: ChunkDocumentAndEnqueueVectorizationUseCase,
) -> None:
    """Ensure vectorization is enqueued when chunking completes successfully."""
    request = ChunkDocumentRequest(
        file_id="file-123",
        tenant_id="tenant-abc",
        source_container="text",
        output_container="chunks",
    )

    chunk_and_enqueue_vectorization_use_case._chunk_use_case.execute = AsyncMock(
        return_value=ChunkDocumentResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            chunk_count=5,
            chunks_url="chunks/tenant-abc/file-123/chunks/",
            chunking_strategy="fixed_size",
            correlation_id="corr-123",
            processing_time_ms=10,
        )
    )

    chunk_and_enqueue_vectorization_use_case._pipeline_store.get_by_id = AsyncMock(
        return_value=MagicMock(document=MagicMock(file_version=3))
    )

    result = await chunk_and_enqueue_vectorization_use_case.execute(request)

    assert result.status == ProcessingStatus.COMPLETED
    chunk_and_enqueue_vectorization_use_case._queue_publisher.publish.assert_called_once()
    publish_kwargs = (
        chunk_and_enqueue_vectorization_use_case._queue_publisher.publish.call_args.kwargs
    )
    assert publish_kwargs["file_version"] == 3
    assert publish_kwargs["payload"]["source_container"] == "chunks"
    assert publish_kwargs["payload"]["output_container"] == "embeddings"
    assert publish_kwargs["payload"]["embedding_model"] == "text-embedding-3-small"
    assert publish_kwargs["payload"]["batch_size"] == 64


async def test_execute_skips_enqueue_on_failure(
    chunk_and_enqueue_vectorization_use_case: ChunkDocumentAndEnqueueVectorizationUseCase,
) -> None:
    """Ensure vectorization enqueue is skipped when chunking fails."""
    request = ChunkDocumentRequest(
        file_id="file-456",
        tenant_id="tenant-xyz",
        source_container="text",
        output_container="chunks",
    )

    chunk_and_enqueue_vectorization_use_case._chunk_use_case.execute = AsyncMock(
        return_value=ChunkDocumentResult(
            file_id=request.file_id,
            status=ProcessingStatus.FAILED,
            chunk_count=0,
            correlation_id="corr-456",
            processing_time_ms=5,
            error_message="failed",
        )
    )

    result = await chunk_and_enqueue_vectorization_use_case.execute(request)

    assert result.status == ProcessingStatus.FAILED
    chunk_and_enqueue_vectorization_use_case._queue_publisher.publish.assert_not_called()
