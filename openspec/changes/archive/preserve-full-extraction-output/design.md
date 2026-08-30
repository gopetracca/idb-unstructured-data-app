# Design

## Context

`prebuilt-layout` with `outputContentFormat=markdown` returns one `AnalyzeResult` carrying
both a rendered markdown string and the structural analysis that produced it. The adapter
currently keeps the string and drops the analysis. The question this change answers is not
*whether* to keep the rest, but in what form.

## Decision: keep both a verbatim copy and a typed projection

Two artefacts, written in the same stage:

| Artefact | Blob | Shape | Consumer |
| --- | --- | --- | --- |
| Raw analysis | `{tenant}/{file_id}/analysis.json` | the service response, unmodified | forensics, reprocessing, anything the domain model does not yet model |
| Text output | `{tenant}/{file_id}/text.json` | `MarkdownOutput`, extended | pipeline stages, application code |

### Why not typed-only

A typed model is a filter. Every field the model does not declare is silently dropped —
which is exactly the failure this change exists to fix, recurring the next time Azure adds
a field or the team needs something nobody modelled. A verbatim copy is lossless by
construction and its correctness does not depend on the model being complete.

### Why not raw-only

Application and pipeline code depending on the raw SDK payload shape would push an
infrastructure concern through the ports into use cases, against the layering rule the
project holds. It also makes the fake adapter meaningless: it would have to emit
hand-written Azure JSON to be useful. The typed projection keeps the domain boundary and
gives downstream code a stable contract; the raw copy is the escape hatch.

### Serialisation of the raw copy

The Azure SDK models are `dict`-backed; serialise the response object's own mapping rather
than re-deriving it field by field, so unknown fields survive. Store as pretty-printed
JSON with `content_type="application/json; charset=utf-8"`, matching `text.json`.

## Decision: `analysis_blob_ref` is a column, not a convention

The project's rule is that blob references in SQL are the source of truth and paths are
never reconstructed by convention. `analysis.json` follows it: a nullable
`analysis_blob_ref` column on the document, written in the same stage as `text_blob_ref`.
Nullable matters — documents extracted before this change legitimately have no raw
analysis, and readers must treat `NULL` as "not captured", not as an error.

## Decision: additive extension of `MarkdownOutput`

`extracted_text`, `pages[].text`, `pages[].word_count`, `extraction_metadata`, `file_id`,
`file_version`, and `created_at` keep their current names and meaning. Everything new is a
new optional field defaulting to empty. Consequences:

- The chunker (`extracted_text` only) needs no change and no coordinated deploy.
- A `text.json` written before this change still deserialises.
- The lossy `pages[].text` stays for compatibility but is no longer the only page-level
  representation — `pages[].lines` preserves line breaks and reading order.

## Table reconstruction: the acceptance bar

The structured table model must be sufficient to rebuild a grid without consulting the
markdown. That requires, per table: `row_count`, `column_count`, the page(s) it appears on,
caption and footnotes; and per cell: `row_index`, `column_index`, `row_span`,
`column_span`, `kind`, `content`, `spans`, `bounding_regions`. A cell grid is
reconstructible when every cell's `(row_index, column_index)` plus its spans tile the
declared `row_count × column_count` without overlap. This is stated as a scenario so it is
testable, and the fake adapter emits a table with a merged cell and a column header row so
the test has a fixture that exercises it.

## Spans are the join key

Every element carries `spans` — `(offset, length)` pairs into `AnalyzeResult.content`,
which is the markdown string stored as `extracted_text`. Preserving spans is what makes it
possible to say "this chunk of markdown is that table's third row" later, and is the
foundation for table-aware chunking. Spans are therefore preserved on every element that
has them, not only on tables.

## Cost and failure posture

- The raw payload is already in memory; persisting it is one extra blob write, no extra
  service call.
- `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT=false` suppresses the raw blob only. The
  structured fields in `text.json` are always populated.
- A failed `analysis.json` write must not fail the stage: the text output and its blob ref
  are the pipeline's contract, and losing the raw sidecar degrades fidelity without
  breaking the document. It is logged as a warning and reflected in
  `extraction_metadata.raw_analysis_stored=false`.

## Open question

Whether to backfill `analysis.json` for already-extracted documents. Backfill means paying
Document Intelligence again for every historical document. Not proposed here; if wanted it
should be an explicit, separately budgeted change.
