"""Turning a provider's table into the canonical one.

Three jobs live here, all of them things an adapter owes the canonical model and none of
them things a consumer should ever do:

- **Header rows from cell roles** — which rows the provider marked as its header, rather
  than assuming the leading one.
- **Vertical continuations** — which rows a merged cell makes inseparable from the row
  above, because that cell's content is rendered once, in the first of them.
- **Partitioning the rendering** — splitting the table's text into exactly the part
  before the first body row, the body rows, and the part after the last, so a consumer
  composing a fragment gets a valid table without knowing the markup.

The partitioners split a string the adapter already has. They never reassemble one from
cell spans: those cover cell *content* and exclude the markup around it, are absent for an
empty cell, and can be discontiguous within one cell — so a range derived from them is not
a rendered row. Because the partition is a split, the concatenation of every part is the
original by construction, which is what makes the exactness rule hold.
"""

import re
from dataclasses import dataclass, field

from src.core.entities.document_analysis import (
    HEADER_CELL_ROLES,
    TableCell,
    TableRow,
)

# One `<tr …>` opening tag; Document Intelligence emits no attributes on it today, but a
# provider that does must not change where the row starts.
_HTML_ROW = re.compile(r"<tr\b[^>]*>.*?</tr\s*>", re.DOTALL | re.IGNORECASE)

# A GitHub-flavoured Markdown delimiter line: only pipes, dashes, colons and spaces, with
# at least one dash. It is what makes the lines above and below it a table rather than
# text with pipes in it, which is why it belongs in the prefix and is not a row.
_PIPE_DELIMITER = re.compile(r"^[\s|:-]*-[\s|:-]*$")


@dataclass(frozen=True)
class RenderedRow:
    """One row of a rendering, and where it sits inside it."""

    row_index: int
    start: int
    end: int


@dataclass
class RenderPartition:
    """A table's rendering split into a prefix, its body rows, and a suffix.

    ``prefix + "".join(row.rendered for row in rows) + suffix`` is the rendering it was
    built from, exactly.
    """

    prefix: str
    prefix_row_indices: list[int] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)
    suffix: str = ""

    def recomposes(self, rendered: str) -> bool:
        """Whether concatenating every part reproduces the rendering it came from."""
        return self.prefix + "".join(row.rendered for row in self.rows) + self.suffix == rendered


def header_rows_from_cells(cells: list[TableCell]) -> list[int]:
    """Row indices that a header-role cell covers, ascending and without duplicates.

    A header cell spanning several rows makes all of them header rows, and the result is
    whatever the provider marked — a table whose only ``columnHeader`` cells sit in row 3
    yields ``[3]``, not ``[0]``.
    """
    rows: set[int] = set()
    for cell in cells:
        if cell.role in HEADER_CELL_ROLES:
            rows.update(range(cell.row_index, cell.row_index + cell.row_span))
    return sorted(rows)


def row_continuations_from_cells(cells: list[TableCell]) -> dict[int, int]:
    """Map each row covered by a vertically merged cell to the row that cell starts in.

    The merged cell's content is rendered once, in that first row, so a fragment holding
    only the later rows would silently lose it. Where several merged cells cover the same
    row, the earliest origin wins: it is the furthest back a consumer must reach to keep
    the group whole.
    """
    continuations: dict[int, int] = {}
    for cell in cells:
        if cell.row_span <= 1:
            continue
        for row in range(cell.row_index + 1, cell.row_index + cell.row_span):
            origin = continuations.get(row)
            if origin is None or cell.row_index < origin:
                continuations[row] = cell.row_index
    return continuations


def partition_html_table(
    rendered: str,
    header_rows: list[int],
    continuations: dict[int, int],
    source_offset: int | None = None,
) -> RenderPartition:
    """Split an HTML table at ``</tr>`` boundaries.

    The prefix is ``<table>`` plus any leading rows the provider marked as header rows;
    the suffix is whatever follows the last row, normally ``</table>``. A rendering with
    no rows at all becomes an all-prefix partition rather than an error — there is nothing
    to cut, and reporting that honestly beats inventing a row.
    """
    matches = list(_HTML_ROW.finditer(rendered))
    starts = [m.start() for m in matches]
    body_end = matches[-1].end() if matches else len(rendered)
    return _partition(
        rendered=rendered,
        row_starts=starts,
        body_end=body_end,
        carried=_leading_header_run(header_rows, len(starts)),
        continuations=continuations,
        source_offset=source_offset,
    )


def partition_pipe_table(
    rendered: str,
    header_rows: list[int],
    continuations: dict[int, int],
    source_offset: int | None = None,
) -> RenderPartition:
    """Split a Markdown pipe table at line boundaries.

    GFM cannot express a table without a header line and its delimiter, so the prefix
    always carries at least the first row — whether or not the provider called it a
    header. That row is reported in ``prefix_row_indices``, because every fragment repeats
    it and a consumer should not have to read the markup to find that out.
    """
    lines = _line_starts(rendered)
    delimiter = _delimiter_line(rendered, lines)
    row_starts = [start for index, start in enumerate(lines) if index != delimiter]
    if not row_starts:
        return RenderPartition(prefix=rendered)

    carried = _leading_header_run(header_rows, len(row_starts))
    # Without the header line the fragment is not a table, so one row is the floor — but
    # only where there is a delimiter to make the line a header in the first place.
    if delimiter is not None:
        carried = max(carried, 1)
    return _partition(
        rendered=rendered,
        row_starts=row_starts,
        body_end=len(rendered),
        carried=carried,
        continuations=continuations,
        source_offset=source_offset,
    )


def _partition(
    rendered: str,
    row_starts: list[int],
    body_end: int,
    carried: int,
    continuations: dict[int, int],
    source_offset: int | None,
) -> RenderPartition:
    """Cut the rendering at the given row starts, with the first `carried` in the prefix.

    Every character lands in exactly one part: the prefix runs to the first body row, each
    body row runs to the next one, and the suffix is everything after the last.
    """
    carried = min(carried, len(row_starts))
    prefix_end = row_starts[carried] if carried < len(row_starts) else body_end
    rows: list[TableRow] = []

    for position in range(carried, len(row_starts)):
        start = row_starts[position]
        end = row_starts[position + 1] if position + 1 < len(row_starts) else body_end
        rows.append(
            TableRow(
                row_index=position,
                rendered=rendered[start:end],
                source_range=(
                    None
                    if source_offset is None
                    else (source_offset + start, source_offset + end)
                ),
                continues_from_row=continuations.get(position),
            )
        )

    return RenderPartition(
        prefix=rendered[:prefix_end],
        prefix_row_indices=list(range(carried)),
        rows=rows,
        suffix=rendered[body_end:],
    )


def _leading_header_run(header_rows: list[int], row_count: int) -> int:
    """How many rows from the top are header rows without a gap.

    Only an unbroken run from row 0 can sit in the prefix: hoisting a later header row
    would reorder the document and break the exactness rule, so a table whose header is
    row 3 carries nothing.
    """
    header = set(header_rows)
    run = 0
    while run < row_count and run in header:
        run += 1
    return run


def _line_starts(rendered: str) -> list[int]:
    """Index of the first character of each non-empty line."""
    starts: list[int] = []
    offset = 0
    for line in rendered.split("\n"):
        if line.strip():
            starts.append(offset)
        offset += len(line) + 1
    return starts


def _delimiter_line(rendered: str, line_starts: list[int]) -> int | None:
    """Which line, if any, is the pipe table's delimiter.

    Only the second line can be one: a dashes-and-pipes line anywhere else is a row whose
    cells happen to hold dashes, and treating it as markup would drop it from the output.
    """
    if len(line_starts) < 2:
        return None
    start = line_starts[1]
    end = rendered.find("\n", start)
    line = rendered[start:] if end == -1 else rendered[start:end]
    return 1 if _PIPE_DELIMITER.match(line.strip()) else None
