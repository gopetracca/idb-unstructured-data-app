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
from src.config.settings import get_settings
from src.core.entities.document_analysis import MarkdownOutput
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
    4. Store the verbatim analysis response and the markdown output in the text container
       (the sidecar is rolled back if the text output cannot be stored, so the two are
       never left describing different runs)
    5. Update pipeline state stage
    6. Return result with markdown URL
    """

    def __init__(
        self,
        blob_client: BlobClientPort,
        document_intelligence: DocumentIntelligencePort,
        pipeline_store: PipelineStorePort,
        processing_events: ProcessingEventsPort | None = None,
        persist_raw_analysis: bool | None = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            blob_client: Client for blob storage operations
            document_intelligence: Document intelligence port implementation
            pipeline_store: Repository for pipeline state operations
            processing_events: Optional ProcessingEventsPort for stage tracking
            persist_raw_analysis: Whether to store the verbatim analysis response as a
                sidecar blob. Defaults to DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT.
        """
        self._blob_client = blob_client
        self._document_intelligence = document_intelligence
        self._pipeline_store = pipeline_store
        self._processing_events = processing_events
        if persist_raw_analysis is None:
            persist_raw_analysis = get_settings().document_intelligence.persist_raw_result
        self._persist_raw_analysis = persist_raw_analysis

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

            # Store the verbatim analysis first: whether it landed is recorded in the
            # extraction metadata that text.json carries, so it has to be known before
            # text.json is serialised.
            analysis_blob_path = await self._store_raw_analysis(request, markdown_output)
            markdown_output.extraction_metadata.raw_analysis_stored = (
                analysis_blob_path is not None
            )

            # Store markdown output (path format: tenant_id/file_id/text.json)
            output_blob_path = f"{request.tenant_id}/{request.file_id}/text.json"
            output_data = json.dumps(markdown_output.model_dump(mode="json"), indent=2)

            try:
                await self._blob_client.upload_blob(
                    container=request.output_container,
                    blob_path=output_blob_path,
                    data=output_data,
                    content_type="application/json; charset=utf-8",
                )
            except Exception:
                # Both artefacts live at fixed paths, so the sidecar written moments ago
                # has already replaced the previous run's. Leaving it there would pair a
                # new analysis.json with the text.json still on disk from the earlier run
                # — two halves of different extractions, indistinguishable to a reader.
                await self._unpublish_raw_analysis(request, analysis_blob_path)
                raise

            # Store blob references in SQL (SSOT for content location). When this run
            # produced no sidecar, the reference is cleared rather than left alone: a
            # re-processed document would otherwise keep pointing at the previous run's
            # analysis.json while its text.json says raw_analysis_stored=false.
            await self._pipeline_store.update_blob_references(
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                text_blob_ref=output_blob_path,
                analysis_blob_ref=analysis_blob_path,
                clear_analysis_blob_ref=analysis_blob_path is None,
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

    async def _store_raw_analysis(
        self,
        request: DocumentAnalysisRequest,
        markdown_output: MarkdownOutput,
    ) -> str | None:
        """Persist the verbatim analysis response as a sidecar blob.

        Returns the blob path, or None if there was nothing to store, persistence is
        disabled, or the write failed. A failure here is deliberately not fatal: text.json
        and its blob reference are the pipeline's contract, and losing the sidecar
        degrades fidelity without breaking the document. The loss is visible afterwards as
        `extraction_metadata.raw_analysis_stored=false` and a null `analysis_blob_ref`.
        """
        if not self._persist_raw_analysis or markdown_output.raw_analysis is None:
            return None

        blob_path = f"{request.tenant_id}/{request.file_id}/analysis.json"
        try:
            await self._blob_client.upload_blob(
                container=request.output_container,
                blob_path=blob_path,
                # default=str so a datetime the service returns cannot cost us the copy.
                data=json.dumps(markdown_output.raw_analysis, indent=2, default=str),
                content_type="application/json; charset=utf-8",
            )
        except Exception:
            logger.warning(
                "Failed to store raw analysis result: file_id=%s, blob_path=%s",
                request.file_id,
                blob_path,
                exc_info=True,
            )
            return None

        logger.info(
            "Stored raw analysis result: file_id=%s, blob_path=%s",
            request.file_id,
            blob_path,
        )
        return blob_path

    async def _unpublish_raw_analysis(
        self,
        request: DocumentAnalysisRequest,
        analysis_blob_path: str | None,
    ) -> None:
        """Undo this run's sidecar after the text output failed to store.

        Clearing the reference is the part that matters: the document row is the source of
        truth for where content lives, so a null `analysis_blob_ref` means no reader can
        reach the orphaned sidecar even if the delete below does not land. The delete is
        cleanup on top of that, not the safety property.

        Everything here is best-effort. The run is already failing and will be reported as
        such; a failure to tidy up must not replace that error with a less informative one.
        """
        if analysis_blob_path is None:
            return

        try:
            await self._blob_client.delete_blob(
                request.output_container, analysis_blob_path
            )
        except Exception:
            logger.warning(
                "Could not delete the superseded raw analysis: file_id=%s, blob_path=%s",
                request.file_id,
                analysis_blob_path,
                exc_info=True,
            )

        try:
            await self._pipeline_store.update_blob_references(
                tenant_id=request.tenant_id,
                file_id=request.file_id,
                clear_analysis_blob_ref=True,
            )
        except Exception:
            logger.warning(
                "Could not clear the raw analysis reference after a failed text write: "
                "file_id=%s",
                request.file_id,
                exc_info=True,
            )

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
