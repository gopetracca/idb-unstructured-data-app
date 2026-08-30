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
from src.core.entities.document_analysis import (
    BlockKind,
    CellRole,
    CoordinateOrigin,
    CoordinateUnit,
    MarkdownOutput,
)
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from tests.support.document_intelligence_payloads import (
    DOCUMENT_MARKDOWN,
    FIGURE_HTML,
    SIMPLE_PAYLOAD,
    TABLE_HTML,
    TABLE_PAYLOAD,
    analyze_result,
)
from tests.support.extractor_contract import (
    assert_blocks_are_ordered_and_disjoint,
    assert_blocks_resolve,
    assert_every_row_subset_is_a_valid_table,
    assert_header_rows_match_the_cells,
    assert_prefix_rows_are_disjoint_from_body_rows,
    assert_rendering_is_exact,
    assert_rows_carry_their_provenance,
    assert_table_blocks_resolve_to_a_table,
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
        assert merged.role == CellRole.COLUMN_HEADER
        assert merged.spans[0].offset == DOCUMENT_MARKDOWN.index("Budget Summary")
        assert merged.spans[0].length == 14
        assert merged.bounding_regions[0].page_number == 1
        assert len(merged.bounding_regions[0].polygon) == 8
        # The service links a cell back to the paragraphs it came from.
        assert merged.elements == ["/paragraphs/2"]

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
        # The cell's span stops at its content: the `<th>` around it is outside, which is
        # exactly why a row cannot be cut at cell spans.
        assert "<th" not in result.extracted_text[span.offset : span.offset + span.length]

    async def test_table_caption_footnotes_and_pages(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)
        table = result.tables[0]

        assert table.caption == "Table 1. Budget by year"
        assert table.footnotes == ["Amounts in thousands."]
        assert table.page_numbers == [1]

    async def test_paragraph_roles_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert [p.role for p in result.paragraphs[:3]] == ["title", None, "pageFooter"]
        assert result.paragraphs[0].content == "Quarterly Report"
        assert result.paragraphs[0].spans[0].offset == 0

    async def test_figures_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert len(result.figures) == 1
        figure = result.figures[0]
        assert figure.figure_id == "1.1"
        assert figure.caption == "Figure 1. Spend over time"
        assert figure.elements == ["/paragraphs/8"]
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
        assert page.spans[0].length == len(DOCUMENT_MARKDOWN)
        # Lines keep the line breaks that the space-joined `page.text` destroys.
        assert [line.content for line in page.lines] == [
            "Quarterly Report",
            "Budget Summary",
        ]
        assert len(page.lines[0].polygon) == 8
        assert [w.content for w in page.words] == ["Budget", "Summary"]
        assert page.words[0].span.offset == DOCUMENT_MARKDOWN.index("Budget")
        assert page.selection_marks[0].state == "selected"

    async def test_content_format_and_model_are_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert result.content_format == "markdown"
        assert result.model_id == "prebuilt-layout"

    async def test_metadata_counts_what_was_preserved(self, output, sample_file_id):
        result = await self._analyze(output, sample_file_id)

        assert result.extraction_metadata.table_count == 1
        assert result.extraction_metadata.figure_count == 1
        assert result.extraction_metadata.paragraph_count == 9
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


# ---------------------------------------------------------------------------------------
# Table shapes the main fixture cannot show, each one a case where a plausible
# implementation gets the partition wrong.
# ---------------------------------------------------------------------------------------

# A merged cell spanning two rows, and a cell the service reports with no span at all
# because it is empty. Neither row has a derivable extent from its cells.
MERGED_TABLE_HTML = (
    "<table>\n"
    "<tr>\n<th>Region</th>\n<th>Amount</th>\n</tr>\n"
    '<tr>\n<td rowSpan="2">North</td>\n<td>10</td>\n</tr>\n'
    "<tr>\n<td></td>\n</tr>\n"
    "</table>"
)

# The service marked row 1 as the header. Row 0 is ordinary data that happens to come
# first — hoisting row 1 above it would reorder the document.
LATE_HEADER_TABLE_HTML = (
    "<table>\n"
    "<tr>\n<td>Draft</td>\n<td>2026-01-01</td>\n</tr>\n"
    "<tr>\n<th>Year</th>\n<th>Amount</th>\n</tr>\n"
    "<tr>\n<td>2026</td>\n<td>1,250</td>\n</tr>\n"
    "</table>"
)


def table_only_payload(rendered: str, cells: list[dict], row_count: int) -> dict:
    """A one-table document whose markdown is exactly that table's rendering."""
    return {
        "content": rendered,
        "contentFormat": "markdown",
        "pages": [{"pageNumber": 1}],
        "tables": [
            {
                "rowCount": row_count,
                "columnCount": 2,
                "cells": cells,
                "spans": [{"offset": 0, "length": len(rendered)}],
                "boundingRegions": [
                    {"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 3.0, 1.0, 3.0]}
                ],
            }
        ],
    }


MERGED_PAYLOAD = table_only_payload(
    MERGED_TABLE_HTML,
    [
        {"rowIndex": 0, "columnIndex": 0, "kind": "columnHeader", "content": "Region"},
        {"rowIndex": 0, "columnIndex": 1, "kind": "columnHeader", "content": "Amount"},
        {"rowIndex": 1, "columnIndex": 0, "rowSpan": 2, "content": "North"},
        {"rowIndex": 1, "columnIndex": 1, "content": "10"},
        # An empty cell: the service sends no span for it, so nothing about this row's
        # extent can be derived from its cells.
        {"rowIndex": 2, "columnIndex": 1, "content": ""},
    ],
    row_count=3,
)

LATE_HEADER_PAYLOAD = table_only_payload(
    LATE_HEADER_TABLE_HTML,
    [
        {"rowIndex": 0, "columnIndex": 0, "content": "Draft"},
        {"rowIndex": 0, "columnIndex": 1, "content": "2026-01-01"},
        {"rowIndex": 1, "columnIndex": 0, "kind": "columnHeader", "content": "Year"},
        {"rowIndex": 1, "columnIndex": 1, "kind": "columnHeader", "content": "Amount"},
        {"rowIndex": 2, "columnIndex": 0, "content": "2026"},
        {"rowIndex": 2, "columnIndex": 1, "content": "1,250"},
    ],
    row_count=3,
)


async def analyse(settings, payload: dict) -> MarkdownOutput:
    """Map a service-shaped payload through the adapter."""
    adapter = adapter_for(settings, analyze_result(**payload))
    return await adapter.analyze_document(
        document_content=b"%PDF-1.4",
        content_type="application/pdf",
        file_id="canonical-model-test",
    )


class TestCanonicalBlocks:
    """The block list is the contract's front door: everything else hangs off it."""

    @pytest.fixture
    async def output(self, mock_document_intelligence_settings):
        return await analyse(mock_document_intelligence_settings, TABLE_PAYLOAD)

    async def test_blocks_are_in_reading_order(self, output):
        """Span order is reading order — the service reports where it put each element."""
        assert [block.kind for block in output.blocks] == [
            BlockKind.HEADING,
            BlockKind.PARAGRAPH,
            BlockKind.TABLE,
            BlockKind.FIGURE,
            BlockKind.PARAGRAPH,
        ]
        assert [block.start for block in output.blocks] == sorted(
            block.start for block in output.blocks
        )

    async def test_every_block_resolves_against_the_extracted_text(self, output):
        """The offset invariant, stated as the text each block actually yields."""
        assert_blocks_resolve(output)
        text = output.extracted_text

        assert output.blocks[0].text_in(text) == "# Quarterly Report"
        assert output.blocks[2].text_in(text) == TABLE_HTML
        assert output.blocks[3].text_in(text) == FIGURE_HTML

    async def test_the_service_role_survives_the_narrowing_to_a_kind(self, output):
        """`title` and `sectionHeading` both become headings; the role says which."""
        assert output.blocks[0].role == "title"
        assert output.blocks[-1].kind is BlockKind.PARAGRAPH
        assert output.blocks[-1].role == "pageFooter"

    async def test_cell_paragraphs_are_not_repeated_as_blocks(self, output):
        """The service reports a paragraph per table cell; the block list must not.

        Emitting both would overlap the table's own range, and "the blocks in order" would
        describe two different documents.
        """
        assert_blocks_are_ordered_and_disjoint(output)
        assert len(output.paragraphs) == 9
        assert sum(1 for block in output.blocks if block.kind is BlockKind.PARAGRAPH) == 2

    async def test_a_table_block_names_its_table(self, output):
        """Without this a consumer sees a table and cannot reach the renderings."""
        table_block = next(b for b in output.blocks if b.kind is BlockKind.TABLE)

        assert table_block.table_index == 0
        assert output.tables[table_block.table_index].rendered == TABLE_HTML
        assert_table_blocks_resolve_to_a_table(output)

    async def test_blocks_carry_page_numbers_and_geometry(self, output):
        block = output.blocks[0]

        assert block.page_number == 1
        assert block.bounding_box is not None
        assert (block.bounding_box.left, block.bounding_box.top) == (1.0, 1.0)
        assert (block.bounding_box.right, block.bounding_box.bottom) == (7.5, 1.4)
        assert block.bounding_box.polygon == [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4]

    async def test_geometry_declares_its_unit_and_origin(self, output):
        """Document Intelligence reports inches from the top left; the box says so."""
        box = output.blocks[0].bounding_box

        assert box.unit is CoordinateUnit.INCH
        assert box.origin is CoordinateOrigin.TOP_LEFT

    async def test_provider_references_are_preserved_verbatim(self, output):
        """`/paragraphs/8` is opaque: kept exactly, interpreted by nobody."""
        figure_block = next(b for b in output.blocks if b.kind is BlockKind.FIGURE)

        assert figure_block.elements == ["/paragraphs/8"]
        assert output.tables[0].cells[0].elements == ["/paragraphs/2"]

    async def test_a_figure_that_encloses_a_table_does_not_overlap_it(
        self, mock_document_intelligence_settings
    ):
        """Two blocks over the same characters would make reading order ambiguous.

        The table wins, because it is the element a consumer can do something with.
        """
        table_html = "<table>\n<tr>\n<td>a</td>\n</tr>\n</table>"
        markdown = f"<figure>\n{table_html}\n</figure>"
        output = await analyse(
            mock_document_intelligence_settings,
            {
                "content": markdown,
                "pages": [{"pageNumber": 1}],
                "tables": [
                    {
                        "rowCount": 1,
                        "columnCount": 1,
                        "cells": [{"rowIndex": 0, "columnIndex": 0, "content": "a"}],
                        "spans": [{"offset": markdown.index(table_html), "length": len(table_html)}],
                    }
                ],
                "figures": [
                    {"id": "1.1", "spans": [{"offset": 0, "length": len(markdown)}]}
                ],
            },
        )

        assert [block.kind for block in output.blocks] == [BlockKind.TABLE]
        assert_blocks_are_ordered_and_disjoint(output)

    async def test_overlapping_paragraphs_cannot_reach_the_block_list(
        self, mock_document_intelligence_settings
    ):
        """The invariant holds for shapes the service is not expected to produce.

        Downstream code relies on walking the blocks and seeing each character once. A
        response that overlaps its own paragraphs must not turn that into a silent
        duplication.
        """
        markdown = "Alpha beta gamma"
        output = await analyse(
            mock_document_intelligence_settings,
            {
                "content": markdown,
                "pages": [{"pageNumber": 1}],
                "paragraphs": [
                    {"content": "Alpha beta", "spans": [{"offset": 0, "length": 10}]},
                    {"content": "beta gamma", "spans": [{"offset": 6, "length": 10}]},
                ],
            },
        )

        assert_blocks_are_ordered_and_disjoint(output)
        assert [block.text_in(output.extracted_text) for block in output.blocks] == ["Alpha beta"]

    async def test_output_written_before_blocks_existed_has_none(
        self, mock_document_intelligence_settings
    ):
        """Nothing invents structure for a response that reports none."""
        output = await analyse(
            mock_document_intelligence_settings,
            {"content": "Plain text", "pages": []},
        )

        assert output.blocks == []


class TestCanonicalTableRendering:
    """The adapter renders; nothing downstream parses."""

    @pytest.fixture
    async def table(self, mock_document_intelligence_settings):
        output = await analyse(mock_document_intelligence_settings, TABLE_PAYLOAD)
        return output.tables[0], output.extracted_text

    async def test_rendered_is_the_text_at_the_tables_span(self, table):
        extracted, text = table
        span = extracted.spans[0]

        assert extracted.rendered == text[span.offset : span.offset + span.length]
        assert extracted.rendered == TABLE_HTML

    async def test_header_rows_are_derived_from_cell_roles(self, table):
        extracted, _ = table

        assert extracted.header_rows == [0, 1]
        assert_header_rows_match_the_cells(extracted)

    async def test_the_prefix_carries_the_leading_header_rows(self, table):
        extracted, _ = table

        assert extracted.prefix_row_indices == [0, 1]
        assert extracted.render_prefix.startswith("<table>")
        assert "Budget Summary" in extracted.render_prefix
        assert "Amount" in extracted.render_prefix

    async def test_the_suffix_is_what_follows_the_last_row(self, table):
        extracted, _ = table

        assert extracted.render_suffix == "\n</table>"

    async def test_the_fragment_for_every_body_row_is_the_whole_table(self, table):
        """The exactness rule — byte for byte, not merely equivalent."""
        extracted, text = table

        assert extracted.fragment() == extracted.rendered
        assert_rendering_is_exact(extracted, text)

    async def test_rows_the_prefix_carries_are_not_body_rows(self, table):
        """Counting them twice would make the fragment longer than the table."""
        extracted, _ = table

        assert [row.row_index for row in extracted.rows] == [2]
        assert_prefix_rows_are_disjoint_from_body_rows(extracted)

    async def test_each_body_row_records_where_it_sits_in_the_text(self, table):
        extracted, text = table
        row = extracted.rows[0]

        assert row.source_range is not None
        start, end = row.source_range
        assert text[start:end] == row.rendered
        assert_rows_carry_their_provenance(extracted, text)

    async def test_a_row_is_more_than_its_cells_spans(self, table):
        """The reason rows exist: cell spans cover content, not the markup around it."""
        extracted, text = table
        cell_spans = [c.spans[0] for c in extracted.cells if c.row_index == 2 and c.spans]
        lowest = min(span.offset for span in cell_spans)
        highest = max(span.offset + span.length for span in cell_spans)

        assert text[lowest:highest] == "2026</td>\n<td>1,250"
        assert extracted.rows[0].rendered == "<tr>\n<td>2026</td>\n<td>1,250</td>\n</tr>"

    async def test_any_selection_of_rows_is_a_valid_table(self, table):
        extracted, _ = table

        assert_every_row_subset_is_a_valid_table(extracted)


class TestTablesTheMainFixtureCannotShow:
    """Shapes where a plausible partition is silently wrong."""

    @pytest.fixture
    async def merged(self, mock_document_intelligence_settings):
        return await analyse(mock_document_intelligence_settings, MERGED_PAYLOAD)

    @pytest.fixture
    async def late_header(self, mock_document_intelligence_settings):
        return await analyse(mock_document_intelligence_settings, LATE_HEADER_PAYLOAD)

    async def test_an_empty_cell_does_not_cost_its_row_a_rendering(self, merged):
        """The service sends no span for an empty cell, so the row has no cell extent."""
        table = merged.tables[0]
        empty = next(cell for cell in table.cells if cell.content == "")

        assert empty.spans == []
        assert table.rows[-1].rendered == "<tr>\n<td></td>\n</tr>"
        assert table.rows[-1].source_range is not None

    async def test_rows_still_partition_the_rendering(self, merged):
        table = merged.tables[0]

        assert table.fragment() == table.rendered
        assert [row.row_index for row in table.rows] == [1, 2]

    async def test_a_vertically_merged_cell_marks_the_rows_it_covers(self, merged):
        """Row 2's content is rendered in row 1; separating them would lose it."""
        table = merged.tables[0]

        assert table.rows[0].continues_from_row is None
        assert table.rows[1].continues_from_row == 1

    async def test_a_header_row_that_is_not_the_first_row(self, late_header):
        """`header_rows` reports what the service marked, not what convention expects."""
        table = late_header.tables[0]

        assert table.header_rows == [1]

    async def test_the_prefix_does_not_carry_a_late_header_row(self, late_header):
        """Hoisting it would reorder the document and break the exactness rule."""
        table = late_header.tables[0]

        assert table.prefix_row_indices == []
        assert table.render_prefix == "<table>\n"

    async def test_a_late_header_row_stays_a_body_row_in_document_order(self, late_header):
        table = late_header.tables[0]

        assert [row.row_index for row in table.rows] == [0, 1, 2]
        assert "Year" in table.rows[1].rendered

    async def test_the_exactness_rule_still_holds(self, late_header):
        table = late_header.tables[0]

        assert table.fragment() == table.rendered == LATE_HEADER_TABLE_HTML
        assert_every_row_subset_is_a_valid_table(table)


class TestEveryCanonicalFieldHasAProducer:
    """A field nothing sets is indistinguishable from one the provider does not supply.

    This walks the canonical types rather than listing their fields, so a field added
    later without a producer fails here instead of shipping empty.
    """

    @staticmethod
    def _is_populated(value) -> bool:
        """Whether an adapter actually set this. Zero counts; empty and absent do not."""
        if value is None:
            return False
        if isinstance(value, (str, list, dict, tuple)) and len(value) == 0:
            return False
        return True

    def _assert_all_fields_populated(self, instances, label: str) -> None:
        assert instances, f"no {label} to check"
        declared = set(type(instances[0]).model_fields)
        populated = {
            name
            for instance in instances
            for name in declared
            if self._is_populated(getattr(instance, name))
        }

        assert declared == populated, f"{label} fields nothing populates: {declared - populated}"

    @pytest.fixture
    async def outputs(self, mock_document_intelligence_settings):
        return [
            await analyse(mock_document_intelligence_settings, payload)
            for payload in (TABLE_PAYLOAD, MERGED_PAYLOAD, LATE_HEADER_PAYLOAD)
        ]

    async def test_every_content_block_field_is_populated(self, outputs):
        self._assert_all_fields_populated(
            [block for output in outputs for block in output.blocks], "ContentBlock"
        )

    async def test_every_bounding_box_field_is_populated(self, outputs):
        self._assert_all_fields_populated(
            [
                block.bounding_box
                for output in outputs
                for block in output.blocks
                if block.bounding_box
            ],
            "BoundingBox",
        )

    async def test_every_table_row_field_is_populated(self, outputs):
        self._assert_all_fields_populated(
            [row for output in outputs for table in output.tables for row in table.rows],
            "TableRow",
        )

    async def test_every_table_field_is_populated(self, outputs):
        self._assert_all_fields_populated(
            [table for output in outputs for table in output.tables], "ExtractedTable"
        )

    async def test_every_table_cell_field_is_populated(self, outputs):
        self._assert_all_fields_populated(
            [cell for output in outputs for table in output.tables for cell in table.cells],
            "TableCell",
        )
