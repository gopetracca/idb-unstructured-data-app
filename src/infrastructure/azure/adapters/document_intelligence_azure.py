"""Azure Document Intelligence adapter implementing DocumentIntelligencePort."""

import logging
from datetime import datetime

from azure.ai.documentintelligence.models import AnalyzeResult, DocumentContentFormat
from azure.core.exceptions import HttpResponseError

from src.application.ports.document_intelligence import DocumentIntelligencePort
from src.config.settings import DocumentIntelligenceSettings, get_settings
from src.core.entities.document_analysis import (
    BoundingRegion,
    DocumentLine,
    DocumentSection,
    DocumentStyle,
    DocumentWord,
    ExtractedFigure,
    ExtractedParagraph,
    ExtractedTable,
    ExtractionMetadata,
    KeyValueElement,
    KeyValuePair,
    MarkdownOutput,
    PageContent,
    SelectionMark,
    TableCell,
    TextSpan,
)
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.clients.document_intelligence_client import (
    DocumentIntelligenceClient,
)

logger = logging.getLogger(__name__)


def _enum_value(value) -> str | None:
    """Return the plain string behind an SDK enum, or None."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _map_span(span) -> TextSpan | None:
    if span is None:
        return None
    return TextSpan(offset=span.offset or 0, length=span.length or 0)


def _map_spans(spans) -> list[TextSpan]:
    return [TextSpan(offset=s.offset or 0, length=s.length or 0) for s in (spans or [])]


def _map_regions(regions) -> list[BoundingRegion]:
    return [
        BoundingRegion(
            page_number=region.page_number,
            polygon=list(getattr(region, "polygon", None) or []),
        )
        for region in (regions or [])
    ]


def _map_kv_element(element) -> KeyValueElement | None:
    if element is None:
        return None
    return KeyValueElement(
        content=getattr(element, "content", None) or "",
        spans=_map_spans(getattr(element, "spans", None)),
        bounding_regions=_map_regions(getattr(element, "bounding_regions", None)),
    )


def _caption_content(caption) -> str | None:
    if caption is None:
        return None
    return getattr(caption, "content", None)


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
        logger.debug(
            "Analyzing document: file_id=%s, content_type=%s, size=%d bytes",
            file_id,
            content_type,
            len(document_content),
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
                "Azure Document Intelligence error: file_id=%s, status=%s, message=%s",
                file_id,
                e.status_code,
                e.message,
                exc_info=True,
            )
            raise DocumentProcessingError(
                message=f"Azure Document Intelligence failed: {e.message}",
                file_id=file_id,
                stage="convert",
                details={"status_code": e.status_code, "error_code": e.error.code if e.error else None},
            ) from e

        except Exception as e:
            logger.error(
                "Unexpected error during document analysis: file_id=%s, error=%s",
                file_id,
                e,
                exc_info=True,
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

        Everything the service returned is carried across: the markdown, the structural
        elements (tables, figures, paragraphs, sections, styles, key-value pairs), the
        per-page layout, and the spans and bounding regions that tie each element back to
        the text and to the page. The verbatim response rides along in `raw_analysis` for
        the caller to persist as a sidecar; it is excluded from serialisation.

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
                        # The service's own page number when it has one: for a multi-file
                        # or partial analysis it need not match the enumeration index.
                        page_number=getattr(page, "page_number", None) or idx,
                        text=page_text,
                        word_count=page_word_count,
                        width=getattr(page, "width", None),
                        height=getattr(page, "height", None),
                        unit=_enum_value(getattr(page, "unit", None)),
                        angle=getattr(page, "angle", None),
                        spans=_map_spans(getattr(page, "spans", None)),
                        lines=[
                            DocumentLine(
                                content=line.content or "",
                                spans=_map_spans(getattr(line, "spans", None)),
                                polygon=list(getattr(line, "polygon", None) or []),
                            )
                            for line in (getattr(page, "lines", None) or [])
                        ],
                        words=[
                            DocumentWord(
                                content=word.content or "",
                                confidence=getattr(word, "confidence", None),
                                span=_map_span(getattr(word, "span", None)),
                                polygon=list(getattr(word, "polygon", None) or []),
                            )
                            for word in (page.words or [])
                        ],
                        selection_marks=[
                            SelectionMark(
                                state=_enum_value(getattr(mark, "state", None)),
                                confidence=getattr(mark, "confidence", None),
                                spans=_map_spans(getattr(mark, "spans", None)),
                                polygon=list(getattr(mark, "polygon", None) or []),
                            )
                            for mark in (getattr(page, "selection_marks", None) or [])
                        ],
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

        tables = [self._map_table(table) for table in (result.tables or [])]
        figures = [self._map_figure(figure) for figure in (getattr(result, "figures", None) or [])]
        paragraphs = [
            ExtractedParagraph(
                content=paragraph.content or "",
                role=_enum_value(getattr(paragraph, "role", None)),
                spans=_map_spans(getattr(paragraph, "spans", None)),
                bounding_regions=_map_regions(getattr(paragraph, "bounding_regions", None)),
            )
            for paragraph in (getattr(result, "paragraphs", None) or [])
        ]
        sections = [
            DocumentSection(
                elements=list(getattr(section, "elements", None) or []),
                spans=_map_spans(getattr(section, "spans", None)),
            )
            for section in (getattr(result, "sections", None) or [])
        ]
        styles = [
            DocumentStyle(
                is_handwritten=getattr(style, "is_handwritten", None),
                confidence=getattr(style, "confidence", None),
                font_style=_enum_value(getattr(style, "font_style", None)),
                font_weight=_enum_value(getattr(style, "font_weight", None)),
                color=getattr(style, "color", None),
                background_color=getattr(style, "background_color", None),
                similar_font_family=getattr(style, "similar_font_family", None),
                spans=_map_spans(getattr(style, "spans", None)),
            )
            for style in (getattr(result, "styles", None) or [])
        ]
        key_value_pairs = [
            KeyValuePair(
                key=_map_kv_element(getattr(pair, "key", None)) or KeyValueElement(),
                value=_map_kv_element(getattr(pair, "value", None)),
                confidence=getattr(pair, "confidence", None),
            )
            for pair in (getattr(result, "key_value_pairs", None) or [])
        ]

        # Create extraction metadata
        extraction_metadata = ExtractionMetadata(
            page_count=len(pages),
            word_count=total_word_count,
            extraction_confidence=round(confidence, 4),
            extraction_method="azure-document-intelligence",
            api_version=result.api_version or self._settings.api_version,
            table_count=len(tables),
            figure_count=len(figures),
            paragraph_count=len(paragraphs),
            # Flipped by whoever actually writes the sidecar; the adapter only supplies it.
            raw_analysis_stored=False,
        )

        logger.debug(
            "Document analysis mapped: file_id=%s, pages=%d, words=%d, confidence=%.4f, "
            "tables=%d, figures=%d, paragraphs=%d",
            file_id,
            len(pages),
            total_word_count,
            confidence,
            len(tables),
            len(figures),
            len(paragraphs),
        )

        return MarkdownOutput(
            file_id=file_id,
            file_version=file_version,
            extracted_text=extracted_text,
            pages=pages,
            extraction_metadata=extraction_metadata,
            created_at=datetime.utcnow(),
            tables=tables,
            figures=figures,
            paragraphs=paragraphs,
            sections=sections,
            styles=styles,
            key_value_pairs=key_value_pairs,
            content_format=_enum_value(getattr(result, "content_format", None)),
            model_id=getattr(result, "model_id", None),
            raw_analysis=self._raw_payload(result),
        )

    @staticmethod
    def _raw_payload(result: AnalyzeResult) -> dict | None:
        """Serialise the response verbatim, tolerating a result that cannot serialise.

        A raw copy that fails to serialise must not cost us the typed output, which is the
        pipeline's actual contract — so this degrades to None and is reported as
        `raw_analysis_stored=False` rather than raising.
        """
        try:
            return DocumentIntelligenceClient.to_raw_payload(result)
        except Exception:
            logger.warning("Could not serialise raw analysis result", exc_info=True)
            return None

    @staticmethod
    def _map_table(table) -> ExtractedTable:
        """Map one table, keeping every cell's position in the grid."""
        return ExtractedTable(
            row_count=getattr(table, "row_count", 0) or 0,
            column_count=getattr(table, "column_count", 0) or 0,
            cells=[
                TableCell(
                    row_index=getattr(cell, "row_index", 0) or 0,
                    column_index=getattr(cell, "column_index", 0) or 0,
                    # The service omits a span of 1 rather than sending it.
                    row_span=getattr(cell, "row_span", None) or 1,
                    column_span=getattr(cell, "column_span", None) or 1,
                    kind=_enum_value(getattr(cell, "kind", None)) or "content",
                    content=cell.content or "",
                    elements=list(getattr(cell, "elements", None) or []),
                    spans=_map_spans(getattr(cell, "spans", None)),
                    bounding_regions=_map_regions(getattr(cell, "bounding_regions", None)),
                )
                for cell in (getattr(table, "cells", None) or [])
            ],
            caption=_caption_content(getattr(table, "caption", None)),
            footnotes=[
                footnote.content or ""
                for footnote in (getattr(table, "footnotes", None) or [])
            ],
            spans=_map_spans(getattr(table, "spans", None)),
            bounding_regions=_map_regions(getattr(table, "bounding_regions", None)),
        )

    @staticmethod
    def _map_figure(figure) -> ExtractedFigure:
        """Map one figure."""
        return ExtractedFigure(
            figure_id=getattr(figure, "id", None),
            caption=_caption_content(getattr(figure, "caption", None)),
            footnotes=[
                footnote.content or ""
                for footnote in (getattr(figure, "footnotes", None) or [])
            ],
            elements=list(getattr(figure, "elements", None) or []),
            spans=_map_spans(getattr(figure, "spans", None)),
            bounding_regions=_map_regions(getattr(figure, "bounding_regions", None)),
        )

    def close(self) -> None:
        """Close the underlying client connection."""
        if self._client:
            self._client.close()
