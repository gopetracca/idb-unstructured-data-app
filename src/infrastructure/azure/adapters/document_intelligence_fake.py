"""Fake Document Intelligence adapter for local development and testing."""

import asyncio
import logging
from datetime import datetime

from src.application.ports.document_intelligence import DocumentIntelligencePort
from src.core.entities.document_analysis import (
    BoundingRegion,
    DocumentLine,
    ExtractedParagraph,
    ExtractedTable,
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
    TableCell,
    TextSpan,
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
                body_text = self._extract_text_content(document_content)
            else:
                body_text = self._generate_placeholder_content(
                    document_content, content_type, file_id
                )

            # Append a rendered table so the fake's markdown and its structural elements
            # describe the same document, the way the real service's do.
            table_markdown = self._table_markdown(file_id)
            extracted_text = f"{body_text}\n\n{table_markdown}"
            table_offset = len(body_text) + 2
            table = self._simulated_table(
                file_id, offset=table_offset, length=len(table_markdown)
            )

            # Calculate word count
            words = extracted_text.split()
            word_count = len(words)

            lines = self._lines_from_text(extracted_text)
            paragraphs = self._simulated_paragraphs(body_text)

            # Create page content (simulate single page for fake)
            pages = [
                PageContent(
                    page_number=1,
                    text=extracted_text,
                    word_count=word_count,
                    width=8.5,
                    height=11.0,
                    unit="inch",
                    angle=0.0,
                    spans=[TextSpan(offset=0, length=len(extracted_text))],
                    lines=lines,
                )
            ]

            # Create extraction metadata
            extraction_metadata = ExtractionMetadata(
                page_count=1,
                word_count=word_count,
                extraction_confidence=self._confidence,
                extraction_method="fake-document-intelligence",
                api_version="fake-1.0.0",
                table_count=1,
                figure_count=0,
                paragraph_count=len(paragraphs),
                raw_analysis_stored=False,
            )

            logger.info(
                f"Fake adapter completed: file_id={file_id}, "
                f"word_count={word_count}, pages=1, tables=1"
            )

            return MarkdownOutput(
                file_id=file_id,
                file_version=file_version,
                extracted_text=extracted_text,
                pages=pages,
                extraction_metadata=extraction_metadata,
                created_at=datetime.utcnow(),
                tables=[table],
                paragraphs=paragraphs,
                content_format="markdown",
                model_id="fake-layout",
                # The fake has no service response to copy, and inventing one would make
                # `raw_analysis_stored` lie about provenance.
                raw_analysis=None,
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

    def _table_markdown(self, file_id: str) -> str:
        """Render the simulated table the way the layout model renders tables."""
        return (
            "| Simulated Table ||\n"
            "| --- | --- |\n"
            "| Field | Value |\n"
            f"| File ID | {file_id} |"
        )

    def _simulated_table(self, file_id: str, offset: int, length: int) -> ExtractedTable:
        """Build the structural twin of `_table_markdown`.

        Deliberately includes a merged cell and a column-header row: those are the cases
        that a rendered-markdown-only representation cannot round-trip, so local runs
        against the fake exercise the same reconstruction path as the real service.
        """
        region = [BoundingRegion(page_number=1, polygon=[1.0, 1.0, 7.5, 1.0, 7.5, 3.0, 1.0, 3.0])]
        return ExtractedTable(
            row_count=3,
            column_count=2,
            cells=[
                TableCell(
                    row_index=0,
                    column_index=0,
                    column_span=2,
                    kind="columnHeader",
                    content="Simulated Table",
                    bounding_regions=region,
                ),
                TableCell(row_index=1, column_index=0, kind="columnHeader", content="Field"),
                TableCell(row_index=1, column_index=1, kind="columnHeader", content="Value"),
                TableCell(row_index=2, column_index=0, content="File ID"),
                TableCell(row_index=2, column_index=1, content=file_id),
            ],
            caption="Simulated extraction summary",
            footnotes=["Produced by the fake Document Intelligence adapter."],
            spans=[TextSpan(offset=offset, length=length)],
            bounding_regions=region,
        )

    @staticmethod
    def _lines_from_text(text: str) -> list[DocumentLine]:
        """Split text into lines, keeping each line's span into the text."""
        lines: list[DocumentLine] = []
        offset = 0
        for raw_line in text.split("\n"):
            if raw_line.strip():
                lines.append(
                    DocumentLine(
                        content=raw_line,
                        spans=[TextSpan(offset=offset, length=len(raw_line))],
                    )
                )
            offset += len(raw_line) + 1
        return lines

    @staticmethod
    def _simulated_paragraphs(body_text: str) -> list[ExtractedParagraph]:
        """Emit a titled first paragraph and a body paragraph, each with its span."""
        blocks = [block for block in body_text.split("\n\n") if block.strip()]
        paragraphs: list[ExtractedParagraph] = []
        offset = 0
        for index, block in enumerate(blocks):
            start = body_text.find(block, offset)
            paragraphs.append(
                ExtractedParagraph(
                    content=block,
                    role="title" if index == 0 else None,
                    spans=[TextSpan(offset=start, length=len(block))],
                    bounding_regions=[BoundingRegion(page_number=1, polygon=[])],
                )
            )
            offset = start + len(block)
        return paragraphs
