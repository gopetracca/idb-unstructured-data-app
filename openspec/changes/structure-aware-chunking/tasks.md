# Tasks

> Depends on `provider-neutral-extraction-model`.

## 1. Partitioning

- [ ] 1.1 Add a pure partitioner in `src/core/` that takes the extraction output — the
      extracted text, the block list, **and the tables** — plus a chunk size, and returns
      regions marked prose or table. It resolves a table block to its table through the
      block's table reference, because composing a fragment needs `render_prefix`, `rows`
      and `render_suffix`, none of which are on the block. No chunker, provider, or IO
      knowledge.
- [ ] 1.2 Table splitting: cut only between the body rows the extractor supplied — never
      at positions derived from cell spans — and never between a row and one marked as
      continuing from it. Compose each piece as `render_prefix + rows + render_suffix`.
      Emit an oversized chunk for a single indivisible group that cannot fit, and log it.
- [ ] 1.3 Record the row range each piece covers, the source range of its own rows, and the
      source range of the prefix it carries.

## 2. Stage

- [ ] 2.1 `chunk_document.py` — partition first, send prose regions to `ChunkerPort`, emit
      table regions directly, and interleave in document order with correct `start_char`
      and `end_char`.
- [ ] 2.2 Set `has_table`, `table_id`, `page_number`, `section_path` for table chunks, and
      the row range for split pieces.
- [ ] 2.3 Fallback: when the extraction output has no blocks, use the existing regex path.

## 3. Adapters

- [ ] 3.1 `chunker_chonkie.py` — remove table extraction from the adapter; keep
      `table_handler.py` for the fallback only, with a docstring saying so.
- [ ] 3.2 Confirm `chunker_llamaindex.py` now gets table handling with no change of its own.

## 4. Metadata, offsets and schema

- [ ] 4.1 Add the row range to `ChunkMetadata`; check whether the search index schema should
      carry it (`src/core/index_schemas/chunk_fields.py`) or whether it stays chunk-local.
- [ ] 4.2 Update `has_table`'s description — it currently says "contains an HTML table",
      which will no longer be true.
- [ ] 4.3 Restate `start_char`/`end_char` on `Chunk` and `ChunkIndex` as provenance of the
      chunk's own content, and add the prepended **prefix** source range and flag — not a
      header range: the prefix may be markup alone, header rows, or a row the rendering
      requires that the provider did not mark as a header.
- [ ] 4.4 Record the composed text's length on `Chunk` and `ChunkIndex` when the chunk is
      created, and persist it — `list_chunks` serves a paginated listing from index rows
      carrying only `text_preview`, so it cannot recompute a length without a blob fetch per
      chunk. Add the column and a migration; backfill it from `end_char - start_char`, which
      is exact for every chunk that exists today because all of them are verbatim slices.
- [ ] 4.4a Change `list_chunks.py:59` to report the recorded length instead of subtracting
      offsets.
- [ ] 4.5 Audit every other reader of these offsets for the same assumption before
      changing their meaning.

## 5. Tests

> Where a task names a scenario, the scenario in the delta is the statement of record and
> the task must not paraphrase it. Restating requirements here is what let the tasks drift
> out of step with the spec three times during review.

- [ ] 5.1 Partitioner unit tests: a table within size stays whole; an oversized table splits
      on row boundaries; every fragment is `render_prefix` + its rows + `render_suffix`; a
      single oversized row group is emitted whole. Note that *every* fragment carries the
      prefix, including for a table with no header cells — the prefix is what the rendering
      puts before the first body row, not a header, and for some forms it is never empty.
- [ ] 5.2 Cover *The rules do not depend on the rendering* and *Where the boundaries fall
      does depend on the rendering* with the same document in both forms. Implementation
      note, not in the spec: do **not** assert identical boundaries — `chunk_size` is a
      budget on text length and an HTML row runs about 2.6× a pipe row, so a test asserting
      equality would be wrong and would have to be weakened later.
- [ ] 5.3 `chunk_document` tests: on both the block-list path and the fallback path, every
      chunk's `start_char`/`end_char` delimit a valid range of `extracted_text` covering the
      content that chunk derives from — which is *not* the same as equalling the chunk's
      text. Whether the text equals that slice is a separate property, true for prose and
      deliberately false for a table piece carrying a repeated prefix; 5.7 asserts both
      cases. This task must not be written as "the offsets reconstruct the chunk".
- [ ] 5.4 Both chunker adapters produce the same table chunks for the same input.
- [ ] 5.5 A regression for the defect that motivated this: a table larger than the chunk
      size must not produce a single chunk exceeding it.
- [ ] 5.6 Cover *A split table is one table, not a table and copies of it*, *The repeated
      frame is not a duplicated row*, and *Pieces are attributable to one table*. Note that
      the coverage rule is about **body** rows: whatever the prefix carries is repeated in
      every piece by design, so a test asserting that no content recurs across pieces would
      contradict the contract.
- [ ] 5.7 Offsets: a prose chunk's text equals the slice at its offsets; a table piece
      carrying a prefix does not, and records the prefix's source range and the flag instead.
      Cover a pipe-table piece whose prefix is a row the provider did not mark as a header.
- [ ] 5.7a `list_chunks` reports the recorded length for a table piece carrying a prefix,
      and reads no blobs while doing so.
- [ ] 5.8 Cover *Rows joined by a merged cell stay together*.
- [ ] 5.8a Cover *A table with no header cells*, in a form that requires a header line:
      every piece still parses as a table in that form.
- [ ] 5.9 Cover *Pieces are composed, not sliced*: a piece is byte-identical to the fragment
      for its rows, and no piece is a slice of `extracted_text` taken at cell-span
      positions.

## 6. Evidence

- [ ] 6.1 Extend `scripts/show_extraction_output.py`, or add a sibling, to print the chunks
      a document would produce — so the effect on a real document is inspectable the way
      the extraction output now is.
- [ ] 6.2 Measure retrieval before and after on table-bearing documents with questions whose
      answers are in cells. Record the result, including if it shows no improvement.

## 7. Docs

- [ ] 7.1 Document the chunking rules for tables in `docs/`, including the repeated prefix
      and its token cost, and that boundaries depend on the rendering's length while the
      rules do not.
