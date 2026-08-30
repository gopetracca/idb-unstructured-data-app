# Tasks

## 1. Canonical model

- [ ] 1.1 Add to `src/core/entities/document_analysis.py`: `BlockKind` (heading,
      paragraph, table, figure, caption, list_item, other), `CellRole` (content,
      column_header, row_header, section_row, stub_head), `CoordinateUnit` (inch, point,
      pixel), `CoordinateOrigin` (top_left, bottom_left), `BoundingBox` (page_number,
      left, top, right, bottom, unit, origin, optional polygon), and `ContentBlock`
      (kind, start, end, page_number, bounding_box, role, table_index, elements).
- [ ] 1.2 Replace `TableCell.kind: str` with `role: CellRole`, keeping `kind` readable as
      a deprecated alias so a pre-change `text.json` still loads.
- [ ] 1.3 Add to `ExtractedTable`: `header_rows: list[int]`, `rendered: str`,
      `render_prefix: str` (exactly the part of the rendering preceding the first body
      row), `prefix_row_indices: list[int]` (the rows, if any, it carries),
      `render_suffix: str`, and `rows: list[TableRow]` holding the remainder in document
      order.
- [ ] 1.3a Add `TableRow`: `row_index`, `rendered`, `source_range: tuple[int, int] | None`,
      `continues_from_row: int | None`.
- [ ] 1.4 Add `blocks: list[ContentBlock]` to `MarkdownOutput`, defaulting to empty.
- [ ] 1.5 Confirm a pre-change `text.json` still deserialises, with empty blocks and cell
      roles mapped from the old `kind` strings.

## 2. Port

- [ ] 2.1 Rename `DocumentIntelligencePort` to `DocumentExtractorPort` in
      `src/application/ports/`, keeping the old name as an alias so no caller breaks.
- [ ] 2.2 State the offset invariant in the port docstring: every block's `(start, end)`
      resolves against the returned `extracted_text`, and the adapter is responsible for it
      however its provider reports position.
- [ ] 2.3 Check no application or presentation module names Document Intelligence in a
      type or a docstring that describes behaviour rather than the current adapter.

## 3. Azure adapter conformance

- [ ] 3.1 Emit `blocks` in reading order, interleaving paragraphs and tables by span
      offset, mapping paragraph roles to `BlockKind` (`title`/`sectionHeading` → heading,
      others → paragraph, with the role preserved). On each block set `start` and `end`
      from the element's span, `page_number` and `bounding_box` from its bounding regions,
      `elements` from the provider's references, and `table_index` on every table block so
      it resolves to its entry in `tables` — without that last one a consumer can see that a
      region is a table and not reach the renderings needed to emit part of one.
- [ ] 3.2 Map cell `kind` strings to `CellRole`; derive `header_rows` from the cells that
      carry a header role.
- [ ] 3.3 Populate `rendered` from the table's span into `content`. Derive `render_prefix`,
      `rows` and `render_suffix` by partitioning that rendering at `</tr>` boundaries —
      partitioning a string the adapter already has, never reassembling one from cell
      spans, which cover cell content only and would exclude the markup.
- [ ] 3.3b Populate `prefix_row_indices` with the rows the prefix carries — for this
      adapter, the leading header `<tr>` elements, which is non-empty for most tables — and
      `row_index` on each body row, numbering rows across the whole table so the prefix's
      rows and the body rows share one sequence. Leaving `prefix_row_indices` empty for a
      prefix that carries rows would report that nothing is repeated when something is.
- [ ] 3.3a Record each body row's `source_range` from its offset within the table's span,
      and set `continues_from_row` for rows covered by a cell with a row span greater
      than one.
- [ ] 3.4 Convert `boundingRegions[].polygon` to a canonical `BoundingBox` with
      `unit=inch`, `origin=top_left`, retaining the polygon.
- [ ] 3.5 Fake adapter: same canonical output, including a table whose `rendered`,
      `render_prefix`, `rows` and `render_suffix` are consistent with its `extracted_text`
      and satisfy the exactness rule.

## 4. Use case and storage

- [ ] 4.1 `process_document.py` — no logic change expected; confirm `blocks` serialise
      into `text.json` and that the raw sidecar is untouched.
- [ ] 4.2 Measure the size change on the sample document and record it, replacing the
      estimate in the proposal with the measurement.

## 5. Tests

> Where a task names a scenario, the scenario in the delta is the statement of record and
> the task must not paraphrase it.

- [ ] 5.1 `tests/unit/core/entities/test_document_analysis.py` — canonical types round-trip;
      a pre-change `text.json` loads with empty blocks and roles mapped from `kind`.
- [ ] 5.2 `tests/unit/infrastructure/adapters/test_document_intelligence_azure.py` — from
      the existing fixture: blocks in reading order, every block's span resolves against
      `extracted_text`, header rows derived from roles, `rendered` equal to the text at the
      table's span.
- [ ] 5.2a Cover *The fragment for every body row is the whole table*: the fragment composed from
      every **body** row equals `rendered` byte for byte, for a contiguously rendered table.
      Rows the prefix carries are not body rows and are not counted twice.
- [ ] 5.2b A table with an empty cell, and one with a cell spanning two rows: rows still
      partition the rendering, and the covered rows are marked `continues_from_row`.
- [ ] 5.2c A table whose header row is not its first row: `header_rows` reports it, the
      opening rendering does not carry it, it stays a body row in document order, and the
      exactness rule still holds.
- [ ] 5.2d A table with no header at all, in a form that requires a header line: the opening
      rendering still carries that line and its delimiter, every fragment parses as a table
      in that form, and `prefix_row_indices` names the row being repeated.
- [ ] 5.3 A contract test that any extractor adapter must pass — offset invariant, canonical
      roles, header rows, the exactness rule, and composability of an arbitrary row subset
      into a valid table — parameterised over the adapters that exist, so a future Docling
      adapter inherits the same bar.
- [ ] 5.4 Fake adapter passes the same contract test.
- [ ] 5.4a Every field the canonical model declares is populated by the Azure adapter and
      asserted somewhere in these tests. A field with no producer is indistinguishable from
      one the provider does not supply, and this list has already grown fields that nothing
      set.
- [ ] 5.5 Live test: the offset invariant and `rendered` hold against the real service.

## 6. Docs

- [ ] 6.1 Document the canonical model in `docs/04-api-and-interfaces.md` beside the
      existing `text.json` description, including the provider mapping table from
      `design.md` — a reader adding an extractor should find the contract, not infer it.
- [ ] 6.2 Note `pages[].text` as superseded by `blocks` and `pages[].lines`.
