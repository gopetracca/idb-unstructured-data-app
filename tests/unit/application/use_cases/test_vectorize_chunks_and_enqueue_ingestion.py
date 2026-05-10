"""Unit tests for VectorizeChunksAndEnqueueIngestionUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_analysis import ProcessingStatus
from src.application.dto.embedding import VectorizeChunksRequest, VectorizeChunksResult
from src.application.use_cases.vectorize_chunks_and_enqueue_ingestion import (
    VectorizeChunksAndEnqueueIngestionUseCase,
)


@pytest.fixture
def vectorize_and_enqueue_ingestion_use_case() -> (
    VectorizeChunksAndEnqueueIngestionUseCase
):
    """Create a VectorizeChunksAndEnqueueIngestionUseCase with mock dependencies."""
    vectorize_use_case = MagicMock()
    queue_publisher = MagicMock()
    pipeline_store = MagicMock()

    vectorize_use_case.execute = AsyncMock()
    queue_publisher.publish = AsyncMock()
    pipeline_store.get_by_id = AsyncMock()

    return VectorizeChunksAndEnqueueIngestionUseCase(
        vectorize_use_case=vectorize_use_case,
        queue_publisher=queue_publisher,
        queue_name="ingest-to-db",
        pipeline_store=pipeline_store,
        batch_size=100,
    )


async def test_execute_enqueues_ingestion_on_success(
    vectorize_and_enqueue_ingestion_use_case: VectorizeChunksAndEnqueueIngestionUseCase,
) -> None:
    """Ensure ingestion is enqueued when vectorization completes successfully."""
    request = VectorizeChunksRequest(
        file_id="file-123",
        tenant_id="tenant-abc",
        file_version=1,
        source_container="chunks",
        output_container="embeddings",
        embedding_model="text-embedding-3-small",
        batch_size=50,
    )

    vectorize_and_enqueue_ingestion_use_case._vectorize_use_case.execute = AsyncMock(
        return_value=VectorizeChunksResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            total_chunks=5,
            embedded_chunks=5,
            failed_chunks=0,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            embeddings_url="embeddings/tenant-abc/file-123/embeddings/",
            correlation_id="corr-123",
            processing_time_ms=100,
        )
    )

    vectorize_and_enqueue_ingestion_use_case._pipeline_store.get_by_id = (
        AsyncMock(return_value=MagicMock(document=MagicMock(file_version=2, collection_name="my-collection")))
    )

    result = await vectorize_and_enqueue_ingestion_use_case.execute(request)

    assert result.status == ProcessingStatus.COMPLETED
    vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish.assert_called_once()
    publish_kwargs = (
        vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish.call_args.kwargs
    )
    assert publish_kwargs["queue_name"] == "ingest-to-db"
    assert publish_kwargs["tenant_id"] == "tenant-abc"
    assert publish_kwargs["file_id"] == "file-123"
    assert publish_kwargs["payload"]["source_container"] == "embeddings"
    assert publish_kwargs["payload"]["collection_name"] == "my-collection"
    assert publish_kwargs["payload"]["batch_size"] == 100


async def test_execute_skips_enqueue_on_failure(
    vectorize_and_enqueue_ingestion_use_case: VectorizeChunksAndEnqueueIngestionUseCase,
) -> None:
    """Ensure ingestion enqueue is skipped when vectorization fails."""
    request = VectorizeChunksRequest(
        file_id="file-456",
        tenant_id="tenant-xyz",
        file_version=1,
        source_container="chunks",
        output_container="embeddings",
    )

    vectorize_and_enqueue_ingestion_use_case._vectorize_use_case.execute = AsyncMock(
        return_value=VectorizeChunksResult(
            file_id=request.file_id,
            status=ProcessingStatus.FAILED,
            total_chunks=5,
            embedded_chunks=0,
            failed_chunks=5,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            correlation_id="corr-456",
            processing_time_ms=50,
            error_message="Embedding failed",
        )
    )

    result = await vectorize_and_enqueue_ingestion_use_case.execute(request)

    assert result.status == ProcessingStatus.FAILED
    vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish.assert_not_called()


async def test_execute_skips_enqueue_when_no_collection_name(
    vectorize_and_enqueue_ingestion_use_case: VectorizeChunksAndEnqueueIngestionUseCase,
) -> None:
    """Ensure ingestion enqueue is skipped when file has no collection_name."""
    request = VectorizeChunksRequest(
        file_id="file-789",
        tenant_id="tenant-abc",
        file_version=1,
        source_container="chunks",
        output_container="embeddings",
    )

    vectorize_and_enqueue_ingestion_use_case._vectorize_use_case.execute = AsyncMock(
        return_value=VectorizeChunksResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            total_chunks=3,
            embedded_chunks=3,
            failed_chunks=0,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            embeddings_url="embeddings/tenant-abc/file-789/embeddings/",
            correlation_id="corr-789",
            processing_time_ms=75,
        )
    )

    vectorize_and_enqueue_ingestion_use_case._pipeline_store.get_by_id = (
        AsyncMock(return_value=MagicMock(document=MagicMock(file_version=1, collection_name=None)))
    )

    result = await vectorize_and_enqueue_ingestion_use_case.execute(request)

    assert result.status == ProcessingStatus.COMPLETED
    vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish.assert_not_called()


async def test_execute_continues_on_queue_publish_failure(
    vectorize_and_enqueue_ingestion_use_case: VectorizeChunksAndEnqueueIngestionUseCase,
) -> None:
    """Ensure use case doesn't fail when queue publish fails."""
    request = VectorizeChunksRequest(
        file_id="file-101",
        tenant_id="tenant-abc",
        file_version=1,
        source_container="chunks",
        output_container="embeddings",
    )

    vectorize_and_enqueue_ingestion_use_case._vectorize_use_case.execute = AsyncMock(
        return_value=VectorizeChunksResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            total_chunks=2,
            embedded_chunks=2,
            failed_chunks=0,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            embeddings_url="embeddings/tenant-abc/file-101/embeddings/",
            correlation_id="corr-101",
            processing_time_ms=60,
        )
    )

    vectorize_and_enqueue_ingestion_use_case._pipeline_store.get_by_id = (
        AsyncMock(return_value=MagicMock(document=MagicMock(file_version=1, collection_name="test-collection")))
    )

    vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish = AsyncMock(
        side_effect=Exception("Queue publish failed")
    )

    result = await vectorize_and_enqueue_ingestion_use_case.execute(request)

    assert result.status == ProcessingStatus.COMPLETED
    vectorize_and_enqueue_ingestion_use_case._queue_publisher.publish.assert_called_once()
