# Structure-aware chunking

> Depends on `provider-neutral-extraction-model`. This change consumes the canonical
> block list that one introduces; it should not be implemented before it.

## Why

Chunking is where a table's structure either survives into the index or is lost. Today it
survives, but by a mechanism that only works for one provider and one chunker, and it
survives incompletely.

**What works today.** `ChonkieChunker` extracts `<table>…</table>` spans by regex,
replaces each with a placeholder, chunks the remaining text, and re-inserts each table as
a single atomic chunk carrying `has_table`, `table_id`, `section_path` and `page_number`.
Tables are not split mid-row.

**Three things do not.**

- **A large table becomes one oversized chunk.** The table branch computes `token_count`
  and never acts on it. A 400-row table is one chunk; at embedding time it either fails
  the model's input limit or is silently truncated, and the tail of the table is not
  retrievable at all. The failure is worst exactly where tables matter most.
- **Only Chonkie does it.** `chunker_llamaindex.py` has no table handling. Which structure
  a document keeps depends on which chunker is configured, which is not a property the
  chunking stage should have.
- **The chunk text is markup.** A table chunk's text is the raw HTML — `<tr>`, `<td>` and
  all — so the embedding encodes markup alongside values, and a retrieved chunk shown to a
  user is HTML.

Underneath all three: the chunker recovers structure by pattern-matching a rendering,
rather than reading the structure the extractor already stored.

## What Changes

Move table handling out of one adapter and onto the stage, and drive it from the canonical
blocks rather than from a regex.

- **Tables are atomic by span, not by pattern.** The chunker takes table boundaries from
  the extraction output's block list. No `<table>` scan, no placeholders, and the same
  behaviour whether the extractor rendered HTML, pipe tables, or anything else.
- **Oversized tables split on row boundaries, repeating the table's prefix.** When a table
  exceeds the strategy's chunk size, it is split between rows — never inside one — and each
  piece is composed as a fragment, so it is a valid table carrying whatever the rendering
  places before the first body row. Where that is a header, a chunk holding rows 40–60
  still says which columns those values are in. Rows joined by a cell that spans them are
  never separated.
- **Chunk offsets become provenance.** A piece carrying a repeated prefix is no longer a
  verbatim slice of the extracted text, so `start_char`/`end_char` are restated as the
  range the chunk's own rows occupy, with the prefix's range recorded separately.
  One consumer is affected today — `list_chunks` derives a character count by subtracting
  the offsets. It cannot simply measure the text instead: it serves a paginated listing from
  index rows that carry only a preview. The composed length is therefore recorded when the
  chunk is created and read from the index, with a migration that backfills it exactly from
  the existing offsets.
- **Table chunks carry the extractor's rendering.** Chunk text comes from the canonical
  `rendered` string, so what is embedded and what is shown is whatever form the extractor
  produced, and the pipeline stops caring which.
- **The behaviour belongs to the stage.** Splitting and prefix propagation move above the
  chunker port, so every strategy and every chunker adapter gets them. Adapters keep doing
  what they are good at: splitting prose.
- **A split table stays one table.** The pieces cover the table exactly once — no
  additional whole-table chunk is emitted beside them. Duplicating a table at two
  granularities doubles its storage and lets the copy compete with its own pieces in
  results, which is a retrieval problem dressed as a feature.
- **Chunk metadata gains the table's identity and extent.** `has_table` and `table_id`
  keep their meaning; a split piece additionally records which rows of the table it holds,
  so a consumer can tell a partial table from a whole one.
- **Documents without blocks keep working.** When the extraction output has no block list —
  anything extracted before `provider-neutral-extraction-model` — the current regex path is
  used unchanged. It is a fallback with a defined trigger, not the primary mechanism.

Out of scope: re-chunking existing documents (their chunks stay as they are until
rechunked), and any change to embedding, ingestion, or search.

## Impact

- Affected specs: `document-chunking` (added, modified)
- Affected code: `src/application/use_cases/chunk_document.py` (drive splitting from
  blocks), a new table-splitting component in `src/core/` (pure, testable, no provider or
  chunker knowledge), `src/infrastructure/chonkie/chunker_chonkie.py` and
  `table_handler.py` (regex path demoted to the fallback),
  `src/core/entities/chunk.py` (row-range metadata)
- Retrieval: table chunks change shape for newly chunked documents — smaller pieces for
  large tables, column context in each. Expected to improve retrieval on tabular questions
  and worth measuring rather than assuming.
- Risk: a document whose extraction predates the block list follows the fallback path, so
  both paths need to stay tested until backfill or re-extraction happens.
