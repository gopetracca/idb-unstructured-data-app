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
from src.core.entities.document_analysis import (
    BlockKind,
    CellRole,
    CoordinateOrigin,
    CoordinateUnit,
    MarkdownOutput,
)
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from tests.support.extractor_contract import (
    assert_blocks_are_ordered_and_disjoint,
    assert_blocks_resolve,
    assert_row_selections_compose_into_a_valid_table,
    assert_header_rows_match_the_cells,
    assert_prefix_rows_are_disjoint_from_body_rows,
    assert_rendering_is_exact,
    assert_roles_are_canonical,
    assert_rows_carry_their_provenance,
    assert_satisfies_the_extraction_contract,
    assert_table_blocks_resolve_to_a_table,
)
from tests.support.sample_documents import (
    BODY,
    HEADING,
    TABLE_ROWS,
    build_sample_image,
    build_sample_pdf,
)
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


class TestLiveOutputSatisfiesTheCanonicalContract:
    """The offline fixtures assert this shape; here the real service has to produce it.

    Everything the adapter derives — the block list, the header rows, the partitioned
    rendering — is derived from a real response rather than one we wrote, which is the only
    way to find out that the service renders tables as HTML and puts markup between the
    cell spans.
    """

    def test_the_whole_contract_holds_against_the_real_service(
        self, live_output: MarkdownOutput
    ):
        """The same assertions every adapter is held to, run on real output."""
        assert_satisfies_the_extraction_contract(live_output)

    def test_the_service_produced_blocks_at_all(self, live_output: MarkdownOutput):
        assert live_output.blocks, "the real response yielded no blocks"
        kinds = {block.kind for block in live_output.blocks}
        assert BlockKind.TABLE in kinds
        assert BlockKind.HEADING in kinds

    def test_every_block_resolves_against_the_real_markdown(self, live_output: MarkdownOutput):
        """The offset invariant, against text nobody here wrote."""
        assert_blocks_resolve(live_output)
        text = live_output.extracted_text

        heading = next(b for b in live_output.blocks if b.kind is BlockKind.HEADING)
        assert HEADING in heading.text_in(text)
        for block in live_output.blocks:
            assert block.text_in(text).strip(), f"{block.kind} block resolved to nothing"

    def test_blocks_are_in_reading_order_and_do_not_overlap(self, live_output: MarkdownOutput):
        """The service reports a paragraph per table cell; the block list must not."""
        assert_blocks_are_ordered_and_disjoint(live_output)
        assert len(live_output.paragraphs) > len(live_output.blocks)

    def test_the_table_block_reaches_the_table(self, live_output: MarkdownOutput):
        assert_table_blocks_resolve_to_a_table(live_output)
        block = next(b for b in live_output.blocks if b.kind is BlockKind.TABLE)
        assert block.table_index == 0

    def test_block_geometry_declares_its_unit_and_origin(self, live_output: MarkdownOutput):
        boxes = [b.bounding_box for b in live_output.blocks if b.bounding_box]

        assert boxes, "the service located every element but no box was mapped"
        for box in boxes:
            assert box.unit.value == "inch"
            assert box.origin.value == "top_left"
            assert box.left <= box.right and box.top <= box.bottom
            assert len(box.polygon) == 8

    def test_cell_roles_are_canonical(self, live_output: MarkdownOutput):
        table = live_output.tables[0]

        assert_roles_are_canonical(table)
        assert CellRole.COLUMN_HEADER in {cell.role for cell in table.cells}

    def test_header_rows_are_derived_from_the_cells(self, live_output: MarkdownOutput):
        """The sample's first two rows are headers: a merged title over a column header row."""
        table = live_output.tables[0]

        assert_header_rows_match_the_cells(table)
        assert table.header_rows == [0, 1]

    def test_rendered_is_the_text_at_the_tables_span(self, live_output: MarkdownOutput):
        table = live_output.tables[0]
        span = table.spans[0]

        assert table.rendered
        assert table.rendered == live_output.extracted_text[
            span.offset : span.offset + span.length
        ]

    def test_the_fragment_for_every_body_row_is_the_whole_table(
        self, live_output: MarkdownOutput
    ):
        """The exactness rule, on a rendering the service produced."""
        table = live_output.tables[0]

        assert table.fragment() == table.rendered
        assert_rendering_is_exact(table, live_output.extracted_text)

    def test_rows_record_where_they_sit_in_the_markdown(self, live_output: MarkdownOutput):
        table = live_output.tables[0]

        assert table.rows, "the rendering was not partitioned into rows"
        assert_rows_carry_their_provenance(table, live_output.extracted_text)
        assert_prefix_rows_are_disjoint_from_body_rows(table)

    def test_a_row_is_more_than_the_extent_of_its_cell_spans(
        self, live_output: MarkdownOutput
    ):
        """The concrete reason rows exist, checked against the real response.

        Cell spans cover cell content and stop before the markup, so the min-to-max range
        over a row's cells is not that row's rendering. Cutting there yields text that is
        not a table.
        """
        table = live_output.tables[0]
        body = table.rows[0]
        cells = [c for c in table.cells if c.row_index == body.row_index and c.spans]
        assert cells, "no cell in the first body row carried a span"

        lowest = min(span.offset for cell in cells for span in cell.spans)
        highest = max(span.offset + span.length for cell in cells for span in cell.spans)
        from_cell_spans = live_output.extracted_text[lowest:highest]

        assert from_cell_spans != body.rendered
        assert from_cell_spans in body.rendered

    def test_every_selection_of_rows_composes_into_a_valid_table(
        self, live_output: MarkdownOutput
    ):
        assert_row_selections_compose_into_a_valid_table(live_output.tables[0])

    def test_the_stored_output_keeps_all_of_it(self, live_output: MarkdownOutput):
        """text.json is what downstream reads, so the guarantees have to survive it."""
        restored = MarkdownOutput.model_validate(
            json.loads(json.dumps(live_output.model_dump(mode="json")))
        )

        assert_satisfies_the_extraction_contract(restored)
        assert len(restored.blocks) == len(live_output.blocks)


@pytest.fixture(scope="module")
def sample_image() -> bytes:
    return build_sample_image()


@pytest.fixture(scope="module")
def live_image_output(sample_image: bytes) -> MarkdownOutput:
    """Analyse the same document as a PNG. Module-scoped: it bills one more analysis.

    Worth the second call because the unit a page is measured in is not visible in the
    coordinates — inches and pixels are both small positive floats — so an adapter
    labelling one as the other can only be caught by analysing both.
    """
    settings = get_settings().document_intelligence
    adapter = AzureDocumentIntelligenceAdapter(settings=settings)
    try:
        return asyncio.run(
            adapter.analyze_document(
                document_content=sample_image,
                content_type="image/png",
                file_id="live-extraction-image-test",
                file_version=1,
            )
        )
    finally:
        adapter.close()


class TestLiveImageGeometryIsNotReportedInInches:
    """An image page is measured in pixels; a PDF page in inches.

    The adapter used to label every polygon `inch`. On a PDF that is right and on a PNG it
    is wrong by three orders of magnitude, while the numbers themselves look equally
    plausible — which is the whole reason the canonical box carries its unit.
    """

    def test_the_service_reports_the_page_in_pixels(self, live_image_output: MarkdownOutput):
        page = live_image_output.pages[0]

        assert page.unit == "pixel"
        assert page.width and page.width > 100

    def test_every_block_box_says_pixel(self, live_image_output: MarkdownOutput):
        boxes = [b.bounding_box for b in live_image_output.blocks if b.bounding_box]

        assert boxes, "the image yielded no geometry at all"
        for box in boxes:
            assert box.unit is CoordinateUnit.PIXEL
            assert box.origin is CoordinateOrigin.TOP_LEFT

    def test_the_coordinates_are_pixels_and_could_not_be_inches(
        self, live_image_output: MarkdownOutput
    ):
        """The decisive check: as inches these would describe a page yards across."""
        page = live_image_output.pages[0]
        widest = max(
            b.bounding_box.right for b in live_image_output.blocks if b.bounding_box
        )

        assert widest > 100, "a coordinate this small would be indistinguishable from inches"
        assert widest <= page.width

    def test_the_same_document_as_a_pdf_reports_inches(
        self, live_image_output: MarkdownOutput, live_output: MarkdownOutput
    ):
        """The two together are the assertion; either alone would have passed the bug."""
        pdf_units = {b.bounding_box.unit for b in live_output.blocks if b.bounding_box}
        image_units = {b.bounding_box.unit for b in live_image_output.blocks if b.bounding_box}

        assert pdf_units == {CoordinateUnit.INCH}
        assert image_units == {CoordinateUnit.PIXEL}

    def test_the_contract_holds_for_the_image_too(self, live_image_output: MarkdownOutput):
        """Everything else the contract asks for, on a scanned document rather than a PDF."""
        assert live_image_output.blocks
        assert_satisfies_the_extraction_contract(live_image_output)

    def test_a_table_the_service_marked_with_no_header_still_partitions(
        self, live_image_output: MarkdownOutput
    ):
        """The image's table comes back as `<td>` throughout, so it has no header rows.

        The prefix then carries nothing and every row is a body row — and the exactness
        rule still has to hold, which is the case a prefix defined as "markup plus header
        rows" would get wrong.
        """
        assert live_image_output.tables, "the service found no table in the image"
        table = live_image_output.tables[0]

        assert table.rows
        assert table.fragment() == table.rendered
        if not table.header_rows:
            assert table.prefix_row_indices == []
            assert [row.row_index for row in table.rows] == list(range(len(table.rows)))


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
