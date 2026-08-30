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
- [x] 5.3 Provenance row — dropped by decision: the index tracks Jira-keyed work, and
      this change has no ticket.

## Deviations and gaps

- **The live Azure tests have now been run** against the real service (`prebuilt-layout`,
  API `2024-11-30`): 14 passed. The generated PDF's table came back reconstructible from
  its cells alone, merged header cell included, and the spans resolved against the returned
  markdown. See "Live verification" below.
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

## Follow-up from review (second and third pass)

- **A torn pair across a failed text write.** Both artefacts sit at fixed paths, so a
  re-run overwrites them in place. The sidecar is written first — its outcome is a fact
  `text.json` has to report — which meant a failing `text.json` write left run 2's
  `analysis.json` beside run 1's `text.json`, with the row still pointing at both.
  `ProcessDocumentUseCase` now unpublishes the sidecar when the text write fails: the
  reference is cleared (the row is the source of truth for content location, so this is
  the safety property) and the blob deleted (cleanup on top). Both steps are best-effort
  so the original failure is what surfaces. `BlobClientPort` gained `delete_blob`, aliased
  on `BlobStoreAdapter` the same way `upload_blob` and `blob_exists` already are.
- Regression coverage asserts on *stored bytes*, not on upload calls — asserting on calls
  cannot see two fixed-path artefacts overwriting each other across runs.
- **Deleting the superseded sidecar was the wrong rollback.** Rolling back destroyed the
  *previous* run's raw payload, because the fixed path had already been overwritten before
  the failure. The sidecar now goes to a run-scoped path
  (`{tenant}/{file_id}/analysis/{run}.json`) and is published by moving the reference to
  it, which only happens once `text.json` is stored. A failed reprocess therefore leaves
  the last completed run untouched. The superseded sidecar is deleted after the reference
  moves past it, so runs do not accumulate one file each. Verified the regression tests
  fail with a fixed path restored: 4 of 7 do.
- **A failing reference update was still a way to read a mismatched pair.** `text.json`
  has a fixed path, so a reprocess replaces it irreversibly; if recording the references
  then failed, the row went on pointing at the previous run's raw analysis, which would
  read as though it described the newly published text. The reference cannot be corrected
  at that point — the store is what just failed — so both raw analyses are removed
  instead. A reference resolving to nothing is a visible fault; one resolving to the wrong
  run's analysis is a silent one. Found by writing the test the review asked for, not by
  reasoning about the code.

## Follow-up from review (fourth pass) — the structural fix

The limitation recorded in the third pass is now fixed, at the reviewer's request: **the
text output is run-scoped too**, so publication is the single update that records both
references, and a run either publishes both outputs or publishes nothing.

- Every failure mode collapses into one rule. A run writes its outputs where nothing can
  reach them, then records both references together. A failure anywhere before that —
  including in the reference update itself — leaves the previous extraction published,
  matched and whole, with nothing to roll back and no visible-versus-silent trade to make.
- The compensating deletes that earlier passes added are gone. What remains is sweeping:
  outputs a run abandoned, and outputs a newer run superseded.
- **Concurrency** falls out of the same property. Two overlapping runs each write under
  their own namespace and move both references in one update, so whichever commits last
  wins both columns and the row can never name one run's text beside another's analysis.
  Covered by an interleaving test that forces the worst ordering — run A reaches the
  publication point, stalls until run B completes, then publishes — and asserts the pair
  is matched. Verified it catches a torn publish: simulating a non-atomic reference update
  makes it fail.

This changes two things previously specified: the text output path
(`{tenant_id}/{file_id}/text/{run}.json`) and consequently the shape of `markdown_url` in
the `202` response. Both are captured in the `content-extraction` delta and `docs/`.

## Follow-up from review (fifth pass)

- **Concurrent runs leaked the loser's outputs.** Each run swept the pair it had observed
  before starting, so two overlapping runs that both observed P would both delete P, and
  whichever published first would leave its own outputs unreachable and never swept.
  `update_blob_references` now returns what it displaced, read inside the transaction that
  writes (under `WITH (UPDLOCK, ROWLOCK)`), and each run sweeps that. Covered at both
  levels: the interleaving test asserts only the published pair survives, and the SQL
  Server tests pin the returned values for a first write, a replacement, a clear, and an
  unknown document. Verified the unit test catches the leak — restoring the
  observed-at-start sweep makes it fail with the losing run's text blob left behind.

## Follow-up from review (sixth pass)

- **The lock I claimed did not exist.** `update_blob_references` read the previous
  references and then wrote the new ones, relying on `with_for_update()` to hold the row.
  SQLAlchemy's MSSQL dialect renders that as *no locking clause at all* — verified by
  compiling the statement against the dialect — so two concurrent publishes could still
  both report the same predecessor, and the pair published first would be orphaned.
  Replaced with a single `UPDATE ... OUTPUT deleted.text_blob_ref, deleted.analysis_blob_ref`
  statement: the swap and the report of what it displaced are one operation under one row
  lock, and `COALESCE`/`CASE` preserve the "None leaves it alone, clearing is explicit"
  semantics.
- **A temporal-table failure the concurrency test exposed.** `files` is system-versioned,
  and SQL Server stamps a row's period start with the *transaction's* start time. A
  transaction that began before another committed cannot then modify the row that one
  stamped — it fails with error 13535 rather than writing history out of order. Two
  overlapping publishes hit this. It would have failed the `convert` stage in production
  under ordinary concurrency, so the publish now retries in a fresh transaction, which
  starts after the winning stamp. Found by running the test, not by reading the code.
- **Two-session integration tests** against real SQL Server: two concurrent publishes must
  report *different* predecessors, and eight concurrent publishes must form a chain in
  which every pair written is displaced by exactly one publisher except the one the row
  ends up naming. Verified they discriminate — restoring the read-then-write makes the
  eight-way test fail.

## Live verification

Run against the configured Document Intelligence resource with
`DOCUMENT_INTELLIGENCE_RUN_TESTS=on`. 14 tests passed, and a one-off script printed what
actually came back:

```
model: prebuilt-layout | api: 2024-11-30 | format: markdown
pages: 1 words: 19 tables: 1 paragraphs: 9 confidence: 0.9944

TABLE RECONSTRUCTED FROM CELLS ALONE (4x2):
    ['Budget Summary', 'Budget Summary']
    ['Year', 'Amount']
    ['2025', '980']
    ['2026', '1250']
merged cell: 'Budget Summary' spans 2 cols; kind: columnHeader | page: 1 | polygon pts: 8
paragraph roles: ['title']
page geometry: 8.5 x 11.0 inch | lines: 9 | words: 19
RAW SIDECAR keys: ['apiVersion', 'content', 'contentFormat', 'modelId', 'pages',
                   'paragraphs', 'sections', 'stringIndexType', 'tables']
raw bytes: 8756 | text.json bytes: 9555
```

Re-run after adding `TableCell.elements` (below): 14 passed, and the sidecar's only
remaining unmodelled key is `stringIndexType`, a request-level knob rather than content.

Three things worth recording from it:

- **The premise of this change is visible in the output.** The markdown the service returns
  renders the table as raw HTML — `<table><tr><th colspan="2">Budget Summary</th>...` —
  which is exactly why the rendered text cannot stand in for the cell grid. The
  reconstruction above uses only `tables[].cells`.
- **The escape hatch earns its place.** The raw sidecar carries `stringIndexType`, a field
  the typed model does not declare. Under the previous mapping it was simply gone.
- **The size claim in the proposal was wrong** and has been corrected. The sidecar was
  *smaller* than `text.json` here (8.8 KB vs 9.6 KB), because the typed projection restates
  per-page words and lines that the raw response holds once.

- **`TableCell.elements` was missing, found by reading real output.** The service returns
  `"elements": ["/paragraphs/2"]` on a cell — the link back to the paragraphs its content
  came from. The typed model did not declare it, so it lived only in the sidecar. Added and
  mapped; `ExtractedFigure` and `DocumentSection` already carried the same field.
- **`scripts/show_extraction_output.py`** analyses a document and prints what the stage
  keeps before and after this change, with `--dump-to` to write `text.json`, its pre-change
  equivalent, and the raw analysis for inspection. On the bundled sample: 767 bytes kept
  before, 9,781 after. How to run it, and the three test suites, are documented in
  `docs/04-api-and-interfaces.md`.
