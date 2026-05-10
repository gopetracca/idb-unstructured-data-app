"""Azure Document Intelligence adapter implementing DocumentIntelligencePort."""

import logging
from datetime import datetime

from azure.ai.documentintelligence.models import AnalyzeResult, DocumentContentFormat
from azure.core.exceptions import HttpResponseError

from src.application.ports.document_intelligence import DocumentIntelligencePort
from src.config.settings import DocumentIntelligenceSettings, get_settings
from src.core.entities.document_analysis import (
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.clients.document_intelligence_client import (
    DocumentIntelligenceClient,
)

logger = logging.getLogger(__name__)


class AzureDocumentIntelligenceAdapter(DocumentIntelligencePort):
    """
    Azure Document Intelligence implementation of DocumentIntelligencePort.

    Uses the Azure Document Intelligence service to analyze documents
    and extract text as markdown.
    """

    SUPPORTED_FORMATS = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/bmp",
        "image/heif",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/html",
    ]

    def __init__(
        self,
        settings: DocumentIntelligenceSettings | None = None,
        client: DocumentIntelligenceClient | None = None,
    ) -> None:
        """
        Initialize the Azure adapter.

        Args:
            settings: Optional DocumentIntelligenceSettings instance
            client: Optional DocumentIntelligenceClient instance (for testing)
        """
        self._settings = settings or get_settings().document_intelligence
        self._client = client or DocumentIntelligenceClient(self._settings)

    def get_supported_formats(self) -> list[str]:
        """Get list of supported document MIME types."""
        return self.SUPPORTED_FORMATS.copy()

    async def analyze_document(
        self,
        document_content: bytes,
        content_type: str,
        file_id: str,
        file_version: int = 1,
    ) -> MarkdownOutput:
        """
        Analyze a document using Azure Document Intelligence.

        Args:
            document_content: Raw document bytes
            content_type: MIME type of the document
            file_id: Unique identifier for the file
            file_version: Version number of the file

        Returns:
            MarkdownOutput containing extracted text and metadata

        Raises:
            UnsupportedFormatError: If content_type is not supported
            DocumentProcessingError: If extraction fails
        """
        logger.info(
            f"Azure adapter analyzing document: file_id={file_id}, "
            f"content_type={content_type}, size={len(document_content)} bytes"
        )

        # Validate content type
        if not self.is_format_supported(content_type):
            raise UnsupportedFormatError(
                content_type=content_type,
                supported_formats=self.SUPPORTED_FORMATS,
            )

        try:
            # Call Azure Document Intelligence
            result = await self._client.analyze_document(
                document_content=document_content,
                content_type=content_type,
                output_format=DocumentContentFormat.MARKDOWN,
            )

            # Convert Azure result to domain model
            return self._map_result_to_output(result, file_id, file_version)

        except HttpResponseError as e:
            logger.error(
                f"Azure Document Intelligence error: file_id={file_id}, "
                f"status={e.status_code}, message={e.message}"
            )
            raise DocumentProcessingError(
                message=f"Azure Document Intelligence failed: {e.message}",
                file_id=file_id,
                stage="convert",
                details={"status_code": e.status_code, "error_code": e.error.code if e.error else None},
            ) from e

        except Exception as e:
            logger.error(
                f"Unexpected error during document analysis: file_id={file_id}, "
                f"error={str(e)}"
            )
            raise DocumentProcessingError(
                message=f"Document analysis failed: {str(e)}",
                file_id=file_id,
                stage="convert",
            ) from e

    def _map_result_to_output(
        self,
        result: AnalyzeResult,
        file_id: str,
        file_version: int,
    ) -> MarkdownOutput:
        """
        Map Azure AnalyzeResult to domain MarkdownOutput.

        Args:
            result: Azure Document Intelligence AnalyzeResult
            file_id: File identifier
            file_version: File version

        Returns:
            MarkdownOutput domain model
        """
        # Keep raw extracted output returned by Document Intelligence.
        extracted_text = result.content or ""

        # Process pages
        pages = []
        total_word_count = 0

        if result.pages:
            for idx, page in enumerate(result.pages, start=1):
                # Extract text for this page from words
                page_text = ""
                page_word_count = 0

                if page.words:
                    page_words = [w.content for w in page.words]
                    page_text = " ".join(page_words)
                    page_word_count = len(page_words)

                pages.append(
                    PageContent(
                        page_number=idx,
                        text=page_text,
                        word_count=page_word_count,
                    )
                )
                total_word_count += page_word_count

        # Fallback to page-level text if service content is empty.
        if not extracted_text:
            extracted_text = "\n\n".join(page.text for page in pages if page.text).strip()

        # If no pages but we have content, create a single page
        if not pages and extracted_text:
            words = extracted_text.split()
            total_word_count = len(words)
            pages.append(
                PageContent(
                    page_number=1,
                    text=extracted_text,
                    word_count=total_word_count,
                )
            )

        # Calculate average confidence from pages
        confidence = 0.0
        if result.pages:
            page_confidences = []
            for page in result.pages:
                if page.words:
                    word_confidences = [
                        w.confidence for w in page.words if w.confidence is not None
                    ]
                    if word_confidences:
                        page_confidences.append(
                            sum(word_confidences) / len(word_confidences)
                        )
            if page_confidences:
                confidence = sum(page_confidences) / len(page_confidences)

        # Create extraction metadata
        extraction_metadata = ExtractionMetadata(
            page_count=len(pages),
            word_count=total_word_count,
            extraction_confidence=round(confidence, 4),
            extraction_method="azure-document-intelligence",
            api_version=result.api_version or self._settings.api_version,
        )

        logger.info(
            f"Document analysis mapped: file_id={file_id}, "
            f"pages={len(pages)}, words={total_word_count}, "
            f"confidence={confidence:.4f}"
        )

        return MarkdownOutput(
            file_id=file_id,
            file_version=file_version,
            extracted_text=extracted_text,
            pages=pages,
            extraction_metadata=extraction_metadata,
            created_at=datetime.utcnow(),
        )

    def close(self) -> None:
        """Close the underlying client connection."""
        if self._client:
            self._client.close()
