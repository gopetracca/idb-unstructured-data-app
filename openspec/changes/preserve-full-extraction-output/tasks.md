# Tasks

## 1. Domain model

- [ ] 1.1 Add value objects to `src/core/entities/document_analysis.py`: `BoundingRegion`
      (page_number, polygon), `Span` (offset, length), `DocumentWord`, `DocumentLine`,
      `SelectionMark`, `TableCell` (content, row_index, column_index, row_span,
      column_span, kind, spans, bounding_regions), `ExtractedTable` (row_count,
      column_count, cells, caption, footnotes, spans, bounding_regions), `ExtractedFigure`,
      `ExtractedParagraph` (content, role, spans, bounding_regions), `DocumentSection`,
      `DocumentStyle`, `KeyValuePair`.
- [ ] 1.2 Extend `PageContent` with the service's own `page_number`, `width`, `height`,
      `unit`, `angle`, `lines`, `words`, `selection_marks`, `spans` — all optional,
      defaulting to empty, leaving `page_number`/`text`/`word_count` semantics untouched.
- [ ] 1.3 Extend `MarkdownOutput` with `tables`, `figures`, `paragraphs`, `sections`,
      `styles`, `key_value_pairs`, `content_format`, `model_id` — all optional with empty
      defaults.
- [ ] 1.4 Extend `ExtractionMetadata` with `table_count`, `figure_count`,
      `paragraph_count`, `raw_analysis_stored`.
- [ ] 1.5 Confirm a `text.json` payload in the pre-change shape still deserialises.

## 2. Client and adapter

- [ ] 2.1 Have `DocumentIntelligenceClient.analyze_document` return the typed
      `AnalyzeResult` together with its verbatim serialised payload (serialise the SDK
      model's own mapping so unknown fields survive); same for
      `analyze_document_from_url`.
- [ ] 2.2 Rewrite `AzureDocumentIntelligenceAdapter._map_result_to_output` to map every
      structural element listed in §1, preserving spans and bounding regions on each.
      Keep the existing `extracted_text` fallback and single-page synthesis paths.
- [ ] 2.3 Widen the port return so the use case can reach the raw payload without
      importing an Azure type (return the typed output plus the raw mapping).
- [ ] 2.4 Give the fake adapter parity: paragraphs with roles, per-page lines, and one
      table with a column-header row and a merged cell.

## 3. Persistence of the raw result

- [ ] 3.1 Add `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` (default `true`) to
      `DocumentIntelligenceSettings`.
- [ ] 3.2 In `process_document.py`, write `{tenant_id}/{file_id}/analysis.json` after
      `text.json`, guarded by the setting; catch and warn on write failure and set
      `raw_analysis_stored` accordingly, without failing the stage.
- [ ] 3.3 Add nullable `analysis_blob_ref` to `src/core/entities/document.py` and
      `src/infrastructure/sqlserver/models/file_model.py`, including the field list at
      `file_model.py:107`.
- [ ] 3.4 Add Alembic revision `011_add_analysis_blob_ref.py` (nullable
      `String(1024)`, with a working downgrade).
- [ ] 3.5 Persist `analysis_blob_ref` in the same repository update that writes
      `text_blob_ref`.

## 4. Tests

- [ ] 4.1 `tests/unit/core/entities/test_document_analysis.py` — new value objects;
      pre-change payload still deserialises; empty collections when nothing is found.
- [ ] 4.2 `tests/unit/infrastructure/azure/adapters/test_document_intelligence_azure.py` —
      from a fixture `AnalyzeResult` containing a table with a merged cell, a header row,
      figures, paragraph roles, and page geometry: assert every element survives the
      mapping with its spans and bounding regions.
- [ ] 4.3 A reconstruction test: rebuild the grid from stored cells alone and assert the
      cells tile `row_count × column_count` without overlap and match the fixture.
- [ ] 4.4 `tests/unit/infrastructure/azure/adapters/test_document_intelligence_fake.py` —
      fake emits the same enriched shape.
- [ ] 4.5 `tests/unit/application/use_cases/test_process_document.py` — `analysis.json`
      written and `analysis_blob_ref` recorded; not written when the setting is false;
      a raising raw write leaves the `202` and the text output intact with
      `raw_analysis_stored=false`.
- [ ] 4.6 Chunking regression: `chunk_document` still reads `extracted_text` from an
      enriched `text.json` unchanged.
- [ ] 4.7 Migration test/check for `011` upgrade and downgrade.

## 5. Docs and spec bookkeeping

- [ ] 5.1 Document the `text.json` and `analysis.json` shapes and the new setting in
      `docs/`, including the note that `analysis_blob_ref` is null for documents extracted
      before this change.
- [ ] 5.2 Note the storage-volume implication of `analysis.json` for table-heavy corpora.
- [ ] 5.3 Add the ticket row to `openspec/provenance.md` and drop the now-fixed loss from
      any "known gaps" list it appears in.
