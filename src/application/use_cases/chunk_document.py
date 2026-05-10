"""Use case for chunking documents."""

import json
import logging
import time
import uuid

from src.application.dto.chunking import ChunkDocumentRequest, ChunkDocumentResult
from src.application.dto.document_analysis import ProcessingStatus
from src.application.ports.blob_client import BlobClientPort
from src.application.ports.chunk_index_store import ChunkIndexStorePort
from src.application.ports.chunker import ChunkerPort
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.processing_events import ProcessingEventsPort
from src.core.entities.chunk import Chunk
from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.pipeline_state import ProcessingStage
from src.core.errors import (
    ChunkingError,
    DocumentNotFoundError,
    InvalidChunkingStrategyError,
    TextNotFoundError,
)

logger = logging.getLogger(__name__)


class ChunkDocumentUseCase:
    """
    Use case for chunking documents.

    Orchestrates the flow:
    1. Retrieve text document from blob storage (text container)
    2. Validate chunking strategy
    3. Apply chunking via ChunkerPort
    4. Store each chunk in chunks container
    5. Update ChunkIndex table
    6. Update pipeline state stage
    7. Return result with chunk count and URLs
    """

    def __init__(
        self,
        blob_client: BlobClientPort,
        chunker: ChunkerPort,
        chunk_index_repository: ChunkIndexStorePort,
        pipeline_store: PipelineStorePort,
        processing_events: ProcessingEventsPort | None = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            blob_client: Client for blob storage operations
            chunker: Chunking port implementation
            chunk_index_repository: Repository for chunk index operations
            pipeline_store: Repository for pipeline state operations
            processing_events: Optional ProcessingEventsPort for stage tracking
        """
        self._blob_client = blob_client
        self._chunker = chunker
        self._chunk_index_repository = chunk_index_repository
        self._pipeline_store = pipeline_store
        self._processing_events = processing_events

    async def execute(self, request: ChunkDocumentRequest) -> ChunkDocumentResult:
        """
        Execute the document chunking use case.

        Args:
            request: Document chunking request

        Returns:
            ChunkDocumentResult with processing status and chunk info

        Raises:
            TextNotFoundError: If the extracted text doesn't exist
            InvalidChunkingStrategyError: If the chunking strategy isn't supported
            ChunkingError: If chunking fails
        """
        correlation_id = request.correlation_id or str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            f"Starting document chunking: file_id={request.file_id}, "
            f"correlation_id={correlation_id}"
        )

        try:
            # Get document with pipeline state
            doc = await self._pipeline_store.get_by_id(
                request.tenant_id, request.file_id
            )

            if doc is None:
                raise DocumentNotFoundError(
                    file_id=request.file_id,
                    container=request.source_container,
                )

            # Use text blob reference from SQL (SSOT for content location)
            if not doc.document.text_blob_ref:
                raise ChunkingError(
                    message="No text blob reference found in file index",
                    file_id=request.file_id,
                    strategy="",
                    details={"reason": "missing_text_blob_ref"},
                )

            source_blob_path = doc.document.text_blob_ref

            # Check if text blob exists
            exists = await self._blob_client.blob_exists(
                request.source_container, source_blob_path
            )
            if not exists:
                raise TextNotFoundError(
                    file_id=request.file_id,
                    container=request.source_container,
                )

            # Use the strategy from the request (always present, defaults to fixed_size)
            strategy = request.chunking_strategy

            # Validate strategy is supported
            if not self._chunker.is_strategy_supported(strategy.strategy_name):
                raise InvalidChunkingStrategyError(
                    strategy_name=strategy.strategy_name.value,
                    supported_strategies=[
                        s.value for s in self._chunker.get_supported_strategies()
                    ],
                )

            # Update status to processing
            await self._pipeline_store.mark_processing(
                request.tenant_id, request.file_id, ProcessingStage.CHUNK
            )

            # Download text document
            text_content = await self._blob_client.download_blob(
                request.source_container, source_blob_path
            )
            text_data = json.loads(text_content)

            # Extract the text to chunk
            text_to_chunk = text_data.get("extracted_text", "")

            if not text_to_chunk:
                raise ChunkingError(
                    message="No text content found in extracted document",
                    file_id=request.file_id,
                    strategy=strategy.strategy_name.value,
                )

            logger.info(
                f"Downloaded text: file_id={request.file_id}, "
                f"text_length={len(text_to_chunk)} chars"
            )

            # Chunk the text
            chunks = await self._chunker.chunk_text(
                text=text_to_chunk,
                file_id=request.file_id,
                strategy=strategy,
            )

            logger.info(
                f"Chunked document: file_id={request.file_id}, "
                f"chunk_count={len(chunks)}"
            )

            # Store chunks and update index
            await self._store_chunks(
                chunks=chunks,
                request=request,
            )

            # Update pipeline state with chunk count
            await self._pipeline_store.update_chunk_counts(
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                chunk_count=len(chunks),
            )

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Build chunks URL (relative path with tenant isolation)
            chunks_url = f"{request.output_container}/{request.tenant_id}/{request.file_id}/chunks/"

            logger.info(
                f"Document chunking completed: file_id={request.file_id}, "
                f"processing_time_ms={processing_time_ms}, "
                f"chunk_count={len(chunks)}"
            )

            await self._log_stage_transition(
                request=request,
                status="success",
                duration_ms=processing_time_ms,
            )

            return ChunkDocumentResult(
                file_id=request.file_id,
                status=ProcessingStatus.COMPLETED,
                chunk_count=len(chunks),
                chunks_url=chunks_url,
                chunking_strategy=strategy.strategy_name.value,
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
            )

        except (TextNotFoundError, DocumentNotFoundError, InvalidChunkingStrategyError) as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._log_stage_transition(
                request=request,
                status="failed",
                duration_ms=elapsed_ms,
                error_message=str(e),
            )
            raise

        except ChunkingError:
            # Re-raise chunking errors as-is
            raise

        except Exception as e:
            # Mark as failed in repository
            await self._pipeline_store.mark_failed(
                request.tenant_id, request.file_id, str(e)
            )
            processing_time_ms = int((time.time() - start_time) * 1000)
            await self._log_stage_transition(
                request=request,
                status="failed",
                duration_ms=processing_time_ms,
                error_message=str(e),
            )

            logger.error(
                f"Document chunking failed: file_id={request.file_id}, "
                f"error={str(e)}",
                exc_info=True,
            )

            raise ChunkingError(
                message=f"Failed to chunk document: {str(e)}",
                file_id=request.file_id,
                strategy=request.chunking_strategy.strategy_name.value,
                details={"correlation_id": correlation_id},
            ) from e

    async def _log_stage_transition(
        self,
        request: ChunkDocumentRequest,
        status: str,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        if not self._processing_events:
            return
        try:
            await self._processing_events.log_stage_event(
                file_id=request.file_id,
                tenant_id=request.tenant_id,
                stage=ProcessingStage.CHUNK.value,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
        except Exception:
            logger.warning("Failed to log stage event", exc_info=True)

    async def _store_chunks(
        self,
        chunks: list[Chunk],
        request: ChunkDocumentRequest,
    ) -> None:
        """
        Store chunks in blob storage and update chunk index.

        Args:
            chunks: List of chunks to store
            request: The original chunking request
        """
        # Delete existing chunks for this file (idempotency)
        await self._chunk_index_repository.delete_by_file(
            file_id=request.file_id,
        )

        chunk_indices = []

        for chunk in chunks:
            # Store chunk blob with tenant isolation (metadata lives in SQL, not blob)
            blob_path = f"{request.tenant_id}/{request.file_id}/chunks/{chunk.chunk_id}.json"
            chunk_data = json.dumps(
                chunk.model_dump(mode="json", exclude={"metadata"}), indent=2
            )

            await self._blob_client.upload_blob(
                container=request.output_container,
                blob_path=blob_path,
                data=chunk_data,
                content_type="application/json; charset=utf-8",
            )

            # Create chunk index entry with blob reference (SSOT for content location)
            chunk_index = ChunkIndex(
                file_id=request.file_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                text_preview=chunk.text_preview,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                page_number=chunk.page_number,
                chunk_blob_ref=blob_path,
                metadata_json=chunk.metadata.model_dump(mode="json"),
            )
            chunk_indices.append(chunk_index)

        # Batch create chunk index entries
        if chunk_indices:
            await self._chunk_index_repository.batch_create(chunk_indices)

        logger.info(
            f"Stored {len(chunks)} chunks for file_id={request.file_id}"
        )
