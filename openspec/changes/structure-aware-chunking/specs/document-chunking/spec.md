# document-chunking Delta

## ADDED Requirements

### Requirement: Tables Are Chunked As Structure, Not As Text

The chunking stage SHALL take table boundaries from the extraction output's block list,
and SHALL NOT recover them by matching patterns in the rendered text.

#### Scenario: Table boundaries come from the extraction output

- **WHEN** a document whose extraction output carries a block list is chunked
- **THEN** each table's extent is taken from its block, and no chunk boundary falls inside a
  table

#### Scenario: The rendering does not matter

- **WHEN** one document's tables were rendered as HTML and another's as pipe tables
- **THEN** both are chunked identically with respect to table boundaries, headers, and
  metadata

#### Scenario: Chunk text is the extractor's rendering

- **WHEN** a chunk contains a table or part of one
- **THEN** its text is the rendering the extractor produced for that table, not a
  re-serialisation by the chunker

#### Scenario: Every chunker behaves the same

- **WHEN** the configured chunker is changed
- **THEN** table handling is unaffected, because it is performed by the chunking stage
  rather than by the chunker

### Requirement: Oversized Tables Are Split On Row Boundaries With Their Header

The chunking stage SHALL split a table that exceeds the configured chunk size, cutting only
between rows and repeating the table's header rows in every piece.

#### Scenario: A table larger than the chunk size

- **WHEN** a table's rendering exceeds the strategy's chunk size
- **THEN** it is emitted as several chunks, each cut at a row boundary and each carrying the
  table's header rows

#### Scenario: A table within the chunk size

- **WHEN** a table fits within the chunk size
- **THEN** it is emitted as a single chunk and its header is not repeated

#### Scenario: Every piece is independently interpretable

- **WHEN** a chunk holds rows from the middle of a table
- **THEN** it begins with the table's header rows, so the columns its values belong to can
  be determined from the chunk alone

#### Scenario: Pieces are composed, not sliced

- **WHEN** a piece of a table is emitted
- **THEN** its text is composed from the renderings the extractor supplied — the table's
  opening rendering, the piece's rows, and the closing rendering — and the stage does not
  cut the extracted text at positions derived from cell spans

#### Scenario: Rows joined by a merged cell stay together

- **WHEN** a table contains a cell spanning several rows
- **THEN** no cut falls between those rows, so no piece is missing content rendered only in
  the first of them

#### Scenario: A single row larger than the chunk size

- **WHEN** one row's rendering alone exceeds the chunk size
- **THEN** that row is emitted whole in an oversized chunk rather than cut, and the
  condition is logged

#### Scenario: A table with no header

- **WHEN** a table that declares no header rows is split
- **THEN** the pieces carry no header prefix and splitting still occurs on row boundaries

#### Scenario: A split table is one table, not a table and copies of it

- **WHEN** a table is split into several chunks
- **THEN** no further chunk containing the whole table is emitted, and each row of the table
  appears in exactly one piece, so the pieces cover the table once rather than duplicating it

#### Scenario: Pieces are attributable to one table

- **WHEN** a consumer reads several chunks produced from one split table
- **THEN** every piece carries the same table identifier and its own row range, so they can
  be recognised as one table and ordered without comparing their text

### Requirement: Table Chunk Metadata

A chunk containing a table or part of one SHALL record enough for a consumer to tell what
it holds.

#### Scenario: Whole table

- **WHEN** a chunk holds an entire table
- **THEN** it records that it contains a table, the table's identifier, and its page number

#### Scenario: Partial table

- **WHEN** a chunk holds part of a split table
- **THEN** it additionally records the range of table rows it covers, so a partial table is
  distinguishable from a whole one

### Requirement: Chunk Offsets Record Provenance

A chunk's character offsets SHALL identify where its own content came from in the extracted
text, and SHALL NOT be relied upon as an instruction for slicing that text.

#### Scenario: A chunk whose text is a verbatim slice

- **WHEN** a chunk carries no content prepended from elsewhere
- **THEN** its offsets delimit exactly the text it holds, as before

#### Scenario: A table piece carrying a repeated header

- **WHEN** a piece of a split table is emitted with the table's header prepended
- **THEN** its offsets delimit the rows the piece itself covers, and the piece additionally
  records the source range of the prepended header and that it carries one

#### Scenario: Length is taken from the text

- **WHEN** a consumer reports a chunk's character count
- **THEN** it is derived from the chunk's text rather than from the difference between its
  offsets, which excludes any prepended content

## MODIFIED Requirements

### Requirement: Chunk A Document

The system SHALL chunk a document's extracted text using the requested strategy, respecting
the structural boundaries the extraction output declares, store each chunk in the chunks
container, and record a chunk index row per chunk.

#### Scenario: Successful chunking

- **WHEN** `POST /api/v1/chunks` is called with `documents.write` for a document whose extracted text exists
- **THEN** the text is chunked, each chunk is written to `{tenant_id}/{file_id}/chunks/{chunk_id}.json`, a chunk index row is created per chunk, and the response is `202` carrying `file_id`, `status`, `chunk_count`, `chunks_url`, the strategy used, `correlation_id`, and `processing_time_ms`

#### Scenario: Extraction output without a block list

- **WHEN** the document's extraction output predates the canonical block list
- **THEN** table boundaries are recovered from the rendered HTML as before, and chunking
  succeeds with the same guarantees for HTML-rendered tables

#### Scenario: Text located via the recorded reference

- **WHEN** the source text is loaded
- **THEN** the document's `text_blob_ref` column is used as the source of truth for its location

#### Scenario: Missing text reference

- **WHEN** the document has no `text_blob_ref`
- **THEN** a chunking error with reason `missing_text_blob_ref` is raised

#### Scenario: Text blob absent

- **WHEN** the recorded text blob does not exist in the source container
- **THEN** a text-not-found error is raised and the response is `404`

#### Scenario: Empty extracted text

- **WHEN** the text JSON contains no `extracted_text` content
- **THEN** a chunking error is raised rather than producing zero chunks silently

#### Scenario: Unknown document

- **WHEN** the `file_id` has no record for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

#### Scenario: Chunk count recorded

- **WHEN** chunking completes
- **THEN** the document's pipeline state is updated with the resulting chunk count
