"""Use case for vectorizing chunks and enqueuing ingestion to vector database."""

import logging
from typing import Any

from src.application.dto.document_analysis import ProcessingStatus
from src.application.dto.embedding import VectorizeChunksRequest, VectorizeChunksResult
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.queue_publisher import QueuePublisherPort
from src.application.use_cases.vectorize_chunks import VectorizeChunksUseCase

logger = logging.getLogger(__name__)


class VectorizeChunksAndEnqueueIngestionUseCase:
    """
    Orchestrates vectorization then enqueues ingestion to vector database.

    Keeps queue triggers thin and preserves clean architecture.
    """

    def __init__(
        self,
        vectorize_use_case: VectorizeChunksUseCase,
        queue_publisher: QueuePublisherPort,
        queue_name: str,
        pipeline_store: PipelineStorePort,
        batch_size: int = 100,
    ) -> None:
        """
        Initialize the use case.

        Args:
            vectorize_use_case: Use case for chunk vectorization
            queue_publisher: Queue publisher port implementation
            queue_name: Target ingestion queue name
            pipeline_store: Repository for pipeline state lookups
            batch_size: Batch size for ingestion processing
        """
        self._vectorize_use_case = vectorize_use_case
        self._queue_publisher = queue_publisher
        self._queue_name = queue_name
        self._pipeline_store = pipeline_store
        self._batch_size = batch_size

    async def execute(self, request: VectorizeChunksRequest) -> VectorizeChunksResult:
        """
        Execute vectorization, then enqueue ingestion.

        Args:
            request: Vectorize chunks request

        Returns:
            VectorizeChunksResult from the vectorization step
        """
        result = await self._vectorize_use_case.execute(request)

        if result.status != ProcessingStatus.COMPLETED:
            logger.warning(
                "Vectorization did not complete; skipping ingestion enqueue: "
                "file_id=%s, status=%s",
                request.file_id,
                result.status,
            )
            return result

        collection_name = await self._resolve_collection_name(request)
        if not collection_name:
            logger.warning(
                "No collection_name found for file; skipping ingestion enqueue: "
                "tenant_id=%s, file_id=%s",
                request.tenant_id,
                request.file_id,
            )
            return result

        payload = self._build_payload(request, collection_name)
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
                "Published to ingestion queue: file_id=%s, queue=%s, collection=%s",
                request.file_id,
                self._queue_name,
                collection_name,
            )
        except Exception as exc:
            logger.error(
                "Failed to publish to ingestion queue: file_id=%s, queue=%s, error=%s",
                request.file_id,
                self._queue_name,
                exc,
                exc_info=True,
            )

        return result

    def _build_payload(
        self, request: VectorizeChunksRequest, collection_name: str
    ) -> dict[str, Any]:
        """Build queue payload for ingestion."""
        return {
            "source_container": request.output_container,
            "collection_name": collection_name,
            "batch_size": self._batch_size,
        }

    async def _resolve_collection_name(
        self, request: VectorizeChunksRequest
    ) -> str | None:
        """Resolve collection name from document."""
        doc = await self._pipeline_store.get_by_id(
            request.tenant_id,
            request.file_id,
        )
        if doc is None:
            return None
        return doc.document.collection_name

    async def _resolve_file_version(self, request: VectorizeChunksRequest) -> int:
        """Resolve file version for queue envelope; default to request value or 1."""
        if request.file_version:
            return request.file_version

        doc = await self._pipeline_store.get_by_id(
            request.tenant_id,
            request.file_id,
        )
        if doc is None:
            logger.warning(
                "Document not found when enqueuing ingestion; defaulting file_version=1: "
                "tenant_id=%s, file_id=%s",
                request.tenant_id,
                request.file_id,
            )
            return 1
        return doc.document.file_version
