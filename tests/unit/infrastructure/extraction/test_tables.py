"""Unit tests for the shared table-rendering helpers.

The adapter tests hold each adapter to the contract; these hold the machinery underneath
to the cases no adapter's own document happens to contain — chiefly a form that cannot
express a table without a header line, which is where a definition of the prefix as
"opening markup plus header rows" quietly produces invalid fragments.
"""

import pytest

from src.core.entities.document_analysis import CellRole, TableCell
from src.infrastructure.extraction.tables import (
    header_rows_from_cells,
    partition_html_table,
    partition_pipe_table,
    row_continuations_from_cells,
)
from tests.support.extractor_contract import assert_is_a_valid_table

pytestmark = pytest.mark.unit


HTML = (
    "<table>\n"
    "<tr>\n<th>Year</th>\n<th>Amount</th>\n</tr>\n"
    "<tr>\n<td>2025</td>\n<td>980</td>\n</tr>\n"
    "<tr>\n<td>2026</td>\n<td>1,250</td>\n</tr>\n"
    "</table>"
)

PIPE = "| Year | Amount |\n| --- | --- |\n| 2025 | 980 |\n| 2026 | 1,250 |"


class TestHeaderRowsFromCells:
    def test_rows_carrying_a_header_cell_are_header_rows(self):
        cells = [
            TableCell(row_index=0, column_index=0, role=CellRole.COLUMN_HEADER),
            TableCell(row_index=1, column_index=0, role=CellRole.CONTENT),
        ]

        assert header_rows_from_cells(cells) == [0]

    def test_a_header_cell_spanning_rows_makes_all_of_them_header_rows(self):
        cells = [TableCell(row_index=0, column_index=0, row_span=2, role=CellRole.STUB_HEAD)]

        assert header_rows_from_cells(cells) == [0, 1]

    def test_a_header_that_is_not_the_first_row_is_reported_as_it_is(self):
        cells = [
            TableCell(row_index=0, column_index=0),
            TableCell(row_index=3, column_index=0, role=CellRole.ROW_HEADER),
        ]

        assert header_rows_from_cells(cells) == [3]

    def test_a_table_with_no_header_cells_has_no_header_rows(self):
        assert header_rows_from_cells([TableCell(row_index=0, column_index=0)]) == []

    def test_a_section_row_does_not_make_a_header(self):
        """It groups body rows; repeating it above a fragment would assert a grouping."""
        cells = [TableCell(row_index=2, column_index=0, role=CellRole.SECTION_ROW)]

        assert header_rows_from_cells(cells) == []


class TestRowContinuations:
    def test_a_merged_cell_ties_the_rows_below_it_to_its_first(self):
        cells = [TableCell(row_index=1, column_index=0, row_span=3)]

        assert row_continuations_from_cells(cells) == {2: 1, 3: 1}

    def test_an_unmerged_cell_ties_nothing(self):
        assert row_continuations_from_cells([TableCell(row_index=0, column_index=0)]) == {}

    def test_the_earliest_origin_wins(self):
        """A consumer keeping the group whole must reach the furthest row back."""
        cells = [
            TableCell(row_index=0, column_index=0, row_span=3),
            TableCell(row_index=1, column_index=1, row_span=2),
        ]

        assert row_continuations_from_cells(cells) == {1: 0, 2: 0}


class TestPartitioningHtml:
    def test_the_parts_are_exactly_the_whole(self):
        partition = partition_html_table(HTML, header_rows=[0], continuations={})

        assert partition.recomposes(HTML)

    def test_the_prefix_carries_the_leading_header_row(self):
        partition = partition_html_table(HTML, header_rows=[0], continuations={})

        assert partition.prefix_row_indices == [0]
        assert partition.prefix.startswith("<table>")
        assert "Year" in partition.prefix
        assert [row.row_index for row in partition.rows] == [1, 2]

    def test_the_suffix_is_the_closing_markup(self):
        partition = partition_html_table(HTML, header_rows=[0], continuations={})

        assert partition.suffix == "\n</table>"

    def test_a_table_with_no_header_keeps_every_row_as_a_body_row(self):
        partition = partition_html_table(HTML, header_rows=[], continuations={})

        assert partition.prefix == "<table>\n"
        assert partition.prefix_row_indices == []
        assert [row.row_index for row in partition.rows] == [0, 1, 2]
        assert partition.recomposes(HTML)

    def test_source_ranges_are_offset_into_the_document(self):
        partition = partition_html_table(
            HTML, header_rows=[0], continuations={}, source_offset=100
        )
        for row in partition.rows:
            start, end = row.source_range
            assert HTML[start - 100 : end - 100] == row.rendered

    def test_no_source_offset_means_no_recorded_range(self):
        """A range is recorded only when the adapter knows where the rendering sits."""
        partition = partition_html_table(HTML, header_rows=[], continuations={})

        assert all(row.source_range is None for row in partition.rows)

    def test_a_rendering_with_no_rows_becomes_all_prefix(self):
        """Reporting that honestly beats inventing a row that is not there."""
        partition = partition_html_table("<table>\n</table>", header_rows=[], continuations={})

        assert partition.rows == []
        assert partition.prefix == "<table>\n</table>"
        assert partition.recomposes("<table>\n</table>")


class TestPartitioningAPipeTableWithNoHeader:
    """A form that cannot express a table without a header line.

    This is the case the prefix is defined structurally to survive: the provider marked no
    cell as a header, but GFM still needs a header line and its delimiter, so the prefix
    carries the first row and every fragment repeats it.
    """

    @pytest.fixture
    def partition(self):
        return partition_pipe_table(PIPE, header_rows=[], continuations={})

    def test_the_prefix_carries_the_header_line_and_its_delimiter(self, partition):
        assert partition.prefix == "| Year | Amount |\n| --- | --- |\n"

    def test_the_prefix_is_never_empty_for_such_a_form(self, partition):
        assert partition.prefix

    def test_prefix_row_indices_names_the_row_being_repeated(self, partition):
        """Leaving it empty would report that nothing is repeated when something is."""
        assert partition.prefix_row_indices == [0]

    def test_the_remaining_rows_are_body_rows(self, partition):
        assert [row.row_index for row in partition.rows] == [1, 2]
        assert partition.rows[0].rendered == "| 2025 | 980 |\n"

    def test_the_parts_are_exactly_the_whole(self, partition):
        assert partition.recomposes(PIPE)

    def test_every_fragment_parses_as_a_table_in_that_form(self, partition):
        for rows in ([], partition.rows[:1], partition.rows[1:], partition.rows):
            fragment = partition.prefix + "".join(r.rendered for r in rows) + partition.suffix
            assert_is_a_valid_table(fragment)

    def test_the_delimiter_is_not_offered_as_a_row(self, partition):
        assert all("---" not in row.rendered for row in partition.rows)


class TestPartitioningAPipeTableWithAHeader:
    def test_a_marked_header_row_is_carried_the_same_way(self):
        partition = partition_pipe_table(PIPE, header_rows=[0], continuations={})

        assert partition.prefix_row_indices == [0]
        assert partition.recomposes(PIPE)

    def test_two_leading_header_rows_are_both_carried(self):
        rendered = "| Budget ||\n| --- | --- |\n| Year | Amount |\n| 2026 | 1,250 |"

        partition = partition_pipe_table(rendered, header_rows=[0, 1], continuations={})

        assert partition.prefix_row_indices == [0, 1]
        assert "Year | Amount" in partition.prefix
        assert [row.row_index for row in partition.rows] == [2]
        assert partition.recomposes(rendered)

    def test_a_late_header_row_is_not_hoisted_into_the_prefix(self):
        partition = partition_pipe_table(PIPE, header_rows=[2], continuations={})

        assert partition.prefix_row_indices == [0]
        assert [row.row_index for row in partition.rows] == [1, 2]
        assert partition.recomposes(PIPE)

    def test_a_dashes_row_that_is_not_the_second_line_stays_a_row(self):
        """Treating it as markup would drop a row the document actually has."""
        rendered = "| Year | Amount |\n| --- | --- |\n| - | - |\n| 2026 | 1,250 |"

        partition = partition_pipe_table(rendered, header_rows=[0], continuations={})

        assert [row.rendered for row in partition.rows] == ["| - | - |\n", "| 2026 | 1,250 |"]
        assert partition.recomposes(rendered)

    def test_continuations_are_carried_onto_the_rows(self):
        partition = partition_pipe_table(PIPE, header_rows=[0], continuations={2: 1})

        assert partition.rows[0].continues_from_row is None
        assert partition.rows[1].continues_from_row == 1
