"""Assertions about reconstructing a table from its preserved cells.

The point of preserving structure is that a consumer can rebuild a table's grid without
re-reading the rendered markdown. These helpers state that as a check, so the offline
tests and the tests that hit the real service can hold the output to the same bar.
"""

from src.core.entities.document_analysis import ExtractedTable


def assert_cells_tile_grid(table: ExtractedTable) -> None:
    """Assert the table's cells cover its declared grid exactly once.

    Every position in ``row_count`` x ``column_count`` must be claimed by exactly one
    cell, counting the positions a merged cell spans. Overlap means the spans are wrong;
    a hole means a cell was lost.
    """
    claimed: dict[tuple[int, int], str] = {}

    for cell in table.cells:
        assert cell.row_index + cell.row_span <= table.row_count, (
            f"cell at ({cell.row_index},{cell.column_index}) spans past row_count "
            f"{table.row_count}"
        )
        assert cell.column_index + cell.column_span <= table.column_count, (
            f"cell at ({cell.row_index},{cell.column_index}) spans past column_count "
            f"{table.column_count}"
        )
        for row in range(cell.row_index, cell.row_index + cell.row_span):
            for col in range(cell.column_index, cell.column_index + cell.column_span):
                assert (row, col) not in claimed, (
                    f"position ({row},{col}) claimed by both '{claimed[(row, col)]}' "
                    f"and '{cell.content}'"
                )
                claimed[(row, col)] = cell.content

    missing = [
        (row, col)
        for row in range(table.row_count)
        for col in range(table.column_count)
        if (row, col) not in claimed
    ]
    assert not missing, f"grid positions covered by no cell: {missing}"


def assert_spans_resolve(table: ExtractedTable, extracted_text: str) -> None:
    """Assert every span on the table and its cells indexes inside the extracted text."""
    for span in table.spans:
        assert span.offset + span.length <= len(extracted_text), (
            f"table span {span.offset}+{span.length} runs past the extracted text "
            f"({len(extracted_text)} chars)"
        )
    for cell in table.cells:
        for span in cell.spans:
            assert span.offset + span.length <= len(extracted_text), (
                f"cell '{cell.content}' span {span.offset}+{span.length} runs past the "
                f"extracted text ({len(extracted_text)} chars)"
            )
