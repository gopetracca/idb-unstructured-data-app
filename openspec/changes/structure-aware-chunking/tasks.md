# Tasks

> Depends on `provider-neutral-extraction-model`.

## 1. Partitioning

- [ ] 1.1 Add a pure partitioner in `src/core/` that takes the block list, the extracted
      text, and a chunk size, and returns regions marked prose or table — no chunker,
      provider, or IO knowledge.
- [ ] 1.2 Table splitting: cut only at row boundaries derived from cell spans; prefix
      pieces after the first with `header_rendered`; emit an oversized chunk for a single
      row that cannot fit, and log it.
- [ ] 1.3 Record the row range each piece covers.

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

## 4. Metadata and schema

- [ ] 4.1 Add the row range to `ChunkMetadata`; check whether the search index schema should
      carry it (`src/core/index_schemas/chunk_fields.py`) or whether it stays chunk-local.
- [ ] 4.2 Update `has_table`'s description — it currently says "contains an HTML table",
      which will no longer be true.

## 5. Tests

- [ ] 5.1 Partitioner unit tests: table within size stays whole; oversized table splits on
      row boundaries; every piece carries the header; a single oversized row is emitted
      whole; a table with no header splits without a prefix.
- [ ] 5.2 The same document rendered as HTML and as pipe tables produces identical chunk
      boundaries and metadata — the provider-independence claim, as a test.
- [ ] 5.3 `chunk_document` tests: block-list path and fallback path both produce chunks
      whose `start_char`/`end_char` resolve against the extracted text.
- [ ] 5.4 Both chunker adapters produce the same table chunks for the same input.
- [ ] 5.5 A regression for the defect that motivated this: a table larger than the chunk
      size must not produce a single chunk exceeding it.

## 6. Evidence

- [ ] 6.1 Extend `scripts/show_extraction_output.py`, or add a sibling, to print the chunks
      a document would produce — so the effect on a real document is inspectable the way
      the extraction output now is.
- [ ] 6.2 Measure retrieval before and after on table-bearing documents with questions whose
      answers are in cells. Record the result, including if it shows no improvement.

## 7. Docs

- [ ] 7.1 Document the chunking rules for tables in `docs/`, including the header repetition
      and its token cost.
