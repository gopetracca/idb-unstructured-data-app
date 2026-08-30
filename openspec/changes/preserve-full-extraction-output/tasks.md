# Tasks

## 1. Domain model

- [x] 1.1 Add value objects to `src/core/entities/document_analysis.py`: `BoundingRegion`
      (page_number, polygon), `Span` (offset, length), `DocumentWord`, `DocumentLine`,
      `SelectionMark`, `TableCell` (content, row_index, column_index, row_span,
      column_span, kind, spans, bounding_regions), `ExtractedTable` (row_count,
      column_count, cells, caption, footnotes, spans, bounding_regions), `ExtractedFigure`,
      `ExtractedParagraph` (content, role, spans, bounding_regions), `DocumentSection`,
      `DocumentStyle`, `KeyValuePair`.
- [x] 1.2 Extend `PageContent` with the service's own `page_number`, `width`, `height`,
      `unit`, `angle`, `lines`, `words`, `selection_marks`, `spans` — all optional,
      defaulting to empty, leaving `page_number`/`text`/`word_count` semantics untouched.
- [x] 1.3 Extend `MarkdownOutput` with `tables`, `figures`, `paragraphs`, `sections`,
      `styles`, `key_value_pairs`, `content_format`, `model_id` — all optional with empty
      defaults.
- [x] 1.4 Extend `ExtractionMetadata` with `table_count`, `figure_count`,
      `paragraph_count`, `raw_analysis_stored`.
- [x] 1.5 Confirm a `text.json` payload in the pre-change shape still deserialises.

## 2. Client and adapter

- [x] 2.1 Have `DocumentIntelligenceClient.analyze_document` return the typed
      `AnalyzeResult` together with its verbatim serialised payload (serialise the SDK
      model's own mapping so unknown fields survive); same for
      `analyze_document_from_url`.
- [x] 2.2 Rewrite `AzureDocumentIntelligenceAdapter._map_result_to_output` to map every
      structural element listed in §1, preserving spans and bounding regions on each.
      Keep the existing `extracted_text` fallback and single-page synthesis paths.
- [x] 2.3 Give the use case access to the raw payload without importing an Azure type.
      **Done differently:** rather than widening the port's return type — which would have
      touched every caller and every test double for a value only one caller wants —
      `MarkdownOutput` carries a `raw_analysis` dict marked `exclude=True`. The port
      signature is unchanged, nothing outside infrastructure names an SDK type, and
      `model_dump()` still produces exactly the text.json body.
- [x] 2.4 Give the fake adapter parity: paragraphs with roles, per-page lines, and one
      table with a column-header row and a merged cell.

## 3. Persistence of the raw result

- [x] 3.1 Add `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` (default `true`) to
      `DocumentIntelligenceSettings`.
- [x] 3.2 In `process_document.py`, write `{tenant_id}/{file_id}/analysis.json` after
      `text.json`, guarded by the setting; catch and warn on write failure and set
      `raw_analysis_stored` accordingly, without failing the stage.
- [x] 3.3 Add nullable `analysis_blob_ref` to `src/core/entities/document.py` and
      `src/infrastructure/sqlserver/models/file_model.py`, including the field list at
      `file_model.py:107`.
- [x] 3.4 Add Alembic revision `011_add_analysis_blob_ref.py` (nullable
      `String(1024)`, with a working downgrade).
- [x] 3.5 Persist `analysis_blob_ref` in the same repository update that writes
      `text_blob_ref`.

## 4. Tests

- [x] 4.1 `tests/unit/core/entities/test_document_analysis.py` — new value objects;
      pre-change payload still deserialises; empty collections when nothing is found.
- [x] 4.2 `tests/unit/infrastructure/azure/adapters/test_document_intelligence_azure.py` —
      from a fixture `AnalyzeResult` containing a table with a merged cell, a header row,
      figures, paragraph roles, and page geometry: assert every element survives the
      mapping with its spans and bounding regions.
- [x] 4.3 A reconstruction test: rebuild the grid from stored cells alone and assert the
      cells tile `row_count × column_count` without overlap and match the fixture.
- [x] 4.4 `tests/unit/infrastructure/azure/adapters/test_document_intelligence_fake.py` —
      fake emits the same enriched shape.
- [x] 4.5 `tests/unit/application/use_cases/test_process_document.py` — `analysis.json`
      written and `analysis_blob_ref` recorded; not written when the setting is false;
      a raising raw write leaves the `202` and the text output intact with
      `raw_analysis_stored=false`.
- [x] 4.6 Chunking regression: `chunk_document` still reads `extracted_text` from an
      enriched `text.json` unchanged.
- [x] 4.7 Migration `011` executed against real SQL Server 2022 (the testcontainers
      fixture that runs `alembic upgrade head`): upgrade, downgrade to `010`, and
      re-upgrade all succeed, with `analysis_blob_ref` present as `varchar(1024)` on both
      `files` and `files_history` and absent from both after downgrade.
- [x] 4.8 Repository-level tests for the raw-analysis reference against real SQL Server,
      covering the explicit clear (`tests/integration/infrastructure/test_analysis_blob_ref_sqlserver.py`).

## 5. Docs and spec bookkeeping

- [x] 5.1 Document the `text.json` and `analysis.json` shapes and the new setting in
      `docs/`, including the note that `analysis_blob_ref` is null for documents extracted
      before this change.
- [x] 5.2 Note the storage-volume implication of `analysis.json` for table-heavy corpora.
- [ ] 5.3 Add the row to `openspec/provenance.md`. **Deferred, not skipped:** that table
      indexes tickets to the capabilities carrying them, and its stated purpose is to
      record work that has been through the loop. This change has no Jira key yet and is
      not archived, so the row belongs at archive time. Nothing to drop from "known gaps"
      — this loss was never recorded there.

## Deviations and gaps

- **The live Azure tests have never been run.** No Document Intelligence endpoint or key
  is available in this workspace, so `tests/integration/infrastructure/test_document_intelligence_live.py`
  has only been shown to skip cleanly. Its offline half — the PDF builder and the
  reconstruction assertions it shares with the unit tests — does run.
- **Migration 011 has now been executed** against SQL Server 2022 in a container — see
  task 4.7. The earlier note that it was unverified no longer applies.
- Marked the test files this change touches with `@pytest.mark.unit`. CI runs
  `pytest -m unit`, and these files carried no marker, so their tests were being collected
  and then deselected in CI. Selected unit tests went from 224 to 336 as a result.

## Follow-up from review

- **A cleared sidecar must clear its reference.** `update_blob_references` treats `None`
  as "leave it alone", which is right for stages that only own one path — but it meant a
  re-processed document kept pointing at the *previous* run's `analysis.json` while the
  freshly written `text.json` said `raw_analysis_stored: false`. Added an explicit
  `clear_analysis_blob_ref` flag on the pipeline-store and file-index ports and their SQL
  Server repositories; `ProcessDocumentUseCase` sets it whenever a run produced no
  sidecar. Covered at both levels: use-case tests for the disabled / failed / no-payload
  paths, and SQL Server tests for the column itself.
- The now-orphaned `analysis.json` blob from the earlier run is left in place. Nothing
  points at it, and `delete_document` already removes it with the `{tenant}/{file_id}/`
  prefix, so deleting it here would add a failure mode without removing a stale read path.
