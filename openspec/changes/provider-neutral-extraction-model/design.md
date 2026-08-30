# Design

## Context

Two extraction services are in scope: Azure Document Intelligence (`prebuilt-layout`,
in production) and Docling (under consideration). They model the same document in
structurally different ways, and the contract has to be satisfiable by both without either
one's vocabulary leaking into it.

| Concern | Azure Document Intelligence | Docling | Canonical |
| --- | --- | --- | --- |
| Rendered text | `content`, markdown, tables as HTML | `export_to_markdown()`, tables as pipe tables | `text`, whatever the adapter rendered |
| Text ↔ element link | `spans: [{offset, length}]` into `content` | `prov[].charspan` into the item's own text | `(start, end)` into `text`, guaranteed by the adapter |
| Reading order | `paragraphs` in order; tables interleaved by span | body tree traversal | `blocks`, in order |
| Element kind | `paragraphs[].role` (`title`, `sectionHeading`, `pageHeader`, `pageFooter`, `footnote`) | `DocItemLabel` (`title`, `section_header`, `paragraph`, `caption`, `list_item`, `page_header`, …) | `BlockKind` |
| Table shape | `rowCount`/`columnCount`, `cells[]` | `TableData.num_rows`/`num_cols`, `table_cells[]` | `row_count`/`column_count`, `cells[]` |
| Cell position | `rowIndex`, `columnIndex`, `rowSpan`, `columnSpan` | `start_row_offset_idx`, `end_row_offset_idx`, `start_col_offset_idx`, `end_col_offset_idx`, `row_span`, `col_span` | `row_index`, `column_index`, `row_span`, `column_span` |
| Header cells | `kind: columnHeader \| rowHeader \| stubHead` | `column_header: bool`, `row_header: bool`, `row_section: bool` | `role: CellRole` |
| Geometry | `boundingRegions[].polygon`, 8 floats, inches, top-left origin | `prov[].bbox` (`l`,`t`,`r`,`b`) with `CoordOrigin`, points | `bbox` + `unit` + `origin`, `polygon` kept when given |
| Page | `boundingRegions[].pageNumber` | `prov[].page_no` | `page_number` |
| Cross-references | `elements: ["/paragraphs/2"]` | `$ref: "#/texts/2"` | `elements: list[str]`, opaque |

The differences that actually matter are the first two rows. Everything else is renaming.

## Decision: the adapter owns the offset invariant

The contract is *"every block's `(start, end)` indexes into `text`"*, not *"the provider
gives us offsets"*. Document Intelligence satisfies it by reporting spans into the
`content` it returns. Docling has no equivalent global string — `charspan` is relative to
an item, and `export_to_markdown()` is a separate rendering pass — so a Docling adapter
would render the document itself, appending each element to a buffer and recording the
range it wrote. That is more work in the adapter and it is the right place for the work:
one adapter absorbs it once, and every consumer downstream gets the same guarantee.

The alternative — exposing provider-shaped provenance and making consumers reconcile it —
puts the hardest part of the problem in the layer with the least context, repeatedly.

## Decision: the adapter renders tables; nothing downstream parses

`ExtractedTable.rendered` holds the table's text exactly as it appears in `text`. Today,
for Document Intelligence, that is the HTML block already in the markdown; for Docling it
would be the pipe table. A consumer that needs a table's text reads `rendered`; a consumer
that needs part of one composes `render_prefix`, the rows it wants, and `render_suffix`.
Neither ever looks for `<table` or `|---|`.

This is the field that removes the regex. `table_handler.extract_tables` exists precisely
because the chunker needed to know where a table started and ended in the text and had
only the rendering to go on. With spans and `rendered`, that question is answered by data.

The prefix/suffix pair exists because a consumer emitting part of a table needs to produce
a *valid* table, and validity is a property of the rendering. `render_prefix` is the
opening markup plus the header rows; `render_suffix` closes it; `rows` holds the body rows
individually. Any subset is then `render_prefix + those rows + render_suffix`, composed by
concatenation and nothing else.

For Document Intelligence, the adapter partitions the HTML it already has at `</tr>`
boundaries: prefix is `<table>` plus the header `<tr>` elements, each body row is one
`<tr>…</tr>`, suffix is `</table>`. For Docling it is the pipe header plus its separator
line, one line per row, and an empty suffix. Both are provider-specific parsing done in the
provider-specific place, once.

**Why not cell spans.** An earlier draft of the dependent change proposed cutting tables at
row boundaries derived from cell spans. That is wrong, and checkably so. Document
Intelligence spans cover cell *content*, not the markup around it: on a real response the
span of the cell `Budget Summary` resolves to exactly `Budget Summary`, so the min-to-max
range over row 0's cells is that same string, while the row's rendering is
`<tr>\n<th colspan="2">Budget Summary</th>\n</tr>`. Cutting there produces text that is not
a table in any rendering. Three further cases break the same assumption: an empty cell may
carry no span at all, so a row of empty cells has no derivable range; a vertically merged
cell belongs to several rows but spans only where its content sits; and a cell's content
may arrive as several discontiguous spans.

**The exactness rule.** For a table whose rendering is contiguous in `text`,
`render_prefix + every row's rendering + render_suffix` SHALL equal `rendered` exactly. The
adapter can guarantee this by construction, because it partitions a string it produced
rather than reassembling one it inferred — and the equality is a cheap, decisive test that
an adapter has done the partition correctly.

**Merged cells across rows.** A cell spanning several rows makes those rows inseparable:
its content is rendered once, in the first of them, and a piece containing only the later
rows would silently lose it. Each row therefore records `continues_from_row` when it is
covered by a vertical span originating above it. Consumers treat such rows as one
indivisible group. The alternative — repeating the spanning cell's content in each piece,
as the header is repeated — was rejected: the header is a label whose repetition is
unambiguous, while repeating a data cell fabricates rows that were never in the document.

## Decision: `header_rows` is indices, not cells

A table carries `header_rows: list[int]` — the row indices that form its header — computed
from cell roles. Two reasons over a boolean per cell: a consumer splitting a table needs to
ask "which rows do I repeat?" without walking every cell, and it keeps the header concept
row-shaped, which is what both providers and every rendering actually mean by it.

Document Intelligence marks header cells individually and they are conventionally, but not
necessarily, the leading rows; a table with `columnHeader` cells only in row 3 yields
`header_rows == [3]`. The adapter reports what it finds rather than assuming row 0.

**`header_rows` and what the prefix repeats are not the same set.** `render_prefix` carries
the opening markup plus the *leading contiguous run* of header rows — rows 0..k where every
one of them is a header row — which may be empty. A header row outside that run stays an
ordinary body row: it is reported in `header_rows`, because that is what the provider found,
and it is not repeated into every piece.

The two must be distinguished or the model contradicts itself. Take `header_rows == [3]`. If
the prefix carried row 3, then the prefix followed by the body rows would render 3, 0, 1, 2,
4… — a different document from the one the extractor produced, and a direct violation of the
exactness rule two decisions above. Restricting the prefix to the leading run keeps
concatenation order-preserving, so exactness holds by construction rather than by luck.

It also keeps repetition honest. Repeating a mid-table header into a piece that holds rows
10–20 asserts that those rows sit under that header, which for a row-3 header of an
irregular table is a guess. Repeating the leading run asserts only what the rendering
already shows.

## Decision: units are recorded, never normalised

Document Intelligence reports inches; Docling reports points. Converting in the adapter
would mean the canonical model carries a number whose meaning depends on a conversion no
consumer can see. The canonical `BoundingBox` therefore carries `unit` (`inch`, `point`,
`pixel`) and `origin` (`top_left`, `bottom_left`) alongside the coordinates, and any
consumer comparing geometry across documents is responsible for checking them. Downstream
code today uses page numbers, not geometry, so this costs nothing now and prevents a
silent class of error later.

## Decision: keep `pages[].text`, deprecate it in documentation

`pages[].text` — words joined by single spaces — is lossy and now redundant with
`blocks` and `pages[].lines`. It stays for compatibility and is documented as
superseded. Removing it is a separate change with its own consumers to check.

## What this change deliberately does not do

- **No Docling adapter.** The mapping above is specified and the contract is designed
  against it, but writing an adapter for a dependency the project has not adopted would be
  speculative. What this change guarantees is that adopting Docling later is an adapter,
  not a redesign.
- **No consumer changes.** The chunker keeps reading `extracted_text` and keeps its regex
  until `structure-aware-chunking` replaces it. Shipping the contract and the migration in
  one change would make both harder to review and to revert.
- **No re-extraction.** Documents extracted before this change have no `blocks`. They are
  not backfilled — that means paying the extraction service again for the whole corpus, a
  decision with a budget attached, not a side effect of a refactor.
