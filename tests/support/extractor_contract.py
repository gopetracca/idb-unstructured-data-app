"""The bar every extraction adapter has to clear, written once.

These assertions are the executable form of the canonical contract: they say what must be
true of any adapter's output without naming a service, a markup, or a field the provider
happens to supply. They are used by the adapter tests and by the parameterised contract
test, so a second adapter inherits the same bar rather than a looser one.
"""

import re
from itertools import combinations

from src.core.entities.document_analysis import (
    HEADER_CELL_ROLES,
    BlockKind,
    CellRole,
    ExtractedTable,
    MarkdownOutput,
)

# A GitHub-flavoured Markdown delimiter line, the thing that makes the lines around it a
# table. Duplicated from the adapter side deliberately: a test that imports the code's own
# notion of validity cannot catch the code being wrong about it.
_PIPE_DELIMITER = re.compile(r"^[\s|:-]*-[\s|:-]*$")


def assert_blocks_resolve(output: MarkdownOutput) -> None:
    """Every block's range indexes into the extracted text — the offset invariant."""
    length = len(output.extracted_text)
    for block in output.blocks:
        assert 0 <= block.start <= block.end <= length, (
            f"{block.kind} block {block.start}..{block.end} does not fit the extracted "
            f"text ({length} chars)"
        )


def assert_blocks_are_ordered_and_disjoint(output: MarkdownOutput) -> None:
    """Blocks are in reading order and no two describe the same characters.

    Overlap would mean "the blocks in order" describes two different documents — the case
    that arises when a service reports a paragraph for each table cell and the adapter
    emits both the table and its cells.
    """
    previous_end = 0
    for block in output.blocks:
        assert block.start >= previous_end, (
            f"{block.kind} block at {block.start} starts before the previous block ended "
            f"({previous_end})"
        )
        previous_end = block.end


def assert_table_blocks_resolve_to_a_table(output: MarkdownOutput) -> None:
    """A table block names its table and covers exactly that table's rendering."""
    for block in output.blocks:
        if block.kind is not BlockKind.TABLE:
            continue
        assert block.table_index is not None, "a table block that names no table"
        assert 0 <= block.table_index < len(output.tables)
        table = output.tables[block.table_index]
        assert output.extracted_text[block.start : block.end] == table.rendered


def assert_roles_are_canonical(table: ExtractedTable) -> None:
    """No provider spelling survived into the stored cells."""
    for cell in table.cells:
        assert isinstance(cell.role, CellRole), f"cell '{cell.content}' kept a raw role"


def assert_header_rows_match_the_cells(table: ExtractedTable) -> None:
    """Header rows are derived from the cells, not assumed to be the leading ones."""
    expected: set[int] = set()
    for cell in table.cells:
        if cell.role in HEADER_CELL_ROLES:
            expected.update(range(cell.row_index, cell.row_index + cell.row_span))
    assert set(table.header_rows) == expected
    assert table.header_rows == sorted(table.header_rows)


def assert_rendering_is_exact(table: ExtractedTable, extracted_text: str) -> None:
    """`rendered` is the table's text, and the parts really are the whole.

    This is the exactness rule: the fragment composed from every body row equals the
    rendering byte for byte. It is cheap and decisive — a partition done wrong cannot pass
    it — and every other guarantee here rests on the parts being the whole.
    """
    if table.spans:
        span = table.spans[0]
        assert table.rendered == extracted_text[span.offset : span.offset + span.length]
    assert table.fragment() == table.rendered


def assert_rows_carry_their_provenance(table: ExtractedTable, extracted_text: str) -> None:
    """A row that records a range records the right one."""
    for row in table.rows:
        if row.source_range is None:
            continue
        start, end = row.source_range
        assert extracted_text[start:end] == row.rendered, (
            f"row {row.row_index} claims {start}..{end} but that is not its rendering"
        )


def assert_prefix_rows_are_disjoint_from_body_rows(table: ExtractedTable) -> None:
    """A row is either carried by the prefix or a body row — never counted twice."""
    body = [row.row_index for row in table.rows]
    assert not set(table.prefix_row_indices) & set(body), (
        "a row is both repeated by every fragment and offered as a body row"
    )
    assert body == sorted(body), "body rows are not in document order"


# Above this many body rows, checking every subset stops being a test and becomes a hang:
# the count is 2**n, so a 30-row table — entirely ordinary in a real document — is a
# billion fragments. Ten rows is 1024, which is free.
_EXHAUSTIVE_ROW_LIMIT = 10


def assert_row_selections_compose_into_a_valid_table(table: ExtractedTable) -> None:
    """Selections of body rows compose into a table in the extractor's own form.

    Exhaustively for a small table, and over a representative sample for a large one. The
    sample is not a weakening: the property under test belongs to the *partition* — a
    prefix that is exactly the rendering before the first body row, and a suffix exactly
    the rendering after the last — and a partition that composes wrongly does so for a
    single row as readily as for the 2**n-th subset. What the sample keeps is every case
    where a boundary could be got wrong: nothing, each row alone, each adjacent pair, the
    leading and trailing runs, a gap in the middle, and everything.
    """
    for selection in _row_selections(table):
        assert_is_a_valid_table(table.fragment(list(selection)))


def _row_selections(table: ExtractedTable) -> list[tuple]:
    """The selections to check: every subset while that is cheap, a sample when it is not."""
    rows = table.rows
    if len(rows) <= _EXHAUSTIVE_ROW_LIMIT:
        return [
            selection
            for size in range(len(rows) + 1)
            for selection in combinations(rows, size)
        ]

    selections: list[tuple] = [(), tuple(rows)]
    selections.extend((row,) for row in rows)
    selections.extend((rows[i], rows[i + 1]) for i in range(len(rows) - 1))
    selections.append(tuple(rows[:3]))
    selections.append(tuple(rows[-3:]))
    # A gap: the parts either side of a hole must still compose, which is the case a
    # consumer emitting "the rows that matched" actually produces.
    selections.append((rows[0], rows[-1]))
    selections.append(tuple(rows[: len(rows) // 2]) + tuple(rows[len(rows) // 2 + 1 :]))
    return selections


def assert_is_a_valid_table(fragment: str) -> None:
    """Whether a string is a table, in whichever of the two forms it is written in.

    The point of the contract is that a consumer never asks this question; the point of
    asserting it here is that the adapter's answer has to be true for every fragment, not
    only the whole.
    """
    text = fragment.strip()
    assert text, "an empty string is not a table"

    if text.startswith("<table"):
        assert text.endswith("</table>"), "an HTML table fragment that is not closed"
        assert text.count("<tr") == len(re.findall(r"</tr\s*>", text)), "unbalanced rows"
        return

    lines = [line for line in text.split("\n") if line.strip()]
    assert all("|" in line for line in lines), f"not a pipe table: {text!r}"
    assert len(lines) >= 2, "a pipe table needs a header line and its delimiter"
    assert _PIPE_DELIMITER.match(lines[1].strip()), (
        f"a pipe table without its delimiter line is four lines with pipes in them: {text!r}"
    )


def assert_satisfies_the_extraction_contract(output: MarkdownOutput) -> None:
    """Everything above, applied to one adapter's output."""
    assert_blocks_resolve(output)
    assert_blocks_are_ordered_and_disjoint(output)
    assert_table_blocks_resolve_to_a_table(output)
    for table in output.tables:
        assert_roles_are_canonical(table)
        assert_header_rows_match_the_cells(table)
        assert_rendering_is_exact(table, output.extracted_text)
        assert_rows_carry_their_provenance(table, output.extracted_text)
        assert_prefix_rows_are_disjoint_from_body_rows(table)
        assert_row_selections_compose_into_a_valid_table(table)
