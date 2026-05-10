"""Use case for processing documents with Document Intelligence."""

import json
import logging
import time
import uuid

from src.application.dto.document_analysis import (
    DocumentAnalysisRequest,
    DocumentAnalysisResult,
    ProcessingStatus,
)
from src.application.ports.blob_client import BlobClientPort
from src.application.ports.document_intelligence import DocumentIntelligencePort
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.ports.processing_events import ProcessingEventsPort
from src.core.entities.pipeline_state import ProcessingStage
from src.core.errors import (
    DocumentNotFoundError,
    DocumentProcessingError,
    UnsupportedFormatError,
)

logger = logging.getLogger(__name__)


class ProcessDocumentUseCase:
    """
    Use case for processing documents and extracting markdown.

    Orchestrates the flow:
    1. Retrieve raw document from blob storage
    2. Validate content type is supported
    3. Call document intelligence adapter
    4. Store markdown output in text container
    5. Update pipeline state stage
    6. Return result with markdown URL
    """

    def __init__(
        self,
        blob_client: BlobClientPort,
        document_intelligence: DocumentIntelligencePort,
        pipeline_store: PipelineStorePort,
        processing_events: ProcessingEventsPort | None = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            blob_client: Client for blob storage operations
            document_intelligence: Document intelligence port implementation
            pipeline_store: Repository for pipeline state operations
            processing_events: Optional ProcessingEventsPort for stage tracking
        """
        self._blob_client = blob_client
        self._document_intelligence = document_intelligence
        self._pipeline_store = pipeline_store
        self._processing_events = processing_events

    async def execute(self, request: DocumentAnalysisRequest) -> DocumentAnalysisResult:
        """
        Execute the document processing use case.

        Args:
            request: Document analysis request

        Returns:
            DocumentAnalysisResult with processing status and output URL

        Raises:
            DocumentNotFoundError: If the document doesn't exist
            UnsupportedFormatError: If the document format isn't supported
            DocumentProcessingError: If processing fails
        """
        correlation_id = request.correlation_id or str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            f"Starting document processing: file_id={request.file_id}, "
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

            # Use blob reference from SQL (SSOT for content location)
            if not doc.document.raw_blob_ref:
                raise DocumentProcessingError(
                    message="No raw blob reference found in file index",
                    file_id=request.file_id,
                    stage="convert",
                    details={"reason": "missing_raw_blob_ref"},
                )

            source_blob_path = doc.document.raw_blob_ref

            # Check if blob exists
            exists = await self._blob_client.blob_exists(
                request.source_container, source_blob_path
            )
            if not exists:
                raise DocumentNotFoundError(
                    file_id=request.file_id,
                    container=request.source_container,
                    details={"blob_path": source_blob_path},
                )

            # Validate content type
            if not self._document_intelligence.is_format_supported(doc.document.content_type):
                raise UnsupportedFormatError(
                    content_type=doc.document.content_type,
                    supported_formats=self._document_intelligence.get_supported_formats(),
                )

            # Update status to processing
            await self._pipeline_store.mark_processing(
                request.tenant_id, request.file_id, ProcessingStage.CONVERT
            )

            # Download raw document
            document_content = await self._blob_client.download_blob(
                request.source_container, source_blob_path
            )

            logger.info(
                f"Downloaded document: file_id={request.file_id}, "
                f"size={len(document_content)} bytes"
            )

            # Analyze document
            markdown_output = await self._document_intelligence.analyze_document(
                document_content=document_content,
                content_type=doc.document.content_type,
                file_id=request.file_id,
                file_version=doc.document.file_version,
            )

            # Store markdown output (path format: tenant_id/file_id/text.json)
            output_blob_path = f"{request.tenant_id}/{request.file_id}/text.json"
            output_data = json.dumps(markdown_output.model_dump(mode="json"), indent=2)

            await self._blob_client.upload_blob(
                container=request.output_container,
                blob_path=output_blob_path,
                data=output_data,
                content_type="application/json; charset=utf-8",
            )

            # Store text blob reference in SQL (SSOT for content location)
            await self._pipeline_store.update_blob_references(
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                text_blob_ref=output_blob_path,
            )

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Build output URL (relative path for now)
            markdown_url = f"{request.output_container}/{output_blob_path}"

            logger.info(
                f"Document processing completed: file_id={request.file_id}, "
                f"processing_time_ms={processing_time_ms}, "
                f"pages={markdown_output.extraction_metadata.page_count}"
            )

            await self._log_stage_transition(
                request=request,
                status="success",
                duration_ms=processing_time_ms,
            )

            return DocumentAnalysisResult(
                file_id=request.file_id,
                status=ProcessingStatus.COMPLETED,
                markdown_url=markdown_url,
                correlation_id=correlation_id,
                processing_time_ms=processing_time_ms,
            )

        except (DocumentNotFoundError, UnsupportedFormatError) as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._log_stage_transition(
                request=request,
                status="failed",
                duration_ms=elapsed_ms,
                error_message=str(e),
            )
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
                f"Document processing failed: file_id={request.file_id}, "
                f"error={str(e)}",
                exc_info=True,
            )

            raise DocumentProcessingError(
                message=f"Failed to process document: {str(e)}",
                file_id=request.file_id,
                stage="convert",
                details={"correlation_id": correlation_id},
            ) from e

    async def _log_stage_transition(
        self,
        request: DocumentAnalysisRequest,
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
                stage=ProcessingStage.CONVERT.value,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
        except Exception:
            logger.warning("Failed to log stage event", exc_info=True)
