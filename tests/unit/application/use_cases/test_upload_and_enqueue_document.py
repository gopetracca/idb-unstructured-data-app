"""Unit tests for UploadAndEnqueueDocumentUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_dto import UploadDocumentInput, UploadDocumentOutput
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.core.value_objects.document_metadata import DocumentMetadata


@pytest.fixture
def mock_upload_output() -> UploadDocumentOutput:
    """Create a mock upload output."""
    return UploadDocumentOutput(
        file_id="file-123",
        filename="test-doc.pdf",
        size_bytes=1024,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 1, 28, 10, 0, 0),
        metadata=DocumentMetadata(file_id="file-123"),
    )


@pytest.fixture
def upload_and_enqueue_use_case(
    mock_upload_output: UploadDocumentOutput,
) -> UploadAndEnqueueDocumentUseCase:
    """Create an UploadAndEnqueueDocumentUseCase with mock dependencies."""
    upload_use_case = MagicMock()
    upload_use_case.execute = AsyncMock(return_value=mock_upload_output)
    queue_publisher = MagicMock()
    queue_publisher.publish = AsyncMock()

    return UploadAndEnqueueDocumentUseCase(
        upload_use_case=upload_use_case,
        queue_publisher=queue_publisher,
        queue_name="raw-to-text",
    )


async def test_execute_forwards_chunking_strategy_in_payload(
    upload_and_enqueue_use_case: UploadAndEnqueueDocumentUseCase,
) -> None:
    """Ensure chunking_strategy is included in the queue payload when provided."""
    chunking_strategy = {"strategy_name": "markdown_aware", "parameters": {"chunk_size": 1024}}
    input_dto = UploadDocumentInput(
        tenant_id="tenant-abc",
        filename="test-doc.pdf",
        content=b"PDF content",
        content_type="application/pdf",
        collection_name="test-collection",
        ezshare_id="EZSHARE-123",
        chunking_strategy=chunking_strategy,
    )

    await upload_and_enqueue_use_case.execute(input_dto)

    publish_kwargs = upload_and_enqueue_use_case._queue_publisher.publish.call_args.kwargs
    assert publish_kwargs["payload"]["chunking_strategy"] == chunking_strategy
    assert publish_kwargs["payload"]["filename"] == "test-doc.pdf"


async def test_execute_forwards_default_chunking_strategy_when_not_provided(
    upload_and_enqueue_use_case: UploadAndEnqueueDocumentUseCase,
) -> None:
    """Ensure default chunking_strategy is included in payload when not explicitly set."""
    input_dto = UploadDocumentInput(
        tenant_id="tenant-abc",
        filename="test-doc.pdf",
        content=b"PDF content",
        content_type="application/pdf",
        collection_name="test-collection",
        ezshare_id="EZSHARE-456",
    )

    await upload_and_enqueue_use_case.execute(input_dto)

    publish_kwargs = upload_and_enqueue_use_case._queue_publisher.publish.call_args.kwargs
    assert publish_kwargs["payload"]["chunking_strategy"] == {"strategy_name": "fixed_size"}
    assert publish_kwargs["payload"]["filename"] == "test-doc.pdf"


async def test_execute_returns_upload_output(
    upload_and_enqueue_use_case: UploadAndEnqueueDocumentUseCase,
    mock_upload_output: UploadDocumentOutput,
) -> None:
    """Ensure the upload output is returned even if enqueue succeeds."""
    input_dto = UploadDocumentInput(
        tenant_id="tenant-abc",
        filename="test-doc.pdf",
        content=b"PDF content",
        content_type="application/pdf",
        collection_name="test-collection",
        ezshare_id="EZSHARE-789",
    )

    result = await upload_and_enqueue_use_case.execute(input_dto)

    assert result.file_id == mock_upload_output.file_id
    assert result.filename == mock_upload_output.filename


async def test_execute_continues_on_queue_publish_failure(
    upload_and_enqueue_use_case: UploadAndEnqueueDocumentUseCase,
    mock_upload_output: UploadDocumentOutput,
) -> None:
    """Ensure upload output is returned even when queue publish fails."""
    upload_and_enqueue_use_case._queue_publisher.publish = AsyncMock(
        side_effect=Exception("Queue unavailable")
    )

    input_dto = UploadDocumentInput(
        tenant_id="tenant-abc",
        filename="test-doc.pdf",
        content=b"PDF content",
        content_type="application/pdf",
        collection_name="test-collection",
        ezshare_id="EZSHARE-101",
    )

    result = await upload_and_enqueue_use_case.execute(input_dto)

    assert result.file_id == mock_upload_output.file_id
