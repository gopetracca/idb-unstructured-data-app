"""Upload document use case."""

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime

from src.application.dto.document_dto import UploadDocumentInput, UploadDocumentOutput
from src.application.ports.blob_store import BlobStorePort
from src.application.ports.document_store import DocumentStorePort
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.errors import DuplicateDocumentError, FileSizeExceededError, InvalidFileTypeError, StorageError
from src.core.value_objects.document_metadata import DocumentMetadata, get_metadata_model

logger = logging.getLogger(__name__)


class UploadDocumentUseCase:
    """
    Use case for uploading documents to the RAG system.

    Splits incoming metadata into promoted fields (-> SQL columns)
    and flexible fields (-> JSON blob).
    """

    DEFAULT_ALLOWED_TYPES = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    DEFAULT_MAX_SIZE_BYTES = 150 * 1024 * 1024

    def __init__(
        self,
        blob_store: BlobStorePort,
        metadata_store: DocumentStorePort,
        container_name: str = "raw",
        allowed_types: list[str] | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        self._blob_store = blob_store
        self._metadata_store = metadata_store
        self._container_name = container_name
        self._allowed_types = allowed_types or self.DEFAULT_ALLOWED_TYPES
        self._max_size_bytes = max_size_bytes or self.DEFAULT_MAX_SIZE_BYTES

    async def execute(self, input_dto: UploadDocumentInput) -> UploadDocumentOutput:
        """
        Execute the upload document use case.

        All metadata fields are stored as SQL columns in file_metadata.
        """
        # Validate file type and size synchronously before any I/O
        if input_dto.content_type not in self._allowed_types:
            raise InvalidFileTypeError(input_dto.content_type, self._allowed_types)

        size_bytes = len(input_dto.content)
        if size_bytes > self._max_size_bytes:
            raise FileSizeExceededError(size_bytes, self._max_size_bytes)

        # Check for duplicate before uploading
        existing = await self._metadata_store.query_by_ezshare_id(
            tenant_id=input_dto.tenant_id,
            ezshare_id=input_dto.ezshare_id,
        )
        if existing:
            raise DuplicateDocumentError(
                ezshare_id=input_dto.ezshare_id,
                existing_file_id=existing.document.file_id,
            )

        file_id = str(uuid.uuid4())
        upload_timestamp = datetime.now(UTC)
        blob_path = f"{input_dto.tenant_id}/{file_id}/{input_dto.filename}"

        # Compute hash (CPU-bound) and upload to blob (I/O-bound) concurrently
        try:
            content_hash, _ = await asyncio.gather(
                asyncio.to_thread(lambda: hashlib.sha256(input_dto.content).hexdigest()),
                self._blob_store.upload(
                    container=self._container_name,
                    blob_path=blob_path,
                    data=input_dto.content,
                    content_type=input_dto.content_type,
                    metadata={"file_id": file_id, "tenant_id": input_dto.tenant_id},
                ),
            )
        except Exception as e:
            raise StorageError("upload", str(e)) from e

        # All metadata fields are promoted SQL columns — no flexible JSON split
        metadata_dict = input_dto.metadata
        document_type = metadata_dict.get("document_type")
        model_class = get_metadata_model(document_type)
        promoted_names = model_class.promoted_field_names()

        promoted = {k: v for k, v in metadata_dict.items() if k in promoted_names}

        # Auto-derive file_extension from filename if not provided
        if not promoted.get("file_extension"):
            ext = os.path.splitext(input_dto.filename)[1]
            if ext:
                promoted["file_extension"] = ext

        # Create Document entity (identity + storage)
        document = Document(
            tenant_id=input_dto.tenant_id,
            file_id=file_id,
            blob_name=input_dto.filename,
            content_type=input_dto.content_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            upload_timestamp=upload_timestamp,
            raw_blob_ref=blob_path,
            collection_name=input_dto.collection_name,
            ezshare_id=input_dto.ezshare_id,
        )

        # Create PipelineState entity (processing state)
        pipeline = PipelineState(
            file_id=file_id,
            current_stage=ProcessingStage.DISPATCHER,
            overall_status=OverallStatus.QUEUED,
            chunking_strategy=input_dto.chunking_strategy.model_dump_json(),
        )

        # Create DocumentMetadata entity (all fields stored as SQL columns)
        metadata = model_class(file_id=file_id, **promoted)

        # Compose DocumentComplete
        doc_complete = DocumentComplete(
            document=document,
            pipeline=pipeline,
            metadata=metadata,
        )

        # Save metadata
        try:
            await self._metadata_store.create(doc_complete)
        except Exception as e:
            logger.exception(
                "Failed to persist document metadata: tenant_id=%s, file_id=%s, ezshare_id=%s",
                input_dto.tenant_id,
                file_id,
                input_dto.ezshare_id,
            )
            try:
                await self._blob_store.delete(self._container_name, blob_path)
            except Exception:
                pass
            raise StorageError("create_metadata", str(e)) from e

        return UploadDocumentOutput(
            file_id=file_id,
            filename=input_dto.filename,
            size_bytes=size_bytes,
            mime_type=input_dto.content_type,
            uploaded_at=upload_timestamp,
            metadata=metadata,
        )
