"""Unit tests for ProcessTextAndEnqueueChunkingUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_analysis import (
    DocumentAnalysisRequest,
    DocumentAnalysisResult,
    ProcessingStatus,
)
from src.application.use_cases.process_text_and_enqueue_chunking import (
    ProcessTextAndEnqueueChunkingUseCase,
)


@pytest.fixture
def process_text_and_enqueue_use_case() -> ProcessTextAndEnqueueChunkingUseCase:
    """Create a ProcessTextAndEnqueueChunkingUseCase with mock dependencies."""
    process_use_case = MagicMock()
    queue_publisher = MagicMock()
    pipeline_store = MagicMock()

    process_use_case.execute = AsyncMock()
    queue_publisher.publish = AsyncMock()
    pipeline_store.get_by_id = AsyncMock()

    return ProcessTextAndEnqueueChunkingUseCase(
        process_use_case=process_use_case,
        queue_publisher=queue_publisher,
        queue_name="chunk-document",
        pipeline_store=pipeline_store,
        chunk_output_container="chunks",
    )


async def test_execute_enqueues_chunking_on_success(
    process_text_and_enqueue_use_case: ProcessTextAndEnqueueChunkingUseCase,
) -> None:
    """Ensure chunking is enqueued when processing completes successfully."""
    request = DocumentAnalysisRequest(
        file_id="file-123",
        tenant_id="tenant-abc",
        source_container="raw",
        output_container="text",
    )

    process_text_and_enqueue_use_case._process_use_case.execute = AsyncMock(
        return_value=DocumentAnalysisResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            markdown_url="text/file-123/text.json",
            correlation_id="corr-123",
            processing_time_ms=10,
        )
    )

    process_text_and_enqueue_use_case._pipeline_store.get_by_id = AsyncMock(
        return_value=MagicMock(document=MagicMock(file_version=2))
    )

    result = await process_text_and_enqueue_use_case.execute(request)

    assert result.status == ProcessingStatus.COMPLETED
    process_text_and_enqueue_use_case._queue_publisher.publish.assert_called_once()
    publish_kwargs = process_text_and_enqueue_use_case._queue_publisher.publish.call_args.kwargs
    assert publish_kwargs["file_version"] == 2
    assert publish_kwargs["payload"]["source_container"] == "text"
    assert publish_kwargs["payload"]["output_container"] == "chunks"


async def test_execute_skips_enqueue_on_failure(
    process_text_and_enqueue_use_case: ProcessTextAndEnqueueChunkingUseCase,
) -> None:
    """Ensure chunking enqueue is skipped when processing fails."""
    request = DocumentAnalysisRequest(
        file_id="file-456",
        tenant_id="tenant-xyz",
        source_container="raw",
        output_container="text",
    )

    process_text_and_enqueue_use_case._process_use_case.execute = AsyncMock(
        return_value=DocumentAnalysisResult(
            file_id=request.file_id,
            status=ProcessingStatus.FAILED,
            markdown_url=None,
            correlation_id="corr-456",
            processing_time_ms=5,
            error_message="failed",
        )
    )

    result = await process_text_and_enqueue_use_case.execute(request)

    assert result.status == ProcessingStatus.FAILED
    process_text_and_enqueue_use_case._queue_publisher.publish.assert_not_called()


async def test_execute_forwards_chunking_strategy_in_payload(
    process_text_and_enqueue_use_case: ProcessTextAndEnqueueChunkingUseCase,
) -> None:
    """Ensure chunking_strategy is forwarded in the queue payload when provided."""
    chunking_strategy = {"strategy_name": "markdown_aware", "parameters": {"chunk_size": 1024}}
    request = DocumentAnalysisRequest(
        file_id="file-789",
        tenant_id="tenant-abc",
        source_container="raw",
        output_container="text",
    )

    process_text_and_enqueue_use_case._process_use_case.execute = AsyncMock(
        return_value=DocumentAnalysisResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            markdown_url="text/file-789/text.json",
            correlation_id="corr-789",
            processing_time_ms=10,
        )
    )

    process_text_and_enqueue_use_case._pipeline_store.get_by_id = AsyncMock(
        return_value=MagicMock(document=MagicMock(file_version=1))
    )

    result = await process_text_and_enqueue_use_case.execute(
        request, chunking_strategy=chunking_strategy
    )

    assert result.status == ProcessingStatus.COMPLETED
    publish_kwargs = process_text_and_enqueue_use_case._queue_publisher.publish.call_args.kwargs
    assert publish_kwargs["payload"]["chunking_strategy"] == chunking_strategy


async def test_execute_omits_chunking_strategy_when_not_provided(
    process_text_and_enqueue_use_case: ProcessTextAndEnqueueChunkingUseCase,
) -> None:
    """Ensure chunking_strategy is omitted from payload when not provided."""
    request = DocumentAnalysisRequest(
        file_id="file-000",
        tenant_id="tenant-abc",
        source_container="raw",
        output_container="text",
    )

    process_text_and_enqueue_use_case._process_use_case.execute = AsyncMock(
        return_value=DocumentAnalysisResult(
            file_id=request.file_id,
            status=ProcessingStatus.COMPLETED,
            markdown_url="text/file-000/text.json",
            correlation_id="corr-000",
            processing_time_ms=10,
        )
    )

    process_text_and_enqueue_use_case._pipeline_store.get_by_id = AsyncMock(
        return_value=MagicMock(document=MagicMock(file_version=1))
    )

    await process_text_and_enqueue_use_case.execute(request)

    publish_kwargs = process_text_and_enqueue_use_case._queue_publisher.publish.call_args.kwargs
    assert "chunking_strategy" not in publish_kwargs["payload"]