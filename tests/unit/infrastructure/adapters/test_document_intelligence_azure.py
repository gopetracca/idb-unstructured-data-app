"""Unit tests for AzureDocumentIntelligenceAdapter.

Fixtures build real `AnalyzeResult` models from service-shaped payloads rather than
MagicMocks. A MagicMock answers every attribute with another MagicMock, so it cannot tell
a field that is mapped from one that is silently dropped — which is the exact failure
these tests exist to catch.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.ai.documentintelligence.models import AnalyzeResult

from src.config.settings import DocumentIntelligenceSettings
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from tests.support.table_reconstruction import assert_cells_tile_grid, assert_spans_resolve

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_document_intelligence_settings() -> DocumentIntelligenceSettings:
    """Create mock Document Intelligence settings."""
    return DocumentIntelligenceSettings(
        endpoint="https://test-di.cognitiveservices.azure.com",
        api_key="test-api-key",
        api_version="2024-11-30",
        use_fake=False,
    )


def analyze_result(**overrides) -> AnalyzeResult:
    """Build an AnalyzeResult from a service-shaped payload."""
    payload = {"apiVersion": "2024-11-30", "modelId": "prebuilt-layout"}
    payload.update(overrides)
    return AnalyzeResult(payload)


# A document with one page and two words — the minimum the older tests asserted on.
SIMPLE_PAYLOAD = {
    "content": "# Hello World\n\nThis is extracted content.",
    "pages": [
        {
            "pageNumber": 1,
            "words": [
                {"content": "Hello", "confidence": 0.95, "span": {"offset": 2, "length": 5}},
                {"content": "World", "confidence": 0.98, "span": {"offset": 8, "length": 5}},
            ],
        }
    ],
}

# A table-bearing document: a merged title cell over a header row over one data row.
# Rendered markdown plus structure, the way the layout model returns both.
TABLE_MARKDOWN = (
    "| Budget Summary ||\n| --- | --- |\n| Year | Amount |\n| 2026 | 1,250 |"
)

TABLE_PAYLOAD = {
    "content": TABLE_MARKDOWN,
    "contentFormat": "markdown",
    "pages": [
        {
            "pageNumber": 1,
            "width": 8.5,
            "height": 11.0,
            "unit": "inch",
            "angle": 0.3,
            "spans": [{"offset": 0, "length": len(TABLE_MARKDOWN)}],
            "words": [
                {"content": "Budget", "confidence": 0.99, "span": {"offset": 2, "length": 6}},
                {"content": "Summary", "confidence": 0.97, "span": {"offset": 9, "length": 7}},
            ],
            "lines": [
                {
                    "content": "| Budget Summary ||",
                    "spans": [{"offset": 0, "length": 19}],
                    "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4],
                },
                {"content": "| Year | Amount |", "spans": [{"offset": 33, "length": 17}]},
            ],
            "selectionMarks": [
                {"state": "selected", "confidence": 0.88, "spans": [{"offset": 0, "length": 1}]}
            ],
        }
    ],
    "tables": [
        {
            "rowCount": 3,
            "columnCount": 2,
            "cells": [
                {
                    "rowIndex": 0,
                    "columnIndex": 0,
                    "columnSpan": 2,
                    "kind": "columnHeader",
                    "content": "Budget Summary",
                    "spans": [{"offset": 2, "length": 14}],
                    "boundingRegions": [
                        {"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4]}
                    ],
                },
                {"rowIndex": 1, "columnIndex": 0, "kind": "columnHeader", "content": "Year"},
                {"rowIndex": 1, "columnIndex": 1, "kind": "columnHeader", "content": "Amount"},
                {"rowIndex": 2, "columnIndex": 0, "content": "2026"},
                {"rowIndex": 2, "columnIndex": 1, "content": "1,250"},
            ],
            "caption": {"content": "Table 1. Budget by year"},
            "footnotes": [{"content": "Amounts in thousands."}],
            "spans": [{"offset": 0, "length": len(TABLE_MARKDOWN)}],
            "boundingRegions": [{"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 3.0, 1.0, 3.0]}],
        }
    ],
    "paragraphs": [
        {"content": "Budget Summary", "role": "title", "spans": [{"offset": 2, "length": 14}]},
        {"content": "page 1", "role": "pageFooter", "spans": [{"offset": 0, "length": 6}]},
    ],
    "figures": [
        {
            "id": "1.1",
            "caption": {"content": "Figure 1. Spend over time"},
            "elements": ["/paragraphs/0"],
            "boundingRegions": [{"pageNumber": 1, "polygon": [2.0, 4.0, 6.0, 4.0, 6.0, 6.0, 2.0, 6.0]}],
        }
    ],
    "sections": [{"elements": ["/paragraphs/0", "/tables/0"]}],
    "styles": [{"isHandwritten": False, "confidence": 0.9, "fontWeight": "bold"}],
    "keyValuePairs": [
        {
            "key": {"content": "Fiscal year", "spans": [{"offset": 0, "length": 11}]},
            "value": {"content": "2026"},
            "confidence": 0.82,
        }
    ],
}


@pytest.fixture
def mock_analyze_result() -> AnalyzeResult:
    """A minimal single-page analysis result."""
    return analyze_result(**SIMPLE_PAYLOAD)


@pytest.fixture
def table_analyze_result() -> AnalyzeResult:
    """An analysis result carrying every structural element the service can return."""
    return analyze_result(**TABLE_PAYLOAD)


def adapter_for(settings, result: AnalyzeResult) -> AzureDocumentIntelligenceAdapter:
    """Build an adapter whose client returns `result`."""
    client = MagicMock()
    client.analyze_document = AsyncMock(return_value=result)
    client.close = MagicMock()
    return AzureDocumentIntelligenceAdapter(settings=settings, client=client)


@pytest.fixture
def mock_di_client(mock_analyze_result):
    """Create a mock DocumentIntelligenceClient."""
    client = MagicMock()
    client.analyze_document = AsyncMock(return_value=mock_analyze_result)
    client.close = MagicMock()
    return client


@pytest.fixture
def azure_adapter(
    mock_document_intelligence_settings, mock_di_client
) -> AzureDocumentIntelligenceAdapter:
    """Create an AzureDocumentIntelligenceAdapter with mock client."""
    return AzureDocumentIntelligenceAdapter(
        settings=mock_document_intelligence_settings,
        client=mock_di_client,
    )


class TestAzureDocumentIntelligenceAdapter:
    """Tests for AzureDocumentIntelligenceAdapter."""

    def test_get_supported_formats(self, azure_adapter):
        """Test getting supported formats."""
        formats = azure_adapter.get_supported_formats()

        assert isinstance(formats, list)
        assert len(formats) > 0
        assert "application/pdf" in formats
        assert "image/png" in formats
        assert "image/jpeg" in formats

    def test_is_format_supported_pdf(self, azure_adapter):
        """Test PDF format is supported."""
        assert azure_adapter.is_format_supported("application/pdf")

    def test_is_format_supported_images(self, azure_adapter):
        """Test image formats are supported."""
        assert azure_adapter.is_format_supported("image/png")
        assert azure_adapter.is_format_supported("image/jpeg")
        assert azure_adapter.is_format_supported("image/tiff")

    def test_is_format_supported_docx(self, azure_adapter):
        """Test DOCX format is supported."""
        assert azure_adapter.is_format_supported(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_is_format_not_supported(self, azure_adapter):
        """Test unsupported format returns False."""
        assert not azure_adapter.is_format_supported("application/unknown")
        assert not azure_adapter.is_format_supported("video/mp4")
        assert not azure_adapter.is_format_supported("text/plain")  # Not supported in Azure DI

    async def test_analyze_document_success(
        self, azure_adapter, mock_di_client, sample_file_id
    ):
        """Test successful document analysis."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
            file_version=1,
        )

        assert result.file_id == sample_file_id
        assert result.file_version == 1
        assert result.extracted_text is not None
        assert "Hello World" in result.extracted_text
        assert len(result.pages) >= 1
        assert result.extraction_metadata.extraction_method == "azure-document-intelligence"
        mock_di_client.analyze_document.assert_called_once()

    async def test_analyze_document_extracts_word_count(
        self, azure_adapter, sample_file_id
    ):
        """Test that word count is properly extracted."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # The mock has 2 words: "Hello" and "World"
        assert result.extraction_metadata.word_count == 2
        assert result.pages[0].word_count == 2
        assert result.extracted_text

    async def test_analyze_document_calculates_confidence(
        self, azure_adapter, sample_file_id
    ):
        """Test that confidence is calculated from word confidences."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Average of 0.95 and 0.98 = 0.965
        assert result.extraction_metadata.extraction_confidence > 0.9
        assert result.extraction_metadata.extraction_confidence < 1.0

    async def test_analyze_document_unsupported_format(
        self, azure_adapter, sample_file_id
    ):
        """Test unsupported format raises error."""
        content = b"some content"

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await azure_adapter.analyze_document(
                document_content=content,
                content_type="application/unknown",
                file_id=sample_file_id,
            )

        assert "application/unknown" in exc_info.value.content_type

    async def test_analyze_document_api_error(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test API error is properly handled."""
        from azure.core.exceptions import HttpResponseError

        mock_error = HttpResponseError(message="API error")
        mock_error.status_code = 400
        mock_error.error = MagicMock()
        mock_error.error.code = "InvalidRequest"

        mock_client = MagicMock()
        mock_client.analyze_document = AsyncMock(side_effect=mock_error)

        adapter = AzureDocumentIntelligenceAdapter(
            settings=mock_document_intelligence_settings,
            client=mock_client,
        )

        with pytest.raises(DocumentProcessingError) as exc_info:
            await adapter.analyze_document(
                document_content=b"content",
                content_type="application/pdf",
                file_id=sample_file_id,
            )

        assert sample_file_id == exc_info.value.file_id
        assert "Azure Document Intelligence failed" in exc_info.value.message

    async def test_analyze_document_with_file_version(
        self, azure_adapter, sample_file_id
    ):
        """Test file version is passed through."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
            file_version=5,
        )

        assert result.file_version == 5

    async def test_analyze_document_has_created_at(
        self, azure_adapter, sample_file_id
    ):
        """Test created_at timestamp is set."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)

    def test_close_calls_client_close(self, azure_adapter, mock_di_client):
        """Test that close calls the underlying client close."""
        azure_adapter.close()
        mock_di_client.close.assert_called_once()


class TestAzureDocumentIntelligenceAdapterMappingEdgeCases:
    """Tests for edge cases in result mapping."""

    async def test_empty_pages_with_content(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when pages is empty but content exists."""
        adapter = adapter_for(
            mock_document_intelligence_settings,
            analyze_result(content="# Title\n\nSome markdown content", pages=[]),
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Should create a single page from content
        assert len(result.pages) == 1
        assert result.extraction_metadata.page_count == 1
        assert result.extraction_metadata.word_count == 5  # "# Title Some markdown content"
        assert result.extracted_text == "# Title\n\nSome markdown content"

    async def test_pages_without_words(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when pages exist but have no words."""
        adapter = adapter_for(
            mock_document_intelligence_settings,
            analyze_result(content="Content", pages=[{"pageNumber": 1}]),
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        assert len(result.pages) == 1
        assert result.pages[0].word_count == 0

    async def test_no_confidence_in_words(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when words have no confidence scores."""
        adapter = adapter_for(
            mock_document_intelligence_settings,
            analyze_result(
                content="Word", pages=[{"pageNumber": 1, "words": [{"content": "Word"}]}]
            ),
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Should default to 0.0 confidence when not available
        assert result.extraction_metadata.extraction_confidence == 0.0


class TestStructuralPreservation:
    """The service's structural elements must survive the mapping.

    Each of these covers something that used to be dropped on the floor between the
    service response and text.json.
    """

    @pytest.fixture
    def output(self, mock_document_intelligence_settings, table_analyze_result, sample_file_id):
        """Map the fully-populated result once and assert against it."""
        adapter = adapter_for(mock_document_intelligence_settings, table_analyze_result)
        return adapter

    async def _analyze(self, adapter, sample_file_id):
        return await adapter.analyze_document(
            document_content=b"%PDF-1.4 fake pdf content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

    async def test_table_cells_are_preserved_with_positions(self, output, sample_file_id):
        """Every cell keeps its grid position, spans, kind, and geometry."""
        result = await self._analyze(output, sample_file_id)

        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.row_count == 3
        assert table.column_count == 2
        assert len(table.cells) == 5

        merged = table.cells[0]
        assert merged.content == "Budget Summary"
        assert merged.row_index == 0
        assert merged.column_index == 0
        assert merged.column_span == 2
        # The service omits a span of 1 rather than sending it; it must not become 0.
        assert merged.row_span == 1
        assert merged.kind == "columnHeader"
        assert merged.spans[0].offset == 2
        assert merged.spans[0].length == 14
        assert merged.bounding_regions[0].page_number == 1
        assert len(merged.bounding_regions[0].polygon) == 8

    async def test_table_can_be_reconstructed_without_the_markdown(
        self, output, sample_file_id
    ):
        """The cells alone rebuild the grid — `extracted_text` is not consulted."""
        result = await self._analyze(output, sample_file_id)
        table = result.tables[0]

        assert_cells_tile_grid(table)
        assert table.to_grid() == [
            ["Budget Summary", "Budget Summary"],
            ["Year", "Amount"],
            ["2026", "1,250"],
        ]

    async def test_table_spans_index_into_the_extracted_text(self, output, sample_file_id):
        """Spans are offsets into the markdown, so they must resolve against it."""
        result = await self._analyze(output, sample_file_id)
        table = result.tables[0]

        assert_spans_resolve(table, result.extracted_text)
        span = table.cells[0].spans[0]
        assert result.extracted_text[span.offset : span.offset + span.length] == "Budget Summary"

    async def test_table_caption_footnotes_and_pages(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)
        table = result.tables[0]

        assert table.caption == "Table 1. Budget by year"
        assert table.footnotes == ["Amounts in thousands."]
        assert table.page_numbers == [1]

    async def test_paragraph_roles_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert [p.role for p in result.paragraphs] == ["title", "pageFooter"]
        assert result.paragraphs[0].content == "Budget Summary"
        assert result.paragraphs[0].spans[0].offset == 2

    async def test_figures_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert len(result.figures) == 1
        figure = result.figures[0]
        assert figure.figure_id == "1.1"
        assert figure.caption == "Figure 1. Spend over time"
        assert figure.elements == ["/paragraphs/0"]
        assert figure.bounding_regions[0].page_number == 1

    async def test_sections_styles_and_key_value_pairs_are_preserved(
        self, output, sample_file_id
    ):
        result = await self._analyze(output, sample_file_id)

        assert result.sections[0].elements == ["/paragraphs/0", "/tables/0"]
        assert result.styles[0].is_handwritten is False
        assert result.styles[0].font_weight == "bold"
        assert result.key_value_pairs[0].key.content == "Fiscal year"
        assert result.key_value_pairs[0].value.content == "2026"
        assert result.key_value_pairs[0].confidence == 0.82

    async def test_page_geometry_lines_words_and_marks_are_preserved(
        self, output, sample_file_id
    ):
        result = await self._analyze(output, sample_file_id)
        page = result.pages[0]

        assert (page.width, page.height, page.unit) == (8.5, 11.0, "inch")
        assert page.angle == 0.3
        assert page.spans[0].length == len(TABLE_MARKDOWN)
        # Lines keep the line breaks that the space-joined `page.text` destroys.
        assert [line.content for line in page.lines] == [
            "| Budget Summary ||",
            "| Year | Amount |",
        ]
        assert len(page.lines[0].polygon) == 8
        assert [w.content for w in page.words] == ["Budget", "Summary"]
        assert page.words[0].span.offset == 2
        assert page.selection_marks[0].state == "selected"

    async def test_content_format_and_model_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert result.content_format == "markdown"
        assert result.model_id == "prebuilt-layout"

    async def test_metadata_counts_what_was_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert result.extraction_metadata.table_count == 1
        assert result.extraction_metadata.figure_count == 1
        assert result.extraction_metadata.paragraph_count == 2
        # The adapter does not persist anything; whoever writes the sidecar flips this.
        assert result.extraction_metadata.raw_analysis_stored is False

    async def test_raw_analysis_is_carried_verbatim(self, output, sample_file_id):
        """The raw copy is the escape hatch, so it must not be filtered by the model."""
        result = await self._analyze(output, sample_file_id)

        assert result.raw_analysis is not None
        assert result.raw_analysis["modelId"] == "prebuilt-layout"
        assert result.raw_analysis["tables"][0]["cells"][0]["columnSpan"] == 2

    async def test_raw_analysis_keeps_fields_the_model_does_not_declare(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """A field a newer service version adds still reaches the sidecar."""
        adapter = adapter_for(
            mock_document_intelligence_settings,
            analyze_result(content="x", pages=[], fieldFromTheFuture={"nested": [1, 2]}),
        )

        result = await self._analyze(adapter, sample_file_id)

        assert result.raw_analysis["fieldFromTheFuture"] == {"nested": [1, 2]}

    async def test_raw_analysis_is_not_serialised_into_text_json(
        self, output, sample_file_id
    ):
        """text.json carries the typed projection; analysis.json carries the raw copy."""
        result = await self._analyze(output, sample_file_id)

        assert "raw_analysis" not in result.model_dump(mode="json")

    async def test_absent_structure_maps_to_empty_collections(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """A document with no tables is empty, not broken."""
        adapter = adapter_for(
            mock_document_intelligence_settings,
            analyze_result(content="Plain text", pages=[]),
        )

        result = await self._analyze(adapter, sample_file_id)

        assert result.tables == []
        assert result.figures == []
        assert result.paragraphs == []
        assert result.key_value_pairs == []
        assert result.extraction_metadata.table_count == 0
