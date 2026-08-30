# A provider-neutral extraction model

## Why

Downstream stages read the extractor's output as **rendered text**, and recover structure
from it by pattern-matching. `ChonkieChunker.chunk_text` calls
`table_handler.extract_tables`, which regex-scans `extracted_text` for
`<table>…</table>` spans, replaces each with a placeholder, chunks what is left, and
re-inserts each table as its own atomic chunk. It works — tables are not split today, and
`has_table`, `table_id`, `section_path` and `page_number` are populated — but it works by
reading HTML that happens to be in the markdown Azure Document Intelligence produces.

That coupling has three costs.

**It breaks the moment the provider changes.** Docling — the alternative under
consideration — exports tables as Markdown pipe tables, not HTML, by default. Point this
pipeline at Docling and `_find_outermost_tables` returns nothing: every table stops being
atomic and gets split by character count like ordinary prose, silently, with no error and
no failing test. The regex is a provider assumption written in a file that never mentions
the provider.

**Only one chunker has it.** `chunker_llamaindex.py` contains no table handling at all.
The behaviour is a property of the Chonkie adapter rather than of the chunking stage, so
which structure a document keeps depends on which chunking implementation is configured.

**It re-derives what we already have.** Since `preserve-full-extraction-output`, the
extractor stores the real cell grid — row and column indices, spans, header kinds,
per-cell page and geometry. The chunker parses HTML to approximate a fact that is sitting
in the same file, one field away.

The structural data is there. What is missing is a contract that presents it the same way
whatever produced it.

## What Changes

Introduce a canonical extraction model that the `convert` stage emits and downstream
stages consume, so no consumer knows or cares which service produced it.

- **An ordered block list.** `ExtractedDocument` carries the rendered `text` plus `blocks`
  in reading order — heading, paragraph, table, figure, caption, list item — each with the
  character range it occupies **in that text**, a page number, and geometry where the
  provider supplies it.
- **The offset invariant is the adapter's job.** Every block's `(start, end)` must resolve
  against `text`. Azure Document Intelligence gives those offsets directly; a Docling
  adapter renders the text itself and records offsets as it emits. Downstream code may
  rely on the invariant without knowing which happened.
- **Normalised table structure.** A canonical `CellRole` (`content`, `column_header`,
  `row_header`, `section_row`, `stub_head`) replaces provider spellings — Document
  Intelligence's `kind` string and Docling's `column_header`/`row_header`/`row_section`
  booleans both map onto it. Each table also carries `header_rows`: the row indices that
  form its header, computed by the adapter.
- **The adapter renders, the consumer never parses — including for parts of a table.**
  A table carries `rendered` (its text exactly as it appears in `text`) and, so that a
  consumer can emit *some rows* of it without knowing the markup: `render_prefix` (the
  opening markup plus the header rows), `render_suffix` (the closing markup), and `rows`
  (the body rows, each with its own rendering). Any subset renders as
  `render_prefix + rows… + render_suffix`, which is a valid table in whatever form the
  extractor produced. This is what makes HTML-vs-pipe-table a non-question — and it is
  needed because cell spans do **not** delimit rendered rows: on a real Document
  Intelligence response, the min-to-max span of row 0's cells is `Budget Summary`, while
  the row's actual rendering is `<tr>\n<th colspan="2">Budget Summary</th>\n</tr>`. Slicing
  a table at cell spans yields fragments that are not tables.
- **Rows carry their own provenance.** Each body row records where its rendering sits in
  `text` when that range is contiguous, and records when a vertically merged cell makes it
  inseparable from the row above — so a consumer can find a legal cut point without
  reasoning about markup or spans.
- **Explicit geometry units.** Document Intelligence reports inches from a top-left
  origin; Docling reports points and can use either origin. The canonical bounding box
  records `unit` and `origin` rather than assuming, so nothing silently compares
  incompatible numbers.
- **Opaque cross-references.** Provider element references (`/paragraphs/2`,
  `#/texts/2`) are preserved verbatim and explicitly not interpreted by any consumer.
- **Additive serialisation, again.** `text.json` gains `blocks`; `extracted_text`,
  `pages`, `tables` and `extraction_metadata` keep their meaning. Output written before
  this change deserialises with an empty block list, and consumers must treat that as
  "structure unavailable" rather than "no structure".

This change defines the contract and makes the Azure adapter satisfy it. It does **not**
implement a Docling adapter — but the mapping is specified in `design.md` for both
providers, because a contract that has only ever been satisfied by one implementation is a
contract in name only.

## Impact

- Affected specs: `content-extraction` (added, modified), `adapter-selection` (added)
- Affected code: `src/core/entities/document_analysis.py` (canonical model),
  `src/application/ports/document_intelligence.py` (port renamed to a provider-neutral
  `DocumentExtractorPort`, keeping the old name as an alias),
  `src/infrastructure/azure/adapters/document_intelligence_azure.py` (emit blocks),
  the fake adapter, `src/application/use_cases/process_document.py` (serialise blocks)
- Not affected: the `202` contract, blob layout, references, and every stage after
  `convert` — those change in `structure-aware-chunking`, which depends on this
- Risk: the block list roughly doubles `text.json` for structure-heavy documents. Measured
  on the sample used in `preserve-full-extraction-output`: 9.8 KB → ~12 KB. Same order,
  and the raw sidecar is unchanged.
