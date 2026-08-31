"""Use case for processing documents and enqueuing chunking."""

import logging
from typing import Any

from src.application.dto.document_analysis import (
    DocumentAnalysisRequest,
    DocumentAnalysisResult,
    ProcessingStatus,
)
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.queue_publisher import QueuePublisherPort
from src.application.use_cases.process_document import ProcessDocumentUseCase

logger = logging.getLogger(__name__)


class ProcessTextAndEnqueueChunkingUseCase:
    """
    Orchestrates text extraction then enqueues chunking.

    Keeps queue triggers thin and preserves clean architecture.
    """

    def __init__(
        self,
        process_use_case: ProcessDocumentUseCase,
        queue_publisher: QueuePublisherPort,
        queue_name: str,
        pipeline_store: PipelineStorePort,
        chunk_output_container: str,
    ) -> None:
        """
        Initialize the use case.

        Args:
            process_use_case: Use case for the extraction stage
            queue_publisher: Queue publisher port implementation
            queue_name: Target chunking queue name
            pipeline_store: Repository for pipeline state lookups
            chunk_output_container: Output container for chunks
        """
        self._process_use_case = process_use_case
        self._queue_publisher = queue_publisher
        self._queue_name = queue_name
        self._pipeline_store = pipeline_store
        self._chunk_output_container = chunk_output_container

    async def execute(
        self,
        request: DocumentAnalysisRequest,
        chunking_strategy: dict[str, Any] | None = None,
    ) -> DocumentAnalysisResult:
        """
        Execute text extraction, then enqueue chunking.

        Args:
            request: Document analysis request
            chunking_strategy: Chunking strategy dict to forward to the chunking queue

        Returns:
            DocumentAnalysisResult from the processing step
        """
        result = await self._process_use_case.execute(request)

        if result.status != ProcessingStatus.COMPLETED:
            logger.warning(
                "Text processing did not complete; skipping chunking enqueue: "
                "file_id=%s, status=%s",
                request.file_id,
                result.status,
            )
            return result

        payload = self._build_payload(request, chunking_strategy)
        file_version = await self._resolve_file_version(request)

        try:
            await self._queue_publisher.publish(
                queue_name=self._queue_name,
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                file_version=file_version,
                payload=payload,
                correlation_id=result.correlation_id,
            )
            logger.info(
                "Published to chunking queue: file_id=%s, queue=%s",
                request.file_id,
                self._queue_name,
            )
        except Exception as exc:
            logger.error(
                "Failed to publish to chunking queue: file_id=%s, queue=%s, error=%s",
                request.file_id,
                self._queue_name,
                exc,
                exc_info=True,
            )

        return result

    def _build_payload(
        self,
        request: DocumentAnalysisRequest,
        chunking_strategy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build queue payload for chunking."""
        payload: dict[str, Any] = {
            "source_container": request.output_container,
            "output_container": self._chunk_output_container,
        }
        if chunking_strategy:
            payload["chunking_strategy"] = chunking_strategy
        return payload

    async def _resolve_file_version(self, request: DocumentAnalysisRequest) -> int:
        """Resolve file version for queue envelope; default to 1 if missing."""
        doc = await self._pipeline_store.get_by_id(
            request.tenant_id,
            request.file_id,
        )
        if doc is None:
            logger.warning(
                "Document not found when enqueuing chunking; defaulting file_version=1: "
                "tenant_id=%s, file_id=%s",
                request.tenant_id,
                request.file_id,
            )
            return 1
        return doc.document.file_version
