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

`ExtractedTable.rendered` holds the table's text exactly as it appears in `text`, and
`header_rendered` holds its header rows in the same form. Today, for Document
Intelligence, `rendered` is the HTML block that is already in the markdown. For Docling it
would be the pipe table. A consumer that needs a table's text reads `rendered`; a consumer
that needs its header reads `header_rendered`; neither ever looks for `<table` or `|---|`.

This is the field that removes the regex. `table_handler.extract_tables` exists precisely
because the chunker needed to know where a table started and ended in the text and had
only the rendering to go on. With spans and `rendered`, that question is answered by data.

`header_rendered` is computed by the adapter rather than the consumer because computing it
requires knowing which rows are headers *and* how the provider renders a table — both
adapter-side facts. For Document Intelligence it is the `<tr>` rows whose cells carry
`kind: columnHeader`; for Docling it is the pipe-table header row plus its separator.

## Decision: `header_rows` is indices, not cells

A table carries `header_rows: list[int]` — the row indices that form its header — computed
from cell roles. Two reasons over a boolean per cell: a consumer splitting a table needs to
ask "which rows do I repeat?" without walking every cell, and it keeps the header concept
row-shaped, which is what both providers and every rendering actually mean by it.

Document Intelligence marks header cells individually and they are conventionally, but not
necessarily, the leading rows; a table with `columnHeader` cells only in row 3 yields
`header_rows == [3]`. The adapter reports what it finds rather than assuming row 0.

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
