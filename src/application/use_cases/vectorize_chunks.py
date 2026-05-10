"""Use case for vectorizing document chunks."""

import json
import logging
import time
import uuid
from typing import Any

from src.application.dto.document_analysis import ProcessingStatus
from src.application.dto.embedding import VectorizeChunksRequest, VectorizeChunksResult
from src.application.ports.blob_client import BlobClientPort
from src.application.ports.chunk_index_store import ChunkIndexStorePort
from src.application.ports.embedding import EmbeddingPort
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.processing_events import ProcessingEventsPort
from src.core.entities.chunk import Chunk
from src.core.entities.embedding import Embedding, EmbeddingMetadata
from src.core.entities.pipeline_state import ProcessingStage
from src.core.errors import (
    ChunksNotFoundError,
    DocumentNotFoundError,
    EmbeddingError,
)

logger = logging.getLogger(__name__)


class VectorizeChunksUseCase:
    """
    Use case for vectorizing document chunks.

    Orchestrates the flow:
    1. Retrieve chunk info from ChunkIndex table
    2. Load chunks from blob storage
    3. Batch chunks for efficient API calls
    4. Generate embeddings via EmbeddingPort
    5. Store embeddings in embeddings container
    6. Update ChunkIndex with embedding status
    7. Update pipeline state with embedded count
    8. Return result with embedding statistics
    """

    def __init__(
        self,
        blob_client: BlobClientPort,
        embedding_port: EmbeddingPort,
        chunk_index_repository: ChunkIndexStorePort,
        pipeline_store: PipelineStorePort,
        processing_events: ProcessingEventsPort | None = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            blob_client: Client for blob storage operations
            embedding_port: Embedding port implementation
            chunk_index_repository: Repository for chunk index operations
            pipeline_store: Repository for pipeline state operations
            processing_events: Optional ProcessingEventsPort for stage tracking
        """
        self._blob_client = blob_client
        self._embedding_port = embedding_port
        self._chunk_index_repository = chunk_index_repository
        self._pipeline_store = pipeline_store
        self._processing_events = processing_events

    async def execute(self, request: VectorizeChunksRequest) -> VectorizeChunksResult:
        """
        Execute the vectorization use case.

        Args:
            request: Vectorization request

        Returns:
            VectorizeChunksResult with processing status and embedding info

        Raises:
            DocumentNotFoundError: If the document doesn't exist
            ChunksNotFoundError: If no chunks exist for the document
            EmbeddingError: If embedding generation fails
        """
        correlation_id = request.correlation_id or str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            f"Starting chunk vectorization: file_id={request.file_id}, "
            f"model={request.embedding_model}, correlation_id={correlation_id}"
        )

        try:
            # Verify file exists
            doc = await self._pipeline_store.get_by_id(
                request.tenant_id, request.file_id
            )
            if doc is None:
                raise DocumentNotFoundError(
                    file_id=request.file_id,
                    tenant_id=request.tenant_id,
                )

            # Get pending chunks from ChunkIndex
            chunk_indices = await self._chunk_index_repository.query_pending_embeddings(
                file_id=request.file_id,
            )

            if not chunk_indices:
                # Check if chunks exist at all
                total_count = await self._chunk_index_repository.count_by_file(
                    request.file_id
                )
                if total_count == 0:
                    raise ChunksNotFoundError(
                        file_id=request.file_id,
                        container=request.source_container,
                    )
                # All chunks already embedded - return success
                embedded_count = await self._chunk_index_repository.count_embedded(
                    request.file_id
                )
                processing_time_ms = int((time.time() - start_time) * 1000)
                return VectorizeChunksResult(
                    file_id=request.file_id,
                    status=ProcessingStatus.COMPLETED,
                    total_chunks=total_count,
                    embedded_chunks=embedded_count,
                    failed_chunks=0,
                    embedding_model=request.embedding_model,
                    embedding_dimension=self._embedding_port.get_model_dimension(
                        request.embedding_model
                    ),
                    embeddings_url=f"{request.output_container}/{request.tenant_id}/{request.file_id}/embeddings/",
                    correlation_id=correlation_id,
                    processing_time_ms=processing_time_ms,
                )

            # Mark file as processing vectorization
            await self._pipeline_store.mark_processing(
                request.tenant_id, request.file_id, ProcessingStage.VECTORIZE
            )

            # Load chunks from blob storage (text only)
            chunks = await self._load_chunks(
                chunk_indices=chunk_indices,
                source_container=request.source_container,
                tenant_id=request.tenant_id,
                file_id=request.file_id,
            )

            # Batch-fetch chunk metadata from SQL (authoritative source)
            chunk_ids = [c.chunk_id for c in chunks]
            metadata_map = await self._chunk_index_repository.batch_get_metadata(chunk_ids)

            # Process in batches
            embedded_count = 0
            failed_count = 0
            dimension = self._embedding_port.get_model_dimension(request.embedding_model)

            for batch_start in range(0, len(chunks), request.batch_size):
                batch_chunks = chunks[batch_start : batch_start + request.batch_size]

                try:
                    embeddings = await self._process_batch(
                        chunks=batch_chunks,
                        model=request.embedding_model,
                        request=request,
                        metadata_map=metadata_map,
                    )

                    # Store embeddings and update indices
                    for embedding in embeddings:
                        await self._store_embedding(embedding, request.output_container, request.tenant_id)
                        await self._chunk_index_repository.mark_embedded(
                            chunk_id=embedding.chunk_id,
                            vector_db_id=f"blob:{embedding.chunk_id}",
                        )
                        embedded_count += 1

                except Exception as e:
                    logger.error(f"Batch embedding failed: {str(e)}", exc_info=True)
                    # Mark chunks as failed
                    for chunk in batch_chunks:
                        await self._chunk_index_repository.mark_failed(
                            chunk_id=chunk.chunk_id,
                        )
                        failed_count += 1

            # Update pipeline state with embedded count
            await self._pipeline_store.update_embedded_count(
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                embedded_count=embedded_count,
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            status = (
                ProcessingStatus.COMPLETED if failed_count == 0 else ProcessingStatus.FAILED
            )

            logger.info(
                f"Vectorization completed: file_id={request.file_id}, "
                f"embedded={embedded_count}, failed={failed_count}, "
                f"time_ms={processing_time_ms}"
            )

            await self._log_stage_transition(
                request=request,
                status="success",
                duration_ms=processing_time_ms,
                error_message=f"{failed_count} chunks failed" if failed_count > 0 else None,
            )

            return VectorizeChunksResult(
                file_id=request.file_id,
                status=status,
                total_chunks=len(chunks),
                embedded_chunks=embedded_count,
                failed_chunks=failed_count,
                embedding_model=request.embedding_model,
                embedding_dimension=dimension,
                embeddings_url=f"{request.output_container}/{request.tenant_id}/{request.file_id}/embeddings/",
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
                error_message=f"{failed_count} chunks failed" if failed_count > 0 else None,
            )

        except (DocumentNotFoundError, ChunksNotFoundError) as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._log_stage_transition(
                request=request,
                status="failed",
                duration_ms=elapsed_ms,
                error_message=str(e),
            )
            raise

        except EmbeddingError:
            # Re-raise embedding errors as-is
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
                f"Vectorization failed: file_id={request.file_id}, error={str(e)}",
                exc_info=True,
            )

            raise EmbeddingError(
                message=f"Failed to vectorize chunks: {str(e)}",
                file_id=request.file_id,
                model=request.embedding_model,
                details={"correlation_id": correlation_id},
            ) from e

    async def _log_stage_transition(
        self,
        request: VectorizeChunksRequest,
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
                stage=ProcessingStage.VECTORIZE.value,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
        except Exception:
            logger.warning("Failed to log stage event", exc_info=True)

    async def _load_chunks(
        self,
        chunk_indices: list,
        source_container: str,
        tenant_id: str,
        file_id: str,
    ) -> list[Chunk]:
        """
        Load chunks from blob storage.

        Args:
            chunk_indices: List of ChunkIndex entries
            source_container: Container name for chunks
            tenant_id: Tenant identifier
            file_id: File identifier

        Returns:
            List of Chunk entities
        """
        chunks = []
        for chunk_index in chunk_indices:
            # Use chunk blob reference from SQL (SSOT for content location)
            if not chunk_index.chunk_blob_ref:
                logger.warning(
                    f"Skipping chunk {chunk_index.chunk_id}: missing chunk_blob_ref"
                )
                continue

            blob_path = chunk_index.chunk_blob_ref
            try:
                content = await self._blob_client.download_blob(source_container, blob_path)
                chunk_data = json.loads(content)
                chunk = Chunk.model_validate(chunk_data)
                chunks.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to load chunk {chunk_index.chunk_id}: {e}")
        return chunks

    async def _process_batch(
        self,
        chunks: list[Chunk],
        model: str,
        request: VectorizeChunksRequest,
        metadata_map: dict[str, dict[str, Any]],
    ) -> list[Embedding]:
        """
        Process a batch of chunks and generate embeddings.

        Args:
            chunks: List of chunks to process
            model: Embedding model to use
            request: Original vectorization request
            metadata_map: {chunk_id: metadata_json} sourced from SQL

        Returns:
            List of Embedding entities
        """
        texts = [chunk.text for chunk in chunks]
        results = await self._embedding_port.generate_embeddings(texts, model)

        embeddings = []
        for chunk, result in zip(chunks, results, strict=False):
            meta = metadata_map.get(chunk.chunk_id, {})
            embedding = Embedding(
                file_id=request.file_id,
                chunk_id=chunk.chunk_id,
                embedding_model=result.model,
                embedding_dimension=result.dimension,
                vector=result.vector,
                chunk_text=chunk.text,
                metadata=EmbeddingMetadata(
                    model_version=result.model,
                    token_count=meta.get("token_count", result.token_count),
                    chunking_strategy=meta.get("chunking_strategy", ""),
                    chunk_size=meta.get("chunk_size", 0),
                    overlap_chars=meta.get("overlap_chars", 0),
                    page_number=chunk.page_number,
                    section_path=meta.get("section_path"),
                    has_table=meta.get("has_table", False),
                    table_id=meta.get("table_id"),
                ),
            )
            embeddings.append(embedding)
        return embeddings

    async def _store_embedding(self, embedding: Embedding, container: str, tenant_id: str) -> None:
        """
        Store embedding in blob storage.

        Args:
            embedding: Embedding entity to store
            container: Container name for embeddings
            tenant_id: Tenant identifier
        """
        blob_path = f"{tenant_id}/{embedding.file_id}/embeddings/{embedding.chunk_id}.json"
        content = json.dumps(embedding.model_dump(mode="json"), indent=2)
        await self._blob_client.upload_blob(
            container=container,
            blob_path=blob_path,
            data=content,
            content_type="application/json",
        )
