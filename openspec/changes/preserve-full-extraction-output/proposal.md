# Preserve the full Document Intelligence analysis result

## Why

The extraction adapter throws away most of what Document Intelligence returns. In
`AzureDocumentIntelligenceAdapter._map_result_to_output` the `AnalyzeResult` is reduced to
three things: the markdown string, one flat `text` per page built by joining word contents
with spaces, and an averaged word confidence. Everything else on the result is discarded:

- `tables` — cell text, `row_index` / `column_index`, `row_span` / `column_span`,
  `kind` (`columnHeader`, `rowHeader`, `stubHead`), caption, footnotes, page number
- `figures`, `paragraphs` (and their `role`: title, sectionHeading, pageHeader,
  pageFooter, footnote), `sections`, `styles`, `key_value_pairs`
- `spans` and `bounding_regions` everywhere — the offsets that map any element back into
  the markdown string, and the geometry that maps it back onto the page
- page geometry (`width`, `height`, `unit`, `angle`), `lines`, `selection_marks`, and the
  service's own `page_number`

The consequence the team is hitting: **tables cannot be reconstructed downstream.** The
markdown string contains a rendered HTML table, but there is no structured cell grid, no
span information, and no way to tell which page or which region of the document a table
came from. Anything that wants to re-emit a table as rows, index cells individually, chunk
on table boundaries, or attribute a retrieved answer to a page region has to re-call
Document Intelligence and pay for the analysis a second time — and for documents already
processed, the original result is simply gone.

Page-level text is lossy in its own right: joining `word.content` with single spaces
destroys line breaks, reading order between columns, and table cell boundaries, so
`pages[].text` is not a usable substitute for the structure either.

Extraction is the only stage that talks to the service, and re-running it is the most
expensive operation in the pipeline. The analysis result should be captured in full at the
moment it is produced.

## What Changes

- **Persist the raw `AnalyzeResult` verbatim.** Serialise the service response as received
  and store it beside the text output as `{tenant_id}/{file_id}/analysis.json`, recorded on
  the document as a new `analysis_blob_ref` column. This is lossless by construction and
  stays lossless when Azure adds fields the domain model does not model yet.
- **Extend the domain model with the structured elements**, so consumers that should not
  parse a raw SDK payload still get tables, figures, paragraphs with roles, sections,
  styles, key-value pairs, per-page geometry, lines, words, selection marks, and the spans
  and bounding regions attached to each. Table cells carry row/column index, spans, and
  kind — enough to reconstruct the grid without the markdown.
- **Keep `text.json` backward compatible.** `extracted_text`, `pages[].text`,
  `pages[].word_count`, and `extraction_metadata` keep their current meaning and shape; new
  fields are additive. The chunker, which reads `extracted_text` only, is unaffected.
- **Record what was preserved** in extraction metadata (table/figure/paragraph counts, and
  whether the raw result was stored) so a document processed before this change is
  distinguishable from one processed after.
- **Fake adapter parity.** The fake produces the same enriched shape, including at least
  one multi-page-spanning table with header cells and a merged cell, so table
  reconstruction is exercisable with `DOCUMENT_INTELLIGENCE_USE_FAKE=true`.
- **New setting** `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` (default `true`) to switch off
  raw-result persistence where blob volume matters. Structured fields in `text.json` are
  not gated — they are the point of the change.

Out of scope: changing how chunking, vectorization, or search consume the extracted text.
This change makes the data available and stops the loss; using tables downstream is
follow-on work.

## Impact

- Affected specs: `content-extraction` (modified), `metadata-persistence` (new column)
- Affected code:
  - `src/core/entities/document_analysis.py` — new value objects, extended `MarkdownOutput`
  - `src/infrastructure/azure/adapters/document_intelligence_azure.py` — full mapping
  - `src/infrastructure/azure/adapters/document_intelligence_fake.py` — parity
  - `src/infrastructure/azure/clients/document_intelligence_client.py` — return the raw
    payload alongside the typed result
  - `src/application/ports/document_intelligence.py` — port return type
  - `src/application/use_cases/process_document.py` — write `analysis.json`, record the ref
  - `src/core/entities/document.py`, `src/infrastructure/sqlserver/models/file_model.py`,
    new Alembic revision `011_add_analysis_blob_ref.py`
  - `src/config/settings.py` — `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT`
- Storage: measured against the real service on a one-page table-bearing PDF, the raw
  analysis was 8.8 KB against 9.6 KB for the text output — comparable, not a multiple, since
  the typed projection re-states per-page words and lines the raw response holds once.
  Blob cost either way, not latency: the payload is already in memory.
- No API contract change. `POST /api/v1/contents` still returns `202` with the same body.
