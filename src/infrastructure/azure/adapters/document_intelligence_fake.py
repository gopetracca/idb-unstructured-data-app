"""Fake Document Intelligence adapter for local development and testing."""

import asyncio
import logging
from datetime import datetime

from src.application.ports.document_intelligence import DocumentIntelligencePort
from src.core.entities.document_analysis import (
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)
from src.core.errors import DocumentProcessingError, UnsupportedFormatError

logger = logging.getLogger(__name__)


class FakeDocumentIntelligenceAdapter(DocumentIntelligencePort):
    """
    Fake implementation of Document Intelligence for local development.

    This adapter simulates document processing without requiring Azure resources.
    It provides simple text extraction for testing.
    """

    SUPPORTED_FORMATS = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/bmp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ]

    def __init__(
        self,
        simulated_delay_seconds: float = 0.5,
        simulated_confidence: float = 0.95,
    ) -> None:
        """
        Initialize the fake adapter.

        Args:
            simulated_delay_seconds: Delay to simulate processing time
            simulated_confidence: Simulated extraction confidence (0-1)
        """
        self._delay = simulated_delay_seconds
        self._confidence = simulated_confidence

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
        Analyze a document and extract text.

        For the fake implementation:
        - Text files: Returns content directly
        - Other files: Returns placeholder text with file info

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
            f"Fake adapter analyzing document: file_id={file_id}, "
            f"content_type={content_type}, size={len(document_content)} bytes"
        )

        # Validate content type
        if not self.is_format_supported(content_type):
            raise UnsupportedFormatError(
                content_type=content_type,
                supported_formats=self.SUPPORTED_FORMATS,
            )

        # Simulate processing delay
        await asyncio.sleep(self._delay)

        try:
            # Extract text based on content type
            if content_type == "text/plain":
                extracted_text = self._extract_text_content(document_content)
            else:
                extracted_text = self._generate_placeholder_content(
                    document_content, content_type, file_id
                )

            # Calculate word count
            words = extracted_text.split()
            word_count = len(words)

            # Create page content (simulate single page for fake)
            pages = [
                PageContent(
                    page_number=1,
                    text=extracted_text,
                    word_count=word_count,
                )
            ]

            # Create extraction metadata
            extraction_metadata = ExtractionMetadata(
                page_count=1,
                word_count=word_count,
                extraction_confidence=self._confidence,
                extraction_method="fake-document-intelligence",
                api_version="fake-1.0.0",
            )

            logger.info(
                f"Fake adapter completed: file_id={file_id}, "
                f"word_count={word_count}, pages=1"
            )

            return MarkdownOutput(
                file_id=file_id,
                file_version=file_version,
                extracted_text=extracted_text,
                pages=pages,
                extraction_metadata=extraction_metadata,
                created_at=datetime.utcnow(),
            )

        except UnsupportedFormatError:
            raise
        except Exception as e:
            logger.error("Fake adapter failed: file_id=%s, error=%s", file_id, e, exc_info=True)
            raise DocumentProcessingError(
                message=f"Fake extraction failed: {str(e)}",
                file_id=file_id,
                stage="convert",
            ) from e

    def _extract_text_content(self, content: bytes) -> str:
        """Extract text from text/plain content."""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("latin-1")
            except Exception:
                return content.decode("utf-8", errors="replace")

    def _generate_placeholder_content(
        self,
        content: bytes,
        content_type: str,
        file_id: str,
    ) -> str:
        """Generate placeholder text for non-text documents."""
        # Get file type description
        type_descriptions = {
            "application/pdf": "PDF document",
            "image/png": "PNG image",
            "image/jpeg": "JPEG image",
            "image/jpg": "JPEG image",
            "image/tiff": "TIFF image",
            "image/bmp": "BMP image",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word document",
        }

        doc_type = type_descriptions.get(content_type, "document")
        file_size = len(content)

        # Generate placeholder text
        extracted_text = (
            f"[Simulated extraction from {doc_type}]\n\n"
            f"File ID: {file_id}\n"
            f"Content Type: {content_type}\n"
            f"Size: {file_size:,} bytes\n\n"
            "This is a placeholder extraction generated by the fake Document Intelligence adapter. "
            "In production, this would contain the actual extracted text from the document.\n\n"
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor "
            "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
            "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
        )

        return extracted_text
