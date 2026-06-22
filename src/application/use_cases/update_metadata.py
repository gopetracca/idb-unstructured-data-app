"""Update metadata use case."""

import logging
from datetime import datetime

from src.application.dto.document_dto import UpdateMetadataInput, UpdateMetadataOutput
from src.application.ports.document_store import DocumentStorePort
from src.application.ports.vector_database import VectorDatabasePort
from src.core.errors import DocumentNotFoundError, StorageError
from src.core.value_objects.document_metadata import get_metadata_model

logger = logging.getLogger(__name__)


class UpdateMetadataUseCase:
    """
    Use case for updating document metadata.

    Supports partial updates (PATCH semantics) with version tracking.
    All metadata fields are stored as SQL columns in file_metadata and
    synced to the Azure AI Search index (best-effort).
    """

    def __init__(
        self,
        metadata_store: DocumentStorePort,
        vector_database: VectorDatabasePort,
        index_name: str,
    ) -> None:
        self._metadata_store = metadata_store
        self._vector_database = vector_database
        self._index_name = index_name

    async def execute(self, input_dto: UpdateMetadataInput) -> UpdateMetadataOutput:
        """
        Execute the update metadata use case.

        All updates are applied to DocumentMetadata entity -> SQL columns,
        then synced to the vector index (best-effort).
        """
        doc = await self._metadata_store.get_by_id(
            input_dto.tenant_id,
            input_dto.file_id,
        )

        if doc is None:
            raise DocumentNotFoundError(input_dto.file_id, input_dto.tenant_id)

        # Get promoted fields for this document category (schema discriminator)
        model_class = get_metadata_model(doc.metadata.document_category)
        promoted_names = model_class.promoted_field_names()

        # Apply all updates that match promoted fields on DocumentMetadata
        for field, value in input_dto.metadata_updates.items():
            if field in promoted_names and hasattr(doc.metadata, field):
                setattr(doc.metadata, field, value)

        doc.document.last_updated = datetime.utcnow()
        doc.document.file_version += 1

        # Save updated document
        try:
            await self._metadata_store.update(doc)
        except Exception as e:
            raise StorageError("update_metadata", str(e)) from e

        # Sync promoted field changes to the vector index (best-effort).
        # Use the document's own collection_name — that is the index where its
        # chunks were ingested. Fall back to the configured default only when the
        # field is absent (pre-collection-feature documents).
        metadata_to_sync = {
            field: getattr(doc.metadata, field)
            for field in input_dto.metadata_updates
            if field in promoted_names and hasattr(doc.metadata, field)
        }
        if metadata_to_sync:
            index_name = doc.document.collection_name or self._index_name
            try:
                await self._vector_database.update_metadata_by_file_id(
                    index_name, input_dto.file_id, metadata_to_sync
                )
            except Exception as e:
                logger.error(
                    "Failed to sync metadata to vector index for file '%s': %s",
                    input_dto.file_id,
                    e,
                )

        return UpdateMetadataOutput(
            file_id=doc.document.file_id,
            filename=doc.document.blob_name,
            updated_at=doc.document.last_updated,
            metadata=doc.metadata,
        )
