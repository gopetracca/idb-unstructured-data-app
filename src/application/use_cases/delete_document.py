"""Delete document use case."""

import logging
from datetime import datetime

from src.application.dto.document_dto import DeleteDocumentInput, DeleteDocumentOutput
from src.application.ports.blob_store import BlobStorePort
from src.application.ports.document_store import DocumentStorePort
from src.application.ports.vector_database import VectorDatabasePort
from src.core.errors import (
    DocumentNotFoundError,
    IndexNotFoundError,
    StorageError,
)

logger = logging.getLogger(__name__)


class DeleteDocumentUseCase:
    """
    Use case for deleting documents from the RAG system.

    Handles deletion of blob storage (all containers), vector index, and metadata.
    Blob and vector index failures are logged but do not block SQL metadata cleanup.
    """

    def __init__(
        self,
        blob_store: BlobStorePort,
        metadata_store: DocumentStorePort,
        vector_database: VectorDatabasePort,
        container_raw: str = "raw",
        container_text: str = "text",
        container_chunks: str = "chunks",
        container_embeddings: str = "embeddings",
        index_name: str = "",
    ) -> None:
        self._blob_store = blob_store
        self._metadata_store = metadata_store
        self._vector_database = vector_database
        self._container_raw = container_raw
        self._container_text = container_text
        self._container_chunks = container_chunks
        self._container_embeddings = container_embeddings
        self._index_name = index_name

    async def execute(self, input_dto: DeleteDocumentInput) -> DeleteDocumentOutput:
        """Execute the delete document use case."""
        doc = await self._metadata_store.get_by_id(
            input_dto.tenant_id,
            input_dto.file_id,
        )

        if doc is None:
            raise DocumentNotFoundError(input_dto.file_id, input_dto.tenant_id)

        filename = doc.document.blob_name
        deleted_at = datetime.utcnow()
        blob_prefix = f"{input_dto.tenant_id}/{input_dto.file_id}/"

        # Delete from all blob containers — failures are logged but do not block cleanup
        for container in (
            self._container_raw,
            self._container_text,
            self._container_chunks,
            self._container_embeddings,
        ):
            try:
                await self._blob_store.delete_by_prefix(container, blob_prefix)
            except Exception as e:
                logger.error(
                    "Failed to delete blobs from container '%s' for file '%s': %s",
                    container,
                    input_dto.file_id,
                    e,
                )

        # Delete chunks from the document's own collection (index) — falls back to
        # the configured default only when the document has no collection_name.
        # Failures are logged but do not block SQL cleanup.
        target_index = doc.document.collection_name or self._index_name
        if not target_index:
            logger.info(
                "Skipping vector index cleanup for file '%s': no collection_name on document and no default index configured",
                input_dto.file_id,
            )
        else:
            try:
                await self._vector_database.delete_by_file_id(
                    target_index, input_dto.file_id
                )
            except IndexNotFoundError:
                logger.warning(
                    "Vector index '%s' not found for file '%s' — skipping vector index cleanup",
                    target_index,
                    input_dto.file_id,
                )
            except Exception as e:
                logger.error(
                    "Failed to delete vector index chunks for file '%s' from index '%s': %s",
                    input_dto.file_id,
                    target_index,
                    e,
                )

        # Delete metadata record (cascades to pipeline_state, file_metadata, chunks, processing_events)
        try:
            await self._metadata_store.delete(input_dto.tenant_id, input_dto.file_id)
        except Exception as e:
            raise StorageError("delete_metadata", str(e)) from e

        return DeleteDocumentOutput(
            file_id=input_dto.file_id,
            filename=filename,
            deleted_at=deleted_at,
            message="Document successfully deleted",
        )
