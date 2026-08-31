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

- **An ordered block list.** `MarkdownOutput` — the type the stage already returns — gains
  `blocks` in reading order beside the existing `extracted_text`: heading, paragraph,
  table, figure, caption, list item, each with the character range it occupies **in that
  text**, a page number, and geometry where the provider supplies it.
- **The offset invariant is the adapter's job.** Every block's `(start, end)` must resolve
  against `extracted_text`. Azure Document Intelligence gives those offsets directly; a Docling
  adapter renders the text itself and records offsets as it emits. Downstream code may
  rely on the invariant without knowing which happened.
- **Normalised table structure.** A canonical `CellRole` (`content`, `column_header`,
  `row_header`, `section_row`, `stub_head`) replaces provider spellings — Document
  Intelligence's `kind` string and Docling's `column_header`/`row_header`/`row_section`
  booleans both map onto it. Each table also carries `header_rows`: the row indices that
  form its header, computed by the adapter.
- **The adapter renders, the consumer never parses — including for parts of a table.**
  A table carries `rendered` (its text exactly as it appears in `extracted_text`) and, so that a
  consumer can emit *some rows* of it without knowing the markup: `render_prefix` (exactly
  the part of the rendering before the first body row), `render_suffix` (exactly the part
  after the last), and `rows` (the body rows, each with its own rendering). A fragment is
  `render_prefix` + the chosen rows + `render_suffix`, and is a valid table in whatever
  form the extractor produced — including forms like Markdown pipe tables that cannot
  express a table without a header line. This is what makes HTML-vs-pipe-table a non-question — and it is
  needed because cell spans do **not** delimit rendered rows: on a real Document
  Intelligence response, the min-to-max span of row 0's cells is `Budget Summary`, while
  the row's actual rendering is `<tr>\n<th colspan="2">Budget Summary</th>\n</tr>`. Slicing
  a table at cell spans yields fragments that are not tables.
- **Rows carry their own provenance.** Each body row records where its rendering sits in
  `extracted_text` when that range is contiguous, and records when a vertically merged cell makes it
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

## A name this change does not fix

`MarkdownOutput` is a poor name for what it now holds — a structured document with blocks,
tables and geometry, of which the markdown is one field. Renaming it to something like
`ExtractedDocument` would be an improvement and is deliberately **not** part of this change:
`add-docling-extraction-adapter` is in flight against `MarkdownOutput` by name, and a rename
would turn a clean parallel change into a collision for no functional gain. Worth doing once
both have landed.

## Relationship to `add-docling-extraction-adapter`

That change, proposed in parallel by another session, adds a real Docling adapter against
the contract as it stands today. This one changes the contract. They are complementary —
one supplies the second implementation, the other makes the interface provider-neutral —
but they overlap, and whoever sequences them should know where:

- **This change renames the port** to `DocumentExtractorPort` (keeping the old name as an
  alias). That change implements `DocumentIntelligencePort` by its current name. The alias
  is what stops that from being a conflict.
- **That change adds `analysis_format` to `extraction_metadata`**, distinguishing an Azure
  `AnalyzeResult` from a serialised `DoclingDocument`. This change does not, and should
  adopt it rather than duplicate the idea: the raw sidecar is provider-shaped by design, so
  naming its shape belongs in the contract.
- **The burden this change places on a Docling adapter is real.** That proposal describes
  its mapping as "a projection, not a reconstruction", which is true for tables, provenance
  and reading order. It is not true for `render_prefix`, `rows` and `render_suffix`: Docling
  has no single rendered string with offsets into it, so its adapter must render the markdown
  itself and partition what it wrote. That is more work than a projection, and it is the
  work that makes the offset invariant hold for both providers.

If both land, this change should land first and that one should be measured against the
contract test in task 5.3 — which exists so a second adapter inherits the same bar rather
than a looser one.

## Impact

- Affected specs: `content-extraction` (added, modified), `adapter-selection` (added)
- Affected code: `src/core/entities/document_analysis.py` (canonical model),
  `src/application/ports/document_intelligence.py` (port renamed to a provider-neutral
  `DocumentExtractorPort`, keeping the old name as an alias),
  `src/infrastructure/azure/adapters/document_intelligence_azure.py` (emit blocks),
  the fake adapter, `src/application/use_cases/process_document.py` (serialise blocks)
- Not affected: the `202` contract, blob layout, references, and every stage after
  `convert` — those change in `structure-aware-chunking`, which depends on this
- Risk: `text.json` grows. Measured against the real service on the sample used in
  `preserve-full-extraction-output`: **9.8 KB → 11.5 KB**, +17%. Most of it is the table's
  rendering being stored twice — once whole in `rendered`, once split across
  `render_prefix`, `rows` and `render_suffix` — so the growth tracks how much of a document
  is tables rather than how long it is. Same order of magnitude, and the raw sidecar is
  unchanged at 8.8 KB.
