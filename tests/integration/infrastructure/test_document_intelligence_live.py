"""Live tests for the Document Intelligence extractor against the real Azure service.

These are the tests that prove the offline fixtures are not lying about the shape of a
real response. They analyse a PDF built on the fly — a table with a merged title cell over
a header row, a heading, and body text — and assert that everything the service found
survives the mapping, and that the table rebuilds from its cells alone.

They require:
1. An Azure Document Intelligence resource with the `prebuilt-layout` model
2. Environment variables:
   - DOCUMENT_INTELLIGENCE_ENDPOINT
   - DOCUMENT_INTELLIGENCE_API_KEY   (omit when using managed identity)
   - DOCUMENT_INTELLIGENCE_RUN_TESTS=on
3. Willingness to pay for one analysis per test (the sample PDF is a single page)

Run with:
    DOCUMENT_INTELLIGENCE_RUN_TESTS=on \
      uv run pytest -m requires_azure_di tests/integration/infrastructure/test_document_intelligence_live.py

Without that configuration the whole module is skipped by the marker handling in
tests/conftest.py, so it is safe to leave in a normal test run and in CI.
"""

import asyncio
import json

import pytest

from src.config.settings import get_settings
from src.core.entities.document_analysis import MarkdownOutput
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from tests.support.sample_documents import BODY, HEADING, TABLE_ROWS, build_sample_pdf
from tests.support.table_reconstruction import assert_cells_tile_grid, assert_spans_resolve

pytestmark = [pytest.mark.integration, pytest.mark.requires_azure_di]


@pytest.fixture(scope="module")
def sample_pdf() -> bytes:
    return build_sample_pdf()


@pytest.fixture(scope="module")
def live_output(sample_pdf: bytes) -> MarkdownOutput:
    """Analyse the sample PDF once and share the result across the module.

    Module-scoped on purpose: every test here would otherwise bill another analysis.
    """
    settings = get_settings().document_intelligence
    adapter = AzureDocumentIntelligenceAdapter(settings=settings)
    try:
        return asyncio.run(
            adapter.analyze_document(
                document_content=sample_pdf,
                content_type="application/pdf",
                file_id="live-extraction-test",
                file_version=1,
            )
        )
    finally:
        adapter.close()


class TestLiveExtractionPreservesStructure:
    """What the real service returns must survive the mapping."""

    def test_markdown_and_pages_are_extracted(self, live_output: MarkdownOutput):
        assert live_output.extracted_text
        assert HEADING in live_output.extracted_text
        assert BODY.split(".")[0] in live_output.extracted_text
        assert live_output.extraction_metadata.page_count == 1
        assert live_output.extraction_metadata.word_count > 0

    def test_the_table_is_found_and_structured(self, live_output: MarkdownOutput):
        assert live_output.tables, "the service returned no tables for a document with one"
        table = live_output.tables[0]

        assert table.row_count == len(TABLE_ROWS)
        assert table.column_count == 2
        assert table.cells

    def test_the_table_reconstructs_from_its_cells_alone(self, live_output: MarkdownOutput):
        """The acceptance bar: rebuild the grid without reading the markdown."""
        table = live_output.tables[0]

        assert_cells_tile_grid(table)
        grid = table.to_grid()

        # The merged title spans both columns, so it appears in both positions.
        assert grid[0][0] == grid[0][1] == "Budget Summary"
        assert grid[1] == ["Year", "Amount"]
        assert grid[2] == ["2025", "980"]
        assert grid[3] == ["2026", "1250"]

    def test_the_merged_cell_keeps_its_span(self, live_output: MarkdownOutput):
        """A rendered markdown table cannot express this; the cell model must."""
        table = live_output.tables[0]
        merged = next(c for c in table.cells if c.content.strip() == "Budget Summary")

        assert merged.column_span == 2
        assert merged.row_index == 0
        assert merged.column_index == 0

    def test_cells_carry_geometry_and_page_numbers(self, live_output: MarkdownOutput):
        table = live_output.tables[0]

        assert table.page_numbers == [1]
        for cell in table.cells:
            assert cell.bounding_regions, f"cell '{cell.content}' lost its bounding region"
            assert cell.bounding_regions[0].page_number == 1
            assert len(cell.bounding_regions[0].polygon) == 8

    def test_spans_resolve_against_the_extracted_markdown(self, live_output: MarkdownOutput):
        assert_spans_resolve(live_output.tables[0], live_output.extracted_text)

        for cell in live_output.tables[0].cells:
            if not cell.spans or not cell.content.strip():
                continue
            span = cell.spans[0]
            excerpt = live_output.extracted_text[span.offset : span.offset + span.length]
            assert cell.content.strip() in excerpt or excerpt.strip() in cell.content

    def test_paragraphs_carry_roles(self, live_output: MarkdownOutput):
        assert live_output.paragraphs
        roles = {p.role for p in live_output.paragraphs if p.role}
        assert roles, "the service assigned no paragraph roles at all"
        assert any(HEADING in p.content for p in live_output.paragraphs)

    def test_page_geometry_and_lines_are_preserved(self, live_output: MarkdownOutput):
        page = live_output.pages[0]

        assert page.unit
        assert page.width and page.height
        assert page.lines, "per-page lines were dropped"
        assert page.words, "per-page words were dropped"
        # Lines keep the layout that the space-joined page text destroys.
        assert any(HEADING in line.content for line in page.lines)

    def test_metadata_counts_what_was_preserved(self, live_output: MarkdownOutput):
        metadata = live_output.extraction_metadata

        assert metadata.table_count == len(live_output.tables)
        assert metadata.paragraph_count == len(live_output.paragraphs)
        assert metadata.extraction_method == "azure-document-intelligence"


class TestLiveRawAnalysisIsLossless:
    """The sidecar copy has to be a superset of the typed projection."""

    def test_raw_analysis_is_captured(self, live_output: MarkdownOutput):
        assert live_output.raw_analysis is not None
        assert live_output.raw_analysis["modelId"]
        assert live_output.raw_analysis["content"] == live_output.extracted_text

    def test_raw_analysis_is_json_serialisable(self, live_output: MarkdownOutput):
        """It is written to a blob as JSON, so it has to survive the round trip."""
        encoded = json.dumps(live_output.raw_analysis, default=str)

        assert json.loads(encoded)["tables"][0]["rowCount"] == len(TABLE_ROWS)

    def test_raw_analysis_keeps_detail_the_typed_model_summarises(
        self, live_output: MarkdownOutput
    ):
        """Anything the domain model does not declare still has to be recoverable."""
        raw_table = live_output.raw_analysis["tables"][0]

        assert len(raw_table["cells"]) == len(live_output.tables[0].cells)
        # elements/references the typed model does not model at cell level
        assert set(raw_table.keys()) >= {"rowCount", "columnCount", "cells", "boundingRegions"}

    def test_raw_analysis_stays_out_of_the_typed_output(self, live_output: MarkdownOutput):
        assert "raw_analysis" not in live_output.model_dump(mode="json")


class TestLiveOutputIsSerialisable:
    """Whatever the service returns must be storable as text.json."""

    def test_output_round_trips_through_json(self, live_output: MarkdownOutput):
        encoded = json.dumps(live_output.model_dump(mode="json"))
        restored = MarkdownOutput.model_validate(json.loads(encoded))

        assert restored.extracted_text == live_output.extracted_text
        assert restored.tables[0].to_grid() == live_output.tables[0].to_grid()
        assert len(restored.pages[0].lines) == len(live_output.pages[0].lines)
