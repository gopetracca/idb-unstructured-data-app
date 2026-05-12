"""Use case for chunking documents and enqueuing vectorization."""

import logging
from typing import Any

from src.application.dto.chunking import ChunkDocumentRequest, ChunkDocumentResult
from src.application.dto.document_analysis import ProcessingStatus
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.queue_publisher import QueuePublisherPort
from src.application.use_cases.chunk_document import ChunkDocumentUseCase

logger = logging.getLogger(__name__)


class ChunkDocumentAndEnqueueVectorizationUseCase:
    """
    Orchestrates chunking then enqueues vectorization.

    Keeps queue triggers thin and preserves clean architecture.
    """

    def __init__(
        self,
        chunk_use_case: ChunkDocumentUseCase,
        queue_publisher: QueuePublisherPort,
        queue_name: str,
        pipeline_store: PipelineStorePort,
        embedding_output_container: str,
        embedding_model: str,
        embedding_batch_size: int,
    ) -> None:
        """
        Initialize the use case.

        Args:
            chunk_use_case: Use case for document chunking
            queue_publisher: Queue publisher port implementation
            queue_name: Target vectorization queue name
            pipeline_store: Repository for pipeline state lookups
            embedding_output_container: Output container for embeddings
            embedding_model: Default embedding model for vectorization
            embedding_batch_size: Default embedding batch size for vectorization
        """
        self._chunk_use_case = chunk_use_case
        self._queue_publisher = queue_publisher
        self._queue_name = queue_name
        self._pipeline_store = pipeline_store
        self._embedding_output_container = embedding_output_container
        self._embedding_model = embedding_model
        self._embedding_batch_size = embedding_batch_size

    async def execute(self, request: ChunkDocumentRequest) -> ChunkDocumentResult:
        """
        Execute chunking, then enqueue vectorization.

        Args:
            request: Chunk document request

        Returns:
            ChunkDocumentResult from the chunking step
        """
        result = await self._chunk_use_case.execute(request)

        if result.status != ProcessingStatus.COMPLETED:
            logger.warning(
                "Chunking did not complete; skipping vectorization enqueue: "
                "file_id=%s, status=%s",
                request.file_id,
                result.status,
            )
            return result

        payload = self._build_payload(request)
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
                "Published to vectorization queue: file_id=%s, queue=%s",
                request.file_id,
                self._queue_name,
            )
        except Exception as exc:
            logger.error(
                "Failed to publish to vectorization queue: file_id=%s, queue=%s, error=%s",
                request.file_id,
                self._queue_name,
                exc,
                exc_info=True,
            )

        return result

    def _build_payload(self, request: ChunkDocumentRequest) -> dict[str, Any]:
        """Build queue payload for vectorization."""
        return {
            "source_container": request.output_container,
            "output_container": self._embedding_output_container,
            "embedding_model": self._embedding_model,
            "batch_size": self._embedding_batch_size,
        }

    async def _resolve_file_version(self, request: ChunkDocumentRequest) -> int:
        """Resolve file version for queue envelope; default to 1 if missing."""
        doc = await self._pipeline_store.get_by_id(
            request.tenant_id,
            request.file_id,
        )
        if doc is None:
            logger.warning(
                "Document not found when enqueuing vectorization; defaulting file_version=1: "
                "tenant_id=%s, file_id=%s",
                request.tenant_id,
                request.file_id,
            )
            return 1
        return doc.document.file_version
