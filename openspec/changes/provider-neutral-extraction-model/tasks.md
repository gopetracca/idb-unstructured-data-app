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
      `header_rendered: str`.
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
      others → paragraph, with the role preserved).
- [ ] 3.2 Map cell `kind` strings to `CellRole`; derive `header_rows` from the cells that
      carry a header role.
- [ ] 3.3 Populate `rendered` from the table's span into `content`, and `header_rendered`
      from the header rows' spans — both taken from the markdown, not re-serialised, so
      they are exactly what a consumer would have found in the text.
- [ ] 3.4 Convert `boundingRegions[].polygon` to a canonical `BoundingBox` with
      `unit=inch`, `origin=top_left`, retaining the polygon.
- [ ] 3.5 Fake adapter: same canonical output, including a table whose `rendered` and
      `header_rendered` are consistent with its `extracted_text`.

## 4. Use case and storage

- [ ] 4.1 `process_document.py` — no logic change expected; confirm `blocks` serialise
      into `text.json` and that the raw sidecar is untouched.
- [ ] 4.2 Measure the size change on the sample document and record it, replacing the
      estimate in the proposal with the measurement.

## 5. Tests

- [ ] 5.1 `tests/unit/core/entities/test_document_analysis.py` — canonical types round-trip;
      a pre-change `text.json` loads with empty blocks and roles mapped from `kind`.
- [ ] 5.2 `tests/unit/infrastructure/adapters/test_document_intelligence_azure.py` — from
      the existing fixture: blocks in reading order, every block's span resolves against
      `extracted_text`, header rows derived from roles, `rendered` equal to the text at the
      table's span, `header_rendered` equal to the header rows' text.
- [ ] 5.3 A contract test that any extractor adapter must pass — offset invariant, canonical
      roles, header rows, rendered strings — parameterised over the adapters that exist, so
      a future Docling adapter inherits the same bar.
- [ ] 5.4 Fake adapter passes the same contract test.
- [ ] 5.5 Live test: the offset invariant and `rendered` hold against the real service.

## 6. Docs

- [ ] 6.1 Document the canonical model in `docs/04-api-and-interfaces.md` beside the
      existing `text.json` description, including the provider mapping table from
      `design.md` — a reader adding an extractor should find the contract, not infer it.
- [ ] 6.2 Note `pages[].text` as superseded by `blocks` and `pages[].lines`.
