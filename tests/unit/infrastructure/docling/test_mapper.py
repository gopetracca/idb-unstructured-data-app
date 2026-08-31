"""What the Docling mapper owes the canonical model, checked without a single model weight.

Every assertion here runs against a `DoclingDocument` built by hand, which is why the file
runs in milliseconds and needs no artifacts. The conversion itself — Docling's own job — is
covered by the marked test in `test_adapter.py`.
"""

import pytest

pytest.importorskip("docling", reason="the optional docling extra is not installed")

from src.core.entities.document_analysis import (
    BlockKind,
    CellRole,
    CoordinateOrigin,
    CoordinateUnit,
)
from src.infrastructure.docling.mapper import (
    ANALYSIS_FORMAT,
    EXTRACTION_METHOD,
    map_document,
)
from tests.support.docling_documents import (
    BODY,
    CAPTION,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    TITLE,
    build_sample_document,
    build_table_with_a_vertical_merge,
    build_table_with_overlapping_cells,
)
from tests.support.extractor_contract import (
    assert_satisfies_the_extraction_contract,
)
from tests.support.table_reconstruction import assert_cells_tile_grid

pytestmark = pytest.mark.unit


@pytest.fixture
def output():
    return map_document(build_sample_document(), file_id="doc-1", api_version="2.0.0")


class TestTheTextItRenders:
    """The mapper writes the markdown, so the text is the thing it is answerable for."""

    def test_every_element_appears_in_reading_order(self, output):
        text = output.extracted_text

        assert text.index(TITLE) < text.index(BODY) < text.index(CAPTION)
        assert text.index(CAPTION) < text.index("| Year")

    def test_a_title_is_rendered_as_a_heading(self, output):
        assert output.extracted_text.startswith(f"# {TITLE}")

    def test_a_picture_renders_as_a_placeholder_rather_than_being_dropped(self, output):
        """A figure with no text still occupies a position in the document."""
        assert "<!-- image -->" in output.extracted_text
        assert output.extraction_metadata.figure_count == 1


class TestTheOffsetInvariant:
    """The half of the port's contract this adapter has to produce rather than pass on."""

    def test_every_block_resolves_to_its_own_text(self, output):
        by_kind = {block.kind: block for block in output.blocks}

        assert by_kind[BlockKind.HEADING].text_in(output.extracted_text) == f"# {TITLE}"
        assert by_kind[BlockKind.PARAGRAPH].text_in(output.extracted_text) == BODY
        assert by_kind[BlockKind.CAPTION].text_in(output.extracted_text) == CAPTION

    def test_the_table_block_covers_exactly_the_table(self, output):
        block = next(b for b in output.blocks if b.kind is BlockKind.TABLE)
        table = output.tables[block.table_index]

        assert output.extracted_text[block.start : block.end] == table.rendered

    def test_the_caption_is_not_swallowed_into_the_table_rendering(self, output):
        """The document-aware renderer prepends it; a table that opened with prose would
        not survive fragment composition."""
        assert not output.tables[0].rendered.startswith(CAPTION)
        assert output.tables[0].caption == CAPTION

    def test_the_whole_output_satisfies_the_shared_contract(self, output):
        assert_satisfies_the_extraction_contract(output)


class TestTheTableGrid:
    def test_cell_roles_come_from_doclings_booleans(self, output):
        roles = {cell.content: cell.role for cell in output.tables[0].cells}

        assert roles["Budget Summary"] is CellRole.COLUMN_HEADER
        assert roles["Year"] is CellRole.COLUMN_HEADER
        assert roles["2025"] is CellRole.CONTENT

    def test_a_cell_that_is_both_a_row_and_column_header_is_the_stub_head(self):
        from docling_core.types.doc.document import TableCell as DoclingCell

        from src.infrastructure.docling.mapper import _cell_role

        corner = DoclingCell(
            text="",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            column_header=True,
            row_header=True,
        )

        assert _cell_role(corner) == "stub_head"

    def test_header_rows_are_derived_from_the_cells(self, output):
        assert output.tables[0].header_rows == [0, 1]

    def test_a_merged_cell_keeps_its_span(self, output):
        merged = next(c for c in output.tables[0].cells if c.content == "Budget Summary")

        assert (merged.row_span, merged.column_span) == (1, 2)

    def test_the_grid_reconstructs(self, output):
        assert_cells_tile_grid(output.tables[0])

    def test_a_vertical_merge_ties_the_rows_it_covers(self):
        table = map_document(build_table_with_a_vertical_merge(), file_id="doc-2").tables[0]

        tied = [row.continues_from_row for row in table.rows]

        assert 1 in tied, "the row a merged cell continues into does not say so"


class TestGeometry:
    def test_a_box_keeps_doclings_unit_and_origin_rather_than_being_converted(self, output):
        box = output.blocks[0].bounding_box

        assert box.unit is CoordinateUnit.POINT
        assert box.origin is CoordinateOrigin.BOTTOM_LEFT

    def test_top_and_bottom_are_ordered_within_that_origin(self, output):
        """Docling's `t` is the higher edge under a bottom-left origin, so it is the
        larger number — copying it into `top` would invert every box."""
        box = output.blocks[0].bounding_box

        assert box.top < box.bottom
        assert box.left < box.right

    def test_page_geometry_survives(self, output):
        page = output.pages[0]

        assert (page.width, page.height, page.unit) == (PAGE_WIDTH, PAGE_HEIGHT, "point")


class TestMetadata:
    def test_the_engine_names_itself(self, output):
        assert output.extraction_metadata.extraction_method == EXTRACTION_METHOD
        assert output.extraction_metadata.api_version == "2.0.0"

    def test_the_raw_analysis_declares_its_schema(self, output):
        assert output.extraction_metadata.analysis_format == ANALYSIS_FORMAT
        assert output.raw_analysis is not None
        assert output.raw_analysis["schema_name"] == "DoclingDocument"

    def test_the_raw_analysis_does_not_reach_the_stored_text_output(self, output):
        assert "raw_analysis" not in output.model_dump()

    def test_counts_report_what_was_actually_emitted(self, output):
        metadata = output.extraction_metadata

        assert metadata.table_count == len(output.tables) == 1
        assert metadata.paragraph_count == len(output.paragraphs)
        assert metadata.page_count == 1


class TestWhatDoclingCannotFill:
    """Empty, not approximated — the contract reads an empty list as "none reported"."""

    def test_no_character_spans_styles_or_key_values_are_invented(self, output):
        assert output.styles == []
        assert output.key_value_pairs == []
        assert output.sections == []

    def test_confidence_is_left_unset_rather_than_derived(self, output):
        assert output.extraction_metadata.extraction_confidence == 0.0


class TestRealTablesAreCopiedNotRepaired:
    """Docling's table model emits overlapping and sparse cells on complex real tables.

    Measured, not assumed: over the two IADB reports in `test-data/`, Docling reported 20
    overlapping grid positions and 362 declared positions covered by no cell, across 44
    tables. The offsets it gives agree with the spans it gives — this is the model's
    reading of the page, not a mapping error — so the adapter copies it. `to_grid()` is
    the only thing that has to cope, and it does so without inventing anything.

    This is a real difference from Document Intelligence, which guarantees a clean tiling.
    A consumer that needs one must check for it rather than assume it across engines.
    """

    @pytest.fixture
    def overlapping(self):
        return map_document(build_table_with_overlapping_cells(), file_id="overlap").tables[0]

    def test_both_overlapping_cells_survive(self, overlapping):
        at_position = [
            cell.content
            for cell in overlapping.cells
            if cell.row_index <= 1 < cell.row_index + cell.row_span
            and cell.column_index <= 2 < cell.column_index + cell.column_span
        ]

        assert sorted(at_position) == ["At approval", "Baseline"]

    def test_the_grid_resolves_rather_than_raising(self, overlapping):
        """Later cells win the contested position and uncovered ones stay None — a
        reconstruction that says "nothing here" where the model found nothing."""
        grid = overlapping.to_grid()

        assert grid[1][2] in {"At approval", "Baseline"}
        assert grid[0][1] is None
        assert len(grid) == 3 and all(len(row) == 3 for row in grid)

    def test_the_canonical_contract_still_holds(self):
        """What the port promises is unaffected: this is a table-quality property, not an
        offset, rendering or composition one."""
        output = map_document(build_table_with_overlapping_cells(), file_id="overlap")

        assert_satisfies_the_extraction_contract(output)
